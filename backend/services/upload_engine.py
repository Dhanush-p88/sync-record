"""
Upload Engine Service - Day 6 Implementation
Automated Session Recording Upload System

Provides:
1. COPY and MOVE operation modes from MySQL Settings:
   - COPY: Copies file to [Upload Root]/[Batch Name]/, original remains in Watch Folder.
   - MOVE: Moves file to [Upload Root]/[Batch Name]/, original is removed from Watch Folder.
2. Automatic destination directory creation if missing.
3. Collision prevention: NEVER overwrites an existing file. Resolves duplicates with _1, _2, etc.
4. Post-transfer verification:
   - Verifies destination file exists on disk.
   - Verifies destination file size matches the source.
   - Updates processing_queue.status to 'Uploaded' on success.
   - Creates/updates record in uploads table.
5. Error handling:
   - Permission denied / locked files
   - Missing source files
   - Insufficient disk space
   - Destination unavailable
6. Retries temporary failures up to 3 times.
7. Dedicated structured logging to logs/upload_engine.log:
   - Copy started
   - Copy completed
   - Move started
   - Move completed
   - Destination created
   - Duplicate detected
   - Verification successful
   - Operation failed
"""

import os
import re
import time
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from backend.models import db, ProcessingQueue, Batch, Setting, Upload


def _setup_upload_logger():
    """Sets up a dedicated rotating logger for the Upload Engine service."""
    logger = logging.getLogger("UploadEngine")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        os.makedirs("logs", exist_ok=True)
        log_file = os.path.join("logs", "upload_engine.log")

        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [UploadEngine] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [UploadEngine] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


upload_logger = _setup_upload_logger()


class UploadEngineService:
    """Service handling file copy/move operations and destination management."""

    def __init__(self, app=None):
        self.app = app
        self.logger = upload_logger

    def init_app(self, app):
        """Bind service to Flask application instance."""
        self.app = app

    def get_operation_mode(self):
        """
        Reads operation mode from Settings table in MySQL.
        Returns: 'COPY' or 'MOVE' (default: 'COPY').
        """
        try:
            setting = Setting.query.filter_by(key="operation_mode").first()
            if setting and setting.value:
                mode = setting.value.strip().upper()
                if mode in {"COPY", "MOVE"}:
                    return mode
        except Exception as exc:
            self.logger.warning(f"Could not read operation_mode setting: {exc}")
        return "COPY"

    def set_operation_mode(self, mode):
        """
        Updates operation mode in Settings table.
        Args:
            mode (str): 'COPY' or 'MOVE'.
        """
        clean_mode = mode.strip().upper()
        if clean_mode not in {"COPY", "MOVE"}:
            raise ValueError(f"Invalid operation mode: {mode}. Must be 'COPY' or 'MOVE'.")

        setting = Setting.query.filter_by(key="operation_mode").first()
        if not setting:
            setting = Setting(
                key="operation_mode",
                value=clean_mode,
                description="Recording upload operation mode: COPY or MOVE"
            )
            db.session.add(setting)
        else:
            setting.value = clean_mode

        db.session.commit()
        self.logger.info(f"Operation mode updated to: {clean_mode}")
        return clean_mode

    def get_upload_root(self):
        """
        Reads upload root directory from Settings table or defaults to 'exports'.
        """
        try:
            setting = Setting.query.filter_by(key="upload_root").first()
            if setting and setting.value:
                return setting.value.strip()
        except Exception:
            pass
        return "exports"

    def resolve_destination_folder(self, item):
        """
        Resolves destination folder for recording: [Upload Root]/[Batch Name]/
        Creates folder if it does not exist.
        """
        batch_name = item.detected_batch or "Unknown"
        safe_batch_name = re.sub(r'[^\w\-]', '_', batch_name)

        dest_folder = None
        if item.batch_id:
            batch = db.session.get(Batch, item.batch_id)
            if batch and batch.destination_folder:
                dest_folder = batch.destination_folder

        if not dest_folder:
            upload_root = self.get_upload_root()
            dest_folder = os.path.join(upload_root, safe_batch_name)

        # Automatically create destination folder if it doesn't exist
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder, exist_ok=True)
            self.logger.info(f"Destination created: '{dest_folder}'")

        return dest_folder

    def resolve_non_colliding_target(self, dest_folder, preferred_filename):
        """
        Ensures target file does not collide with existing file in destination.
        Appends _1, _2, _3 if candidate exists.

        Returns:
            tuple: (final_filename: str, full_dest_path: str)
        """
        base, ext = os.path.splitext(preferred_filename)
        candidate_filename = preferred_filename
        full_dest_path = os.path.join(dest_folder, candidate_filename)

        counter = 1
        while os.path.exists(full_dest_path):
            self.logger.info(f"Duplicate detected: '{candidate_filename}' already exists in '{dest_folder}'")
            candidate_filename = f"{base}_{counter}{ext}"
            full_dest_path = os.path.join(dest_folder, candidate_filename)
            counter += 1

        return candidate_filename, full_dest_path

    def process_item(self, item, max_retries=3):
        """
        Transfers validated recording to destination using COPY or MOVE mode.
        Verifies transfer, updates queue status, records upload, and handles retries.

        Returns:
            dict: Result of transfer operation.
        """
        src_path = item.file_path
        preferred_name = item.standardized_name or item.file_name

        mode = self.get_operation_mode()

        for attempt in range(1, max_retries + 1):
            item.attempts = (item.attempts or 0) + 1

            # 1. Source existence check
            if not src_path or not os.path.exists(src_path):
                msg = f"Source file missing: '{src_path}'"
                self.logger.error(f"Operation failed for '{item.file_name}': {msg}")
                item.status = "Failed"
                item.error_message = msg
                db.session.commit()
                return {"success": False, "status": "Failed", "error": msg}

            # 2. Source size & readability check
            try:
                src_size = os.path.getsize(src_path)
                with open(src_path, "rb") as f:
                    _ = f.read(1)
            except (IOError, OSError, PermissionError) as err:
                msg = f"File locked or permission denied: {err}"
                if attempt < max_retries:
                    self.logger.warning(f"Attempt {attempt}/{max_retries} failed for '{item.file_name}': {msg}. Retrying in 1s...")
                    time.sleep(1.0)
                    continue
                else:
                    self.logger.error(f"Operation failed for '{item.file_name}': {msg}")
                    item.status = "Failed"
                    item.error_message = msg
                    db.session.commit()
                    return {"success": False, "status": "Failed", "error": msg}

            # 3. Resolve destination folder
            try:
                dest_folder = self.resolve_destination_folder(item)
            except Exception as err:
                msg = f"Destination unavailable: {err}"
                self.logger.error(f"Operation failed for '{item.file_name}': {msg}")
                item.status = "Failed"
                item.error_message = msg
                db.session.commit()
                return {"success": False, "status": "Failed", "error": msg}

            # 4. Check available disk space
            try:
                usage = shutil.disk_usage(dest_folder)
                if usage.free < (src_size + 1024 * 1024):  # 1MB buffer
                    msg = f"Insufficient disk space in '{dest_folder}'. Free: {usage.free} bytes, Required: {src_size} bytes"
                    self.logger.error(f"Operation failed for '{item.file_name}': {msg}")
                    item.status = "Failed"
                    item.error_message = msg
                    db.session.commit()
                    return {"success": False, "status": "Failed", "error": msg}
            except Exception:
                pass

            # 5. Resolve target filename (preventing overwrite)
            final_filename, dest_path = self.resolve_non_colliding_target(dest_folder, preferred_name)

            # 6. Execute transfer (COPY or MOVE)
            try:
                if mode == "COPY":
                    self.logger.info(f"Copy started for '{item.file_name}' to '{dest_path}'")
                    shutil.copy2(src_path, dest_path)
                    self.logger.info(f"Copy completed for '{item.file_name}' to '{dest_path}'")
                else:  # MOVE mode
                    self.logger.info(f"Move started for '{item.file_name}' to '{dest_path}'")
                    shutil.move(src_path, dest_path)
                    self.logger.info(f"Move completed for '{item.file_name}' to '{dest_path}'")

                # 7. Verification: check destination exists and size matches
                if not os.path.exists(dest_path):
                    raise IOError(f"Destination file '{dest_path}' does not exist after transfer")

                dest_size = os.path.getsize(dest_path)
                if dest_size != src_size:
                    raise IOError(f"Size mismatch: Source was {src_size} bytes, destination is {dest_size} bytes")

                self.logger.info(f"Verification successful for '{final_filename}' (Size: {dest_size} bytes)")

                # 8. Record in Uploads table and update ProcessingQueue
                now_utc = datetime.now(timezone.utc)
                _, file_ext = os.path.splitext(final_filename)

                # Compute checksum if helper available
                checksum_val = None
                try:
                    from backend.services.upload_service import calculate_sha256
                    checksum_val = calculate_sha256(dest_path)
                except Exception:
                    pass

                upload_record = Upload(
                    batch_id=item.batch_id,
                    batch_name=item.detected_batch,
                    original_file_name=item.file_name,
                    original_file_path=src_path,
                    file_name=final_filename,
                    file_path=dest_path,
                    file_size=dest_size,
                    file_extension=file_ext.lower() if file_ext else None,
                    upload_date=now_utc.date(),
                    upload_time=now_utc.strftime("%H:%M:%S"),
                    checksum=checksum_val,
                    status="Uploaded",
                    error_message=None,
                    uploaded_at=now_utc
                )
                db.session.add(upload_record)
                db.session.flush()

                item.upload_id = upload_record.id
                item.standardized_name = final_filename
                item.status = "Uploaded"
                item.error_message = None
                item.completed_time = now_utc
                db.session.commit()

                # 9. Auto-sync directly to Google Drive Desktop target folder
                try:
                    from backend.services.cloud_sync_service import cloud_sync_service
                    from backend.models import Setting
                    dest_gdrive = r"G:\My Drive\meetings"
                    try:
                        s_dest = Setting.query.filter_by(key="gdrive_destination_folder").first()
                        if s_dest and s_dest.value and s_dest.value.strip():
                            dest_gdrive = s_dest.value.strip()
                    except Exception:
                        pass
                    cloud_sync_service.auto_export_to_gdrive(dest_path, dest_gdrive)
                except Exception as gd_err:
                    self.logger.warning(f"Google Drive auto-sync note: {gd_err}")

                return {
                    "success": True,
                    "queue_id": item.id,
                    "upload_id": upload_record.id,
                    "mode": mode,
                    "file_name": item.file_name,
                    "standardized_name": final_filename,
                    "destination_path": dest_path,
                    "file_size": dest_size,
                    "status": "Uploaded"
                }

            except Exception as transfer_err:
                msg = f"Transfer failed ({mode}): {transfer_err}"
                if attempt < max_retries:
                    self.logger.warning(f"Attempt {attempt}/{max_retries} failed for '{item.file_name}': {msg}. Retrying...")
                    time.sleep(1.0)
                    continue
                else:
                    self.logger.error(f"Operation failed for '{item.file_name}': {msg}")
                    item.status = "Failed"
                    item.error_message = msg
                    db.session.commit()
                    return {"success": False, "status": "Failed", "error": msg}

        return {"success": False, "status": "Failed", "error": "Exceeded maximum retry attempts"}

    def process_all_validated_items(self):
        """Processes all items currently in 'Validated' status."""
        items = ProcessingQueue.query.filter_by(status="Validated").all()
        results = []
        for item in items:
            res = self.process_item(item)
            results.append(res)
        return results


upload_engine_service = UploadEngineService()
