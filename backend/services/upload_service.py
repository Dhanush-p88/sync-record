"""
Upload Service - Day 7 Implementation
Automated Session Recording Upload System

Provides:
1. Complete pipeline coordinator:
   Watchdog -> File Stabilization -> Batch Identification -> Validation -> Standardized Rename -> Copy/Move -> Verification -> MySQL Upload History
2. Asynchronous background execution:
   Runs processing in background threads/ThreadPoolExecutor without blocking Flask request threads.
3. Rich Upload History persistence in MySQL 'uploads' table:
   - Record ID
   - Batch ID & Batch Name
   - Original File Name & Path
   - Final File Name & Destination Path
   - File Size & Extension
   - Upload Date & Time
   - Status & Error Message
   - SHA-256 Checksum
4. Search, filtering, and pagination query engine:
   - search (filename or batch)
   - batch
   - status
   - date
   - pagination
5. Single upload record lookup API support.
6. Real MySQL Dashboard statistics aggregation:
   - Total Recordings
   - Successful Uploads
   - Failed Uploads
   - Pending
   - Unknown Batch
"""

import os
import hashlib
import logging
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, date
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import or_, and_, func
from backend.models import db, ProcessingQueue, Batch, Upload, Setting


def _setup_service_logger():
    """Sets up a dedicated rotating logger for the Upload Service."""
    logger = logging.getLogger("UploadService")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        os.makedirs("logs", exist_ok=True)
        log_file = os.path.join("logs", "upload_service.log")

        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [UploadService] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [UploadService] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


service_logger = _setup_service_logger()


def calculate_sha256(file_path):
    """Calculates SHA-256 checksum for a file using chunked reading."""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception as err:
        service_logger.warning(f"Could not compute checksum for '{file_path}': {err}")
        return None


class UploadService:
    """Service managing the end-to-end pipeline, asynchronous execution, and MySQL history."""

    def __init__(self, app=None):
        self.app = app
        self.logger = service_logger
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="PipelineWorker")

    def init_app(self, app):
        """Bind service to Flask application instance."""
        self.app = app

    def record_upload_success(self, item, dest_path, dest_size):
        """
        Creates a complete upload history record in MySQL and updates the queue item.
        """
        now_utc = datetime.now(timezone.utc)
        _, ext = os.path.splitext(dest_path)
        checksum = calculate_sha256(dest_path)

        # Check if upload already exists for this item or identical source path + checksum
        if item.upload_id:
            existing_upload = db.session.get(Upload, item.upload_id)
            if existing_upload:
                existing_upload.file_name = os.path.basename(dest_path)
                existing_upload.file_path = dest_path
                existing_upload.file_size = dest_size
                existing_upload.checksum = checksum
                existing_upload.status = "Uploaded"
                existing_upload.error_message = None
                existing_upload.uploaded_at = now_utc
                item.status = "Uploaded"
                item.completed_time = now_utc
                db.session.commit()
                return existing_upload

        existing_record = Upload.query.filter_by(
            original_file_path=item.file_path, status="Uploaded"
        ).first()
        if existing_record and existing_record.checksum == checksum:
            self.logger.info(
                f"Existing upload history found (ID #{existing_record.id}) for '{item.file_name}', avoiding duplicate"
            )
            item.upload_id = existing_record.id
            item.status = "Uploaded"
            item.completed_time = now_utc
            db.session.commit()
            return existing_record

        upload_record = Upload(
            batch_id=item.batch_id,
            batch_name=item.detected_batch,
            original_file_name=item.file_name,
            original_file_path=item.file_path,
            file_name=os.path.basename(dest_path),
            file_path=dest_path,
            file_size=dest_size,
            file_extension=ext.lower() if ext else None,
            upload_date=now_utc.date(),
            upload_time=now_utc.strftime("%H:%M:%S"),
            checksum=checksum,
            status="Uploaded",
            error_message=None,
            uploaded_at=now_utc,
        )
        db.session.add(upload_record)
        db.session.flush()

        item.upload_id = upload_record.id
        item.standardized_name = os.path.basename(dest_path)
        item.status = "Uploaded"
        item.error_message = None
        item.completed_time = now_utc
        db.session.commit()

        self.logger.info(
            f"Upload history recorded: ID {upload_record.id} for '{item.file_name}' -> '{upload_record.file_name}' (Batch: '{item.detected_batch}', Size: {dest_size} bytes)"
        )
        return upload_record

    def record_upload_failure(self, item, error_message):
        """
        Marks item as Failed, stores error message, and writes to log.
        """
        item.status = "Failed"
        item.error_message = str(error_message)
        now_utc = datetime.now(timezone.utc)
        item.completed_time = now_utc

        # Create failed upload record if an upload ID doesn't exist yet
        upload_record = None
        if not item.upload_id:
            upload_record = Upload(
                batch_id=item.batch_id,
                batch_name=item.detected_batch or "Unknown",
                original_file_name=item.file_name,
                original_file_path=item.file_path,
                file_name=item.standardized_name or item.file_name,
                file_path=item.file_path or "",
                file_size=item.file_size or 0,
                file_extension=os.path.splitext(item.file_name)[1].lower() if item.file_name else None,
                upload_date=now_utc.date(),
                upload_time=now_utc.strftime("%H:%M:%S"),
                checksum=None,
                status="Failed",
                error_message=str(error_message),
                uploaded_at=now_utc,
            )
            db.session.add(upload_record)
            db.session.flush()
            item.upload_id = upload_record.id

        db.session.commit()
        self.logger.error(f"Processing failed for file '{item.file_name}': {error_message}")
        return upload_record

    def process_pipeline_item(self, queue_id):
        """
        Executes the full pipeline for a single queue item from its current status.
        Runs:
        Ready -> Batch Identified -> Validated -> Standardized Renaming -> Copy/Move -> MySQL Upload Record
        """
        if not self.app:
            return {"success": False, "error": "App context not configured"}

        with self.app.app_context():
            item = db.session.get(ProcessingQueue, queue_id)
            if not item:
                return {"success": False, "error": f"Queue item {queue_id} not found"}

            try:
                # 1. Batch Identification if needed
                if item.status in {"Ready", "Pending", "Stabilizing"}:
                    from backend.services.batch_manager import batch_manager_service
                    item = batch_manager_service.process_item(item)

                if item.status == "Unknown Batch":
                    self.logger.warning(f"Pipeline stopped for '{item.file_name}': Batch is Unknown")
                    return {"success": False, "status": "Unknown Batch", "item": item.to_dict()}

                # 2. Validation & Renaming if in Batch Identified status
                if item.status == "Batch Identified":
                    from backend.services.file_processor import file_processor_service
                    proc_res = file_processor_service.process_item(item)
                    if not proc_res.get("success") or item.status != "Validated":
                        err = proc_res.get("error") or item.error_message or "File validation failed"
                        self.record_upload_failure(item, err)
                        return {"success": False, "status": "Failed", "error": err}

                # 3. Copy / Move Engine & Verification if in Validated status
                if item.status == "Validated":
                    from backend.services.upload_engine import upload_engine_service
                    transfer_res = upload_engine_service.process_item(item)
                    if not transfer_res.get("success") or item.status != "Uploaded":
                        err = transfer_res.get("error") or item.error_message or "File transfer failed"
                        self.record_upload_failure(item, err)
                        return {"success": False, "status": "Failed", "error": err}

                # 4. Enhance Upload Record with Day 7 metadata (checksum, extensions, dates)
                upload_rec = db.session.get(Upload, item.upload_id) if item.upload_id else None
                if upload_rec:
                    now_utc = datetime.now(timezone.utc)
                    upload_rec.batch_name = item.detected_batch
                    upload_rec.original_file_name = item.file_name
                    upload_rec.original_file_path = item.file_path
                    upload_rec.file_extension = os.path.splitext(upload_rec.file_name)[1].lower()
                    upload_rec.upload_date = now_utc.date()
                    upload_rec.upload_time = now_utc.strftime("%H:%M:%S")
                    upload_rec.status = "Uploaded"
                    if not upload_rec.checksum:
                        upload_rec.checksum = calculate_sha256(upload_rec.file_path)
                    db.session.commit()

                    # 5. Check if auto Google Drive export is configured in Settings
                    try:
                        from backend.models import Setting
                        dest_gdrive = r"G:\My Drive\meetings"
                        gdrive_setting = Setting.query.filter_by(key="gdrive_destination_folder").first()
                        if gdrive_setting and gdrive_setting.value and gdrive_setting.value.strip():
                            dest_gdrive = gdrive_setting.value.strip()
                        from backend.services.cloud_sync_service import cloud_sync_service
                        cloud_sync_service.auto_export_to_gdrive(upload_rec.file_path, dest_gdrive)
                    except Exception as g_err:
                        self.logger.warning(f"Google Drive auto-export note: {g_err}")

                return {
                    "success": True,
                    "status": "Uploaded",
                    "queue_id": item.id,
                    "upload_id": item.upload_id,
                    "standardized_name": item.standardized_name,
                    "batch": item.detected_batch,
                    "dest_path": upload_rec.file_path if upload_rec else None
                }

            except Exception as exc:
                self.logger.exception(f"Unexpected error in pipeline for item {queue_id}: {exc}")
                self.record_upload_failure(item, str(exc))
                return {"success": False, "status": "Failed", "error": str(exc)}

    def process_pipeline_item_async(self, queue_id):
        """
        Dispatches process_pipeline_item to the background thread pool,
        ensuring Flask request threads are NEVER frozen.
        """
        return self._executor.submit(self.process_pipeline_item, queue_id)

    def get_upload_history(self, search=None, batch=None, status=None, date_filter=None, page=1, per_page=10):
        """
        Queries upload history from MySQL with search, batch, status, date filtering, and pagination.
        """
        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1

        try:
            per_page = max(1, min(100, int(per_page)))
        except (ValueError, TypeError):
            per_page = 10

        query = Upload.query

        # Search filter: matches file_name, original_file_name, or batch_name
        if search:
            s_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Upload.file_name.ilike(s_term),
                    Upload.original_file_name.ilike(s_term),
                    Upload.batch_name.ilike(s_term),
                )
            )

        # Batch filter
        if batch and batch.strip() and batch.strip().lower() != "all":
            b_term = batch.strip()
            if b_term.isdigit():
                query = query.filter(Upload.batch_id == int(b_term))
            else:
                query = query.filter(Upload.batch_name.ilike(b_term))

        # Status filter
        if status and status.strip() and status.strip().lower() != "all":
            st_term = status.strip()
            if st_term.lower() == "uploaded":
                query = query.filter(Upload.status.in_(["Uploaded", "completed"]))
            else:
                query = query.filter(Upload.status.ilike(st_term))

        # Date filter
        if date_filter and date_filter.strip():
            df_str = date_filter.strip()
            try:
                # Matches either upload_date column or date(uploaded_at)
                target_date = datetime.strptime(df_str, "%Y-%m-%d").date()
                query = query.filter(
                    or_(
                        Upload.upload_date == target_date,
                        func.date(Upload.uploaded_at) == target_date,
                    )
                )
            except ValueError:
                pass

        total = query.count()
        pages = max(1, (total + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        items = query.order_by(Upload.id.desc()).offset(offset).limit(per_page).all()

        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "has_next": page < pages,
            "has_prev": page > 1,
        }

    def get_upload_by_id(self, upload_id):
        """Retrieves a single upload history record by ID."""
        try:
            upload_id = int(upload_id)
        except (ValueError, TypeError):
            return None

        record = db.session.get(Upload, upload_id)
        return record.to_dict() if record else None

    def get_dashboard_stats(self):
        """
        Retrieves real MySQL dashboard statistics:
        - Total Recordings
        - Successful Uploads
        - Failed Uploads
        - Pending
        - Unknown Batch
        """
        total_recordings = ProcessingQueue.query.count()
        successful_uploads = Upload.query.filter(Upload.status.in_(["Uploaded", "completed"])).count()
        failed_uploads = ProcessingQueue.query.filter_by(status="Failed").count()
        pending_count = ProcessingQueue.query.filter(ProcessingQueue.status.in_(["Pending", "Stabilizing"])).count()
        unknown_batch_count = ProcessingQueue.query.filter_by(status="Unknown Batch").count()

        return {
            "total_recordings": total_recordings,
            "successful_uploads": successful_uploads,
            "failed_uploads": failed_uploads,
            "pending": pending_count,
            "unknown_batch": unknown_batch_count,
        }


upload_service = UploadService()
