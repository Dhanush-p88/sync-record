import os
import time
import logging
from logging.handlers import RotatingFileHandler
import threading
from datetime import datetime, timezone

from backend.config import Config
from backend.models import db, ProcessingQueue, Setting

# Dedicated logger for File Stabilization
logger = logging.getLogger("file_stabilization")
logger.setLevel(logging.INFO)
logger.propagate = False

os.makedirs(Config.LOGS_DIR, exist_ok=True)
log_file_path = os.path.join(Config.LOGS_DIR, "stabilization.log")

if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [Stabilization] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers):
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [Stabilization] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)


class StabilizationService:
    """Service to monitor files until their size remains unchanged for a configured period."""

    DEFAULT_STABILIZATION_TIME = 30.0  # seconds
    CHECK_INTERVAL = 2.0  # check every 2 seconds
    MAX_TIMEOUT_SECONDS = 900.0  # 15 minutes max stabilization timeout

    def __init__(self, app=None, check_interval=None, default_stab_time=None):
        self.app = app
        self.check_interval = check_interval or self.CHECK_INTERVAL
        self.default_stab_time = default_stab_time or self.DEFAULT_STABILIZATION_TIME
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # In-memory tracking state:
        # queue_id -> { "last_size": int, "stable_since": float, "started_at": float, "filename": str }
        self._tracked_files = {}

    def init_app(self, app):
        """Bind Flask app instance."""
        self.app = app

    def start(self):
        """Starts the background stabilization monitor loop."""
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="FileStabilizerThread")
            self._thread.start()
            logger.info("Stabilization service started")

    def stop(self):
        """Stops the background stabilization monitor loop."""
        with self._lock:
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            self._thread = None
            logger.info("Stabilization service stopped")

    def get_configured_stabilization_time(self):
        """Reads stabilization period from the MySQL Setting table (defaults to 30.0 seconds)."""
        if not self.app:
            return self.default_stab_time

        try:
            with self.app.app_context():
                setting = Setting.query.filter_by(key="stabilization_time").first()
                if setting and setting.value:
                    try:
                        val = float(setting.value.strip())
                        if val > 0:
                            return val
                    except ValueError:
                        pass
        except Exception as exc:
            logger.warning(f"Could not read stabilization_time from database ({exc}), using default {self.default_stab_time}s")
        return self.default_stab_time

    def _worker_loop(self):
        """Periodic background evaluation loop."""
        while self._running:
            try:
                self.check_active_queue_files()
            except Exception as exc:
                logger.error(f"Stabilization error in worker loop: {exc}", exc_info=True)
            
            # Sleep in small increments for responsive shutdown
            slept = 0.0
            while self._running and slept < self.check_interval:
                time.sleep(0.5)
                slept += 0.5

    def check_active_queue_files(self):
        """Queries database for items in Pending or Stabilizing status and evaluates their file size."""
        if not self.app:
            return

        with self.app.app_context():
            try:
                items = ProcessingQueue.query.filter(
                    ProcessingQueue.status.in_(["Pending", "Stabilizing"])
                ).all()
            except Exception as exc:
                logger.error(f"Stabilization error querying database: {exc}")
                return

            now_ts = time.time()
            stab_time = self.get_configured_stabilization_time()

            for item in items:
                self._evaluate_file(item, now_ts, stab_time)

    def _evaluate_file(self, item, now_ts, stab_time):
        """Evaluates stabilization criteria for a single ProcessingQueue item."""
        queue_id = item.id
        filepath = item.file_path
        filename = item.file_name or os.path.basename(filepath)

        # 1. Check if file was deleted before stabilization
        if not os.path.exists(filepath):
            logger.error(f"Stabilization error: File deleted before stabilization: '{filename}'")
            item.status = "Failed"
            item.error_message = "File was deleted before stabilization completed"
            item.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            self._tracked_files.pop(queue_id, None)
            return

        # 2. Check accessibility / file lock
        try:
            stat_info = os.stat(filepath)
            current_size = stat_info.st_size
        except (PermissionError, OSError) as exc:
            logger.warning(f"File locked/in use or inaccessible: '{filename}' ({exc}). Will retry.")
            if item.status != "Stabilizing":
                item.status = "Stabilizing"
                db.session.commit()
            return
        except Exception as exc:
            logger.error(f"Stabilization error: Inaccessible file '{filename}': {exc}")
            return

        # Initialize tracking if not present
        track_info = self._tracked_files.get(queue_id)
        if not track_info:
            track_info = {
                "last_size": current_size,
                "stable_since": now_ts,
                "started_at": now_ts,
                "filename": filename
            }
            self._tracked_files[queue_id] = track_info
            logger.info(f"Stabilization started for '{filename}' (Initial size: {current_size} bytes, target: {stab_time}s)")
            if item.status != "Stabilizing":
                item.status = "Stabilizing"
                item.file_size = current_size
                db.session.commit()
            return

        # 3. Timeout check
        elapsed_total = now_ts - track_info["started_at"]
        if elapsed_total > self.MAX_TIMEOUT_SECONDS:
            logger.error(f"Stabilization error: Timeout ({self.MAX_TIMEOUT_SECONDS}s) exceeded for '{filename}'")
            item.status = "Failed"
            item.error_message = f"Stabilization timed out after {int(elapsed_total)}s"
            item.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            self._tracked_files.pop(queue_id, None)
            return

        # 4. Check for size = 0
        if current_size == 0:
            # File is empty/0-bytes, not ready
            track_info["stable_since"] = now_ts
            track_info["last_size"] = 0
            if item.status != "Stabilizing":
                item.status = "Stabilizing"
                item.file_size = 0
                db.session.commit()
            return

        # 5. Check if file size is still changing
        if current_size != track_info["last_size"]:
            prev_size = track_info["last_size"]
            track_info["last_size"] = current_size
            track_info["stable_since"] = now_ts  # reset stable timer

            logger.info(f"File still changing: '{filename}' (Previous: {prev_size} B, Current: {current_size} B)")
            item.status = "Stabilizing"
            item.file_size = current_size
            item.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return

        # 6. File size has remained unchanged
        stable_duration = now_ts - track_info["stable_since"]
        item.file_size = current_size

        if stable_duration >= stab_time:
            # File is STABILIZED and READY!
            completion_time = datetime.now(timezone.utc)
            item.status = "Ready"
            item.completed_time = completion_time
            item.error_message = None
            item.updated_at = completion_time
            db.session.commit()

            logger.info(f"File stabilized: '{filename}' (Size: {current_size} bytes, stable for {stable_duration:.1f}s)")
            self._tracked_files.pop(queue_id, None)

            # Day 4: Automatically identify batch for the stabilized file
            try:
                from backend.services.batch_manager import batch_manager_service
                batch_manager_service.process_item(item)
            except Exception as b_exc:
                logger.error(f"Error during batch identification for '{filename}': {b_exc}")
        else:
            # Keep status as Stabilizing (or Pending if still initially waiting)
            if item.status != "Stabilizing":
                item.status = "Stabilizing"
                db.session.commit()


# Singleton stabilization service
stabilization_service = StabilizationService()
