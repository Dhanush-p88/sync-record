import os
import stat
import fnmatch
import logging
from logging.handlers import RotatingFileHandler
import threading
from datetime import datetime, timezone
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.config import Config
from backend.models import db, ProcessingQueue

# Setup dedicated logger for File Watcher
logger = logging.getLogger("file_watcher")
logger.setLevel(logging.INFO)
logger.propagate = False

# Ensure logs directory exists
os.makedirs(Config.LOGS_DIR, exist_ok=True)
log_file_path = os.path.join(Config.LOGS_DIR, "file_watcher.log")

# Add RotatingFileHandler if not already added
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [FileWatcher] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# Add Console Handler if not already present
if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers):
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [FileWatcher] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)


def is_hidden_or_system_file(filepath):
    """Checks if a file is hidden or marked as system file."""
    basename = os.path.basename(filepath)
    if basename.startswith("."):
        return True
    
    # Windows-specific attribute check
    if os.name == "nt":
        try:
            attrs = os.stat(filepath).st_file_attributes
            if attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM):
                return True
        except Exception:
            pass
    return False


class RecordingFileHandler(FileSystemEventHandler):
    """Watchdog event handler for monitoring recording files."""

    def __init__(self, service):
        super().__init__()
        self.service = service

    def on_created(self, event):
        if not event.is_directory:
            self.service.process_detected_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.service.process_detected_file(event.dest_path)


class FileWatcherService:
    """Manages the lifecycle and processing of the directory file watcher."""

    STATUS_RUNNING = "RUNNING"
    STATUS_PAUSED = "PAUSED"
    STATUS_STOPPED = "STOPPED"

    def __init__(self, app=None, watch_folder=None):
        self.app = app
        self.watch_folder = os.path.abspath(watch_folder or Config.WATCH_FOLDER)
        self.supported_extensions = {ext.lower() for ext in Config.SUPPORTED_EXTENSIONS}
        self.ignored_extensions = {ext.lower() for ext in Config.IGNORED_EXTENSIONS}
        self.ignored_patterns = Config.IGNORED_PATTERNS
        
        self.state = self.STATUS_STOPPED
        self.observer = None
        self._lock = threading.Lock()

        # Ensure watch folder exists
        os.makedirs(self.watch_folder, exist_ok=True)

    def init_app(self, app):
        """Initializes service with Flask application instance."""
        self.app = app

    def start(self):
        """Starts monitoring the configured watch folder."""
        with self._lock:
            if self.state == self.STATUS_RUNNING:
                return {
                    "success": True,
                    "message": "Monitoring is already running",
                    "status": self.state
                }

            if self.state == self.STATUS_PAUSED:
                self.state = self.STATUS_RUNNING
                logger.info("Monitoring resumed")
                return {
                    "success": True,
                    "message": "Monitoring resumed",
                    "status": self.state
                }

            try:
                os.makedirs(self.watch_folder, exist_ok=True)
                event_handler = RecordingFileHandler(self)
                self.observer = Observer()
                self.observer.schedule(event_handler, self.watch_folder, recursive=False)
                self.observer.daemon = True
                self.observer.start()
                self.state = self.STATUS_RUNNING
                logger.info(f"Monitoring started on watch folder: '{self.watch_folder}'")

                # Also ensure stabilization service is running
                from backend.services.stabilization import stabilization_service
                stabilization_service.init_app(self.app)
                stabilization_service.start()

                return {
                    "success": True,
                    "message": f"Monitoring started on '{self.watch_folder}'",
                    "status": self.state
                }
            except Exception as exc:
                self.state = self.STATUS_STOPPED
                logger.error(f"Error starting file watcher: {exc}", exc_info=True)
                return {
                    "success": False,
                    "message": f"Failed to start monitoring: {exc}",
                    "status": self.state
                }

    def pause(self):
        """Pauses file detection processing."""
        with self._lock:
            if self.state == self.STATUS_STOPPED:
                return {
                    "success": False,
                    "message": "Cannot pause: Monitoring is currently stopped",
                    "status": self.state
                }
            if self.state == self.STATUS_PAUSED:
                return {
                    "success": True,
                    "message": "Monitoring is already paused",
                    "status": self.state
                }

            self.state = self.STATUS_PAUSED
            logger.info("Monitoring paused")
            return {
                "success": True,
                "message": "Monitoring paused",
                "status": self.state
            }

    def resume(self):
        """Resumes file detection processing from paused state."""
        with self._lock:
            if self.state == self.STATUS_STOPPED:
                return {
                    "success": False,
                    "message": "Cannot resume: Monitoring is stopped. Start monitoring instead.",
                    "status": self.state
                }
            if self.state == self.STATUS_RUNNING:
                return {
                    "success": True,
                    "message": "Monitoring is already running",
                    "status": self.state
                }

            self.state = self.STATUS_RUNNING
            logger.info("Monitoring resumed")
            return {
                "success": True,
                "message": "Monitoring resumed",
                "status": self.state
            }

    def stop(self):
        """Stops the watchdog observer completely."""
        with self._lock:
            if self.state == self.STATUS_STOPPED:
                return {
                    "success": True,
                    "message": "Monitoring is already stopped",
                    "status": self.state
                }

            try:
                if self.observer and self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join(timeout=2)
                self.observer = None
                self.state = self.STATUS_STOPPED
                logger.info("Monitoring stopped")

                # Also stop stabilization service
                from backend.services.stabilization import stabilization_service
                stabilization_service.stop()

                return {
                    "success": True,
                    "message": "Monitoring stopped",
                    "status": self.state
                }
            except Exception as exc:
                logger.error(f"Error stopping file watcher: {exc}", exc_info=True)
                return {
                    "success": False,
                    "message": f"Failed to cleanly stop monitoring: {exc}",
                    "status": self.state
                }

    def process_detected_file(self, filepath):
        """Evaluates and inserts newly detected file into processing_queue."""
        # 1. State check
        if self.state != self.STATUS_RUNNING:
            return

        filename = os.path.basename(filepath)
        norm_filepath = os.path.abspath(filepath)
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()

        # 2. Check for hidden or system files
        if is_hidden_or_system_file(norm_filepath):
            return

        # 3. Check for explicitly ignored extensions (.tmp, .part, .crdownload)
        if ext_lower in self.ignored_extensions:
            return

        # 4. Check for ignored patterns (~*, .*, desktop.ini, thumbs.db)
        for pattern in self.ignored_patterns:
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                return

        # 5. Check supported extensions
        if ext_lower not in self.supported_extensions:
            logger.info(f"Unsupported file ignored: {filename}")
            return

        # 6. Database record insertion (prevent duplicates)
        if not self.app:
            logger.error(f"Error: Flask app context not configured in FileWatcherService for {filename}")
            return

        with self.app.app_context():
            try:
                # Prevent duplicate file from being added multiple times
                existing = ProcessingQueue.query.filter_by(file_path=norm_filepath).first()
                if existing:
                    return

                # Record file size at detection time if file is accessible
                init_size = 0
                try:
                    init_size = os.path.getsize(norm_filepath)
                except Exception:
                    pass

                now = datetime.now(timezone.utc)
                new_queue_item = ProcessingQueue(
                    file_name=filename,
                    file_path=norm_filepath,
                    file_size=init_size,
                    task_type="file_detection",
                    status="Pending",
                    detected_time=now,
                    created_at=now,
                    updated_at=now
                )
                db.session.add(new_queue_item)
                db.session.commit()

                logger.info(f"File detected: {filename} (Path: {norm_filepath})")

                # Notify stabilization service immediately
                from backend.services.stabilization import stabilization_service
                stabilization_service.check_active_queue_files()

            except Exception as exc:
                db.session.rollback()
                # If duplicate key or integrity error, quietly ignore or log info
                if "Duplicate entry" in str(exc) or "uq_file_path" in str(exc):
                    logger.info(f"File already queued, skipping duplicate: {filename}")
                else:
                    logger.error(f"Error queuing detected file '{filename}': {exc}", exc_info=True)

    def get_status(self):
        """Returns the current state, watch folder, and queue statistics."""
        pending_count = 0
        stabilizing_count = 0
        ready_count = 0
        recent_files = []
        stab_time = 30.0

        if self.app:
            from backend.services.stabilization import stabilization_service
            stab_time = stabilization_service.get_configured_stabilization_time()

            with self.app.app_context():
                try:
                    pending_count = ProcessingQueue.query.filter_by(status="Pending").count()
                    stabilizing_count = ProcessingQueue.query.filter_by(status="Stabilizing").count()
                    ready_count = ProcessingQueue.query.filter_by(status="Ready").count()
                    batch_identified_count = ProcessingQueue.query.filter_by(status="Batch Identified").count()
                    validated_count = ProcessingQueue.query.filter_by(status="Validated").count()
                    uploaded_count = ProcessingQueue.query.filter_by(status="Uploaded").count()
                    unknown_batch_count = ProcessingQueue.query.filter_by(status="Unknown Batch").count()
                    validation_failed_count = ProcessingQueue.query.filter_by(status="Validation Failed").count()
                    recents = (
                        ProcessingQueue.query.order_by(ProcessingQueue.id.desc())
                        .limit(10)
                        .all()
                    )
                    recent_files = [item.to_dict() for item in recents]

                    from backend.services.upload_engine import upload_engine_service
                    op_mode = upload_engine_service.get_operation_mode()
                except Exception as exc:
                    logger.error(f"Error reading status from database: {exc}")
                    op_mode = "COPY"

        return {
            "status": self.state,
            "watch_folder": self.watch_folder,
            "pending_files": pending_count,
            "stabilizing_files": stabilizing_count,
            "ready_files": ready_count,
            "batch_identified_files": batch_identified_count if 'batch_identified_count' in locals() else 0,
            "validated_files": validated_count if 'validated_count' in locals() else 0,
            "uploaded_files": uploaded_count if 'uploaded_count' in locals() else 0,
            "unknown_batch_files": unknown_batch_count if 'unknown_batch_count' in locals() else 0,
            "validation_failed_files": validation_failed_count if 'validation_failed_count' in locals() else 0,
            "operation_mode": op_mode if 'op_mode' in locals() else "COPY",
            "stabilization_time_seconds": stab_time,
            "recent_files": recent_files,
            "supported_extensions": list(self.supported_extensions)
        }


# Singleton service instance
file_watcher_service = FileWatcherService()
