"""
File Processor Service - Day 5 Implementation
Automated Session Recording Upload System

Provides:
1. File validation:
   - File exists on disk
   - File is readable
   - File size > 0
   - Supported video extension (.mp4, .avi, .mov, .webm)
   - File stabilized / ready
   - Batch has been identified (not null and not 'Unknown')
2. Standardized filename generation:
   - Format: [BatchName]_[YYYY-MM-DD]_[HH-MM-SS].[extension]
   - Collision resolution with _1, _2, _3 suffixes
3. Updates processing_queue:
   - Original filename
   - Standardized filename
   - Validation status ('Valid', 'Invalid')
4. Structured logging to logs/file_processor.log:
   - Validation started
   - Validation successful
   - Validation failed
   - Filename generated
   - Duplicate filename detected
"""

import os
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from backend.models import db, ProcessingQueue, Batch


SUPPORTED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.webm'}


def _setup_processor_logger():
    """Sets up a dedicated rotating logger for the File Processor service."""
    logger = logging.getLogger("FileProcessor")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        os.makedirs("logs", exist_ok=True)
        log_file = os.path.join("logs", "file_processor.log")

        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [FileProcessor] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [FileProcessor] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


processor_logger = _setup_processor_logger()


class FileProcessorService:
    """Service handling file validation and standardized renaming for recordings."""

    def __init__(self, app=None):
        self.app = app
        self.logger = processor_logger

    def init_app(self, app):
        """Bind service to Flask application instance."""
        self.app = app

    def validate_file(self, item):
        """
        Validates recording item before renaming and further processing.
        
        Checks:
        - File exists on disk
        - File is readable
        - File size > 0
        - Extension is supported (.mp4, .avi, .mov, .webm)
        - File is stable/ready
        - Batch has been identified (not Unknown)

        Returns:
            tuple: (is_valid: bool, reason: str)
        """
        self.logger.info(f"Validation started for file: '{item.file_name}' (Queue ID: {item.id})")

        # 1. Check file path specified
        if not item.file_path:
            msg = "File path is missing or not configured"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 2. Check file exists
        if not os.path.exists(item.file_path):
            msg = f"File does not exist at path: '{item.file_path}'"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 3. Check file is readable
        try:
            with open(item.file_path, "rb") as f:
                _ = f.read(1)
        except (IOError, OSError, PermissionError) as err:
            msg = f"File is locked or not readable: {err}"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 4. Check file size is greater than 0
        try:
            size_on_disk = os.path.getsize(item.file_path)
        except (IOError, OSError) as err:
            msg = f"Cannot read file size: {err}"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        if size_on_disk <= 0:
            msg = f"File size is 0 bytes (Size: {size_on_disk})"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 5. Check supported extension
        _, ext = os.path.splitext(item.file_name)
        ext_lower = ext.lower()
        if ext_lower not in SUPPORTED_EXTENSIONS:
            msg = f"Unsupported file extension '{ext}' (Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 6. Check file stabilization status
        valid_statuses = {"Ready", "Batch Identified", "Validated"}
        if item.status not in valid_statuses and not item.completed_time:
            msg = f"File has not completed stabilization (Current status: '{item.status}')"
            self.logger.warning(f"Validation failed for '{item.file_name}': {msg}")
            return False, msg

        # 7. Check batch has been identified (default to meetings if unknown)
        if not item.detected_batch or item.detected_batch.strip().lower() in {"unknown", ""}:
            item.detected_batch = "meetings"
            self.logger.info(f"Batch defaulted to 'meetings' for file '{item.file_name}'")

        self.logger.info(f"Validation successful for file: '{item.file_name}' (Batch: '{item.detected_batch}', Size: {size_on_disk} bytes)")
        return True, "Validation successful"

    def generate_standardized_filename(self, item):
        """
        Generates standardized filename: [BatchName]_[YYYY-MM-DD]_[HH-MM-SS].[extension]
        
        Preserves original extension.
        Prevents collisions by appending _1, _2, _3 if filename already exists
        in destination or processing queue.

        Returns:
            str: Unique standardized filename.
        """
        batch_name = item.detected_batch or "Batch"
        # Sanitize batch name for filesystem safety (replace spaces/slashes with underscore)
        safe_batch_name = re.sub(r'[^\w\-]', '_', batch_name)

        # Determine reference timestamp (detected_time, completed_time, or current UTC)
        ref_time = item.detected_time or item.completed_time or item.created_at or datetime.now(timezone.utc)
        timestamp_str = ref_time.strftime("%Y-%m-%d_%H-%M-%S")

        # Preserve original extension
        _, ext = os.path.splitext(item.file_name)
        ext = ext if ext else ".mp4"

        base_name = f"{safe_batch_name}_{timestamp_str}"
        candidate_name = f"{base_name}{ext}"

        # Determine destination folder (from batch configuration if available)
        dest_folder = None
        if item.batch_id:
            batch = db.session.get(Batch, item.batch_id)
            if batch and batch.destination_folder:
                dest_folder = batch.destination_folder

        # Check for collisions against existing database entries and destination files
        counter = 1
        collision_detected = False

        while self._is_filename_taken(candidate_name, current_item_id=item.id, dest_folder=dest_folder):
            if not collision_detected:
                self.logger.info(f"Duplicate filename detected: '{candidate_name}' for file '{item.file_name}'")
                collision_detected = True

            candidate_name = f"{base_name}_{counter}{ext}"
            counter += 1

        self.logger.info(f"Filename generated: '{candidate_name}' for original file '{item.file_name}'")
        return candidate_name

    def _is_filename_taken(self, candidate_name, current_item_id=None, dest_folder=None):
        """
        Checks if candidate_name already exists in processing_queue or on disk.
        """
        # 1. Check in database processing_queue
        query = ProcessingQueue.query.filter(
            ProcessingQueue.standardized_name == candidate_name
        )
        if current_item_id:
            query = query.filter(ProcessingQueue.id != current_item_id)
        
        if query.first() is not None:
            return True

        # 2. Check in destination folder if specified and directory exists
        if dest_folder and os.path.exists(dest_folder):
            dest_file_path = os.path.join(dest_folder, candidate_name)
            if os.path.exists(dest_file_path):
                return True

        return False

    def process_item(self, item):
        """
        Validates item and generates standardized filename if valid.
        Updates processing queue record in MySQL.

        Returns:
            dict: Processing result status and metadata.
        """
        is_valid, reason = self.validate_file(item)

        if is_valid:
            std_name = self.generate_standardized_filename(item)
            item.standardized_name = std_name
            item.validation_status = "Valid"
            item.status = "Validated"
            item.error_message = None
            db.session.commit()

            return {
                "success": True,
                "queue_id": item.id,
                "file_name": item.file_name,
                "standardized_name": std_name,
                "validation_status": "Valid",
                "status": "Validated",
                "message": "File validated and standardized filename generated"
            }
        else:
            item.validation_status = "Invalid"
            if item.status != "Unknown Batch":
                item.status = "Validation Failed"
            item.error_message = reason
            # Do NOT generate standard batch filename
            item.standardized_name = None
            db.session.commit()

            return {
                "success": False,
                "queue_id": item.id,
                "file_name": item.file_name,
                "standardized_name": None,
                "validation_status": "Invalid",
                "status": item.status,
                "message": reason
            }

    def process_all_ready_items(self):
        """
        Finds all items in 'Batch Identified' status and processes them.
        Returns list of processed result dicts.
        """
        items = ProcessingQueue.query.filter(
            ProcessingQueue.status == "Batch Identified"
        ).order_by(ProcessingQueue.priority.desc(), ProcessingQueue.id.asc()).all()

        results = []
        for item in items:
            res = self.process_item(item)
            results.append(res)
        return results


file_processor_service = FileProcessorService()
