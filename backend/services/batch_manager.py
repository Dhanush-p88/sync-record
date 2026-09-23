import os
import re
import fnmatch
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from backend.config import Config
from backend.models import db, Batch, ProcessingQueue

# Dedicated logger for Batch Manager
logger = logging.getLogger("batch_manager")
logger.setLevel(logging.INFO)
logger.propagate = False

os.makedirs(Config.LOGS_DIR, exist_ok=True)
log_file_path = os.path.join(Config.LOGS_DIR, "batch_manager.log")

if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [BatchManager] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers):
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [BatchManager] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)


class BatchManagerService:
    """Service to identify and map recordings to configured batches."""

    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        """Bind Flask app instance."""
        self.app = app

    def identify_batch(self, filename):
        """
        Identifies the best matching batch for a given recording filename.
        Matching is case-insensitive and prioritizes the most specific match (longest match).
        Returns: (batch_id, batch_name) or (None, 'Unknown')
        """
        if not filename:
            return None, "Unknown"

        # Remove file extension for cleaner matching
        base_name, _ = os.path.splitext(filename)
        filename_lower = filename.lower()
        base_name_lower = base_name.lower()

        # Tokenize by common delimiters (_ - . space)
        tokens = [t.lower() for t in re.split(r'[_.\s\-]+', base_name) if t]

        try:
            enabled_batches = Batch.query.filter_by(is_enabled=True).all()
        except Exception as exc:
            logger.error(f"Error querying batches: {exc}")
            return None, "Unknown"

        best_match = None
        highest_score = -1

        for batch in enabled_batches:
            patterns = []
            # Always include the batch name itself
            if batch.batch_name:
                patterns.append(batch.batch_name.strip())

            # Parse configured keywords/patterns
            if batch.keywords:
                for kw in re.split(r'[,;\n]+', batch.keywords):
                    clean_kw = kw.strip()
                    if clean_kw and clean_kw not in patterns:
                        patterns.append(clean_kw)

            for pattern in patterns:
                pat_lower = pattern.lower()
                matched = False
                score = 0

                # 1. Exact token match or substring in tokens
                if pat_lower in tokens:
                    matched = True
                    # Token match gets high priority plus pattern length
                    score = 100 + len(pat_lower)
                # 2. Substring match in base_name
                elif pat_lower in base_name_lower or pat_lower in filename_lower:
                    matched = True
                    score = len(pat_lower)
                # 3. Wildcard / Glob pattern match
                elif '*' in pat_lower or '?' in pat_lower:
                    glob_pat = pat_lower if pat_lower.startswith('*') else f"*{pat_lower}*"
                    if fnmatch.fnmatch(filename_lower, glob_pat) or fnmatch.fnmatch(base_name_lower, glob_pat):
                        matched = True
                        score = len(pat_lower.replace('*', '').replace('?', ''))

                if matched and score > highest_score:
                    highest_score = score
                    best_match = batch

        if best_match:
            logger.info(f"Batch detected: '{best_match.batch_name}' for file '{filename}'")
            return best_match.id, best_match.batch_name
        else:
            # Fallback to 'meetings' batch so no recording is rejected
            meetings_batch = Batch.query.filter(Batch.batch_name.ilike("meetings"), Batch.is_enabled == True).first()
            if meetings_batch:
                logger.info(f"Batch defaulted to '{meetings_batch.batch_name}' for file '{filename}'")
                return meetings_batch.id, meetings_batch.batch_name
            logger.info(f"No specific batch matched for '{filename}', defaulting to 'meetings'")
            return None, "meetings"

    def process_item(self, item):
        """
        Identifies batch for a ProcessingQueue item and updates status to
        'Batch Identified' or 'Unknown Batch'.
        """
        filename = item.file_name or os.path.basename(item.file_path)
        batch_id, batch_name = self.identify_batch(filename)

        if batch_id:
            item.batch_id = batch_id
            item.detected_batch = batch_name
            item.status = "Batch Identified"
            item.updated_at = datetime.now(timezone.utc)

            # Update batch total_files counter if present
            try:
                batch = Batch.query.get(batch_id)
                if batch:
                    batch.total_files = ProcessingQueue.query.filter_by(batch_id=batch_id).count() + 1
            except Exception:
                pass
        else:
            item.batch_id = None
            item.detected_batch = "Unknown"
            item.status = "Unknown Batch"
            item.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        # DAY 5: Trigger file validation & standardized renaming if file exists on disk
        if item.file_path and os.path.exists(item.file_path):
            try:
                from backend.services.file_processor import file_processor_service
                proc_res = file_processor_service.process_item(item)

                # DAY 6: Trigger Copy/Move upload engine if file is validated
                if proc_res.get("success") and item.status == "Validated":
                    from backend.services.upload_engine import upload_engine_service
                    upload_engine_service.process_item(item)
            except Exception as proc_err:
                self.logger.error(f"Error during file processing/upload for '{filename}': {proc_err}")

        return item

    def process_ready_queue_items(self):
        """Processes all items currently in 'Ready' status."""
        if not self.app:
            return []

        with self.app.app_context():
            ready_items = ProcessingQueue.query.filter_by(status="Ready").all()
            processed = []
            for item in ready_items:
                self.process_item(item)
                processed.append(item.to_dict())
            return processed

    # CRUD Operations for Batch Mappings
    def get_all_batches(self):
        """Returns all configured batches."""
        batches = Batch.query.order_by(Batch.id.asc()).all()
        return [b.to_dict() for b in batches]

    def get_batch(self, batch_id):
        """Returns a single batch by ID."""
        batch = Batch.query.get(batch_id)
        return batch.to_dict() if batch else None

    def create_batch(self, data):
        """Creates a new batch mapping."""
        batch_name = data.get("batch_name", "").strip()
        if not batch_name:
            raise ValueError("Batch name is required")

        # Prevent duplicate batch names
        existing = Batch.query.filter_by(batch_name=batch_name).first()
        if existing:
            raise ValueError(f"Batch with name '{batch_name}' already exists")

        batch = Batch(
            batch_name=batch_name,
            keywords=data.get("keywords", "").strip(),
            destination_folder=data.get("destination_folder", "").strip() or f"exports/{batch_name}",
            is_enabled=bool(data.get("is_enabled", True)),
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.session.add(batch)
        db.session.commit()

        logger.info(f"Batch mapping created: '{batch.batch_name}' (Keywords: '{batch.keywords}', Dest: '{batch.destination_folder}')")
        return batch.to_dict()

    def update_batch(self, batch_id, data):
        """Updates an existing batch mapping."""
        batch = Batch.query.get(batch_id)
        if not batch:
            return None

        if "batch_name" in data:
            new_name = data["batch_name"].strip()
            if not new_name:
                raise ValueError("Batch name cannot be empty")
            # Check for conflict with other batches
            existing = Batch.query.filter(Batch.batch_name == new_name, Batch.id != batch_id).first()
            if existing:
                raise ValueError(f"Another batch with name '{new_name}' already exists")
            batch.batch_name = new_name

        if "keywords" in data:
            batch.keywords = data["keywords"].strip()

        if "destination_folder" in data:
            batch.destination_folder = data["destination_folder"].strip()

        if "is_enabled" in data:
            batch.is_enabled = bool(data["is_enabled"])

        if "status" in data:
            batch.status = data["status"]

        batch.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(f"Batch mapping updated: '{batch.batch_name}' (ID: {batch_id})")
        return batch.to_dict()

    def delete_batch(self, batch_id):
        """Deletes a batch mapping."""
        batch = Batch.query.get(batch_id)
        if not batch:
            return False

        name = batch.batch_name
        db.session.delete(batch)
        db.session.commit()

        logger.info(f"Batch mapping deleted: ID {batch_id} ('{name}')")
        return True


# Singleton instance
batch_manager_service = BatchManagerService()
