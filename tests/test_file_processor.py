"""
Unit Tests for Day 5: File Validation & Standardized Renaming
Automated Session Recording Upload System

Test Cases:
1. Valid MP4 file -> Validation successful -> Standard filename generated: [Batch]_[YYYY-MM-DD]_[HH-MM-SS].mp4
2. Unsupported .txt file -> Validation failed
3. Empty file (0 bytes) -> Validation failed
4. Duplicate target filename -> Generate _1, _2, etc.
5. Unknown batch -> Do not generate a normal batch filename
"""

import os
import unittest
import tempfile
import shutil
from datetime import datetime, timezone

from backend.app import create_app
from backend.models import db, ProcessingQueue, Batch
from backend.services.file_processor import file_processor_service, FileProcessorService


class TestFileProcessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.test_dir = tempfile.mkdtemp(prefix="test_processor_")
        cls.service = file_processor_service
        cls.service.init_app(cls.app)

        with cls.app.app_context():
            # Ensure sample batch Clarity exists
            batch = Batch.query.filter_by(batch_name="Clarity").first()
            if not batch:
                batch = Batch(
                    batch_name="Clarity",
                    keywords="Clarity, Clarity_Batch",
                    destination_folder="exports/Clarity",
                    is_enabled=True,
                )
                db.session.add(batch)
                db.session.commit()
            cls.batch_id = batch.id

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.created_files = []
        self.created_queue_ids = []

    def tearDown(self):
        # Cleanup files on disk
        for path in self.created_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        # Cleanup DB queue entries
        with self.app.app_context():
            for q_id in self.created_queue_ids:
                item = db.session.get(ProcessingQueue, q_id)
                if item:
                    db.session.delete(item)
            db.session.commit()

    def _create_temp_file(self, filename, content=b"SAMPLE_VIDEO_DATA_STREAM_123"):
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        self.created_files.append(filepath)
        return filepath

    def test_case_1_valid_mp4_file(self):
        """Case 1: Valid MP4 file -> Validation successful -> Standard filename generated."""
        filepath = self._create_temp_file("Clarity_Session_01.mp4", b"VALID_VIDEO_CONTENT")

        fixed_time = datetime(2026, 8, 6, 14, 35, 22, tzinfo=timezone.utc)

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="Clarity_Session_01.mp4",
                file_path=filepath,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=len(b"VALID_VIDEO_CONTENT"),
                detected_time=fixed_time,
                completed_time=fixed_time,
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertTrue(res["success"])
            self.assertEqual(res["validation_status"], "Valid")
            self.assertEqual(res["status"], "Validated")
            self.assertIsNotNone(res["standardized_name"])
            self.assertEqual(res["standardized_name"], "Clarity_2026-08-06_14-35-22.mp4")

            # Check item updated in DB
            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertEqual(db_item.standardized_name, "Clarity_2026-08-06_14-35-22.mp4")
            self.assertEqual(db_item.validation_status, "Valid")
            self.assertEqual(db_item.status, "Validated")

    def test_case_2_unsupported_extension(self):
        """Case 2: Unsupported .txt file -> Validation failed/skipped."""
        filepath = self._create_temp_file("notes.txt", b"SOME_TEXT_CONTENT")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="notes.txt",
                file_path=filepath,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=len(b"SOME_TEXT_CONTENT"),
                completed_time=datetime.now(timezone.utc),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertFalse(res["success"])
            self.assertEqual(res["validation_status"], "Invalid")
            self.assertIsNone(res["standardized_name"])
            self.assertIn("Unsupported file extension", res["message"])

            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertIsNone(db_item.standardized_name)
            self.assertEqual(db_item.validation_status, "Invalid")
            self.assertEqual(db_item.status, "Validation Failed")

    def test_case_3_empty_file(self):
        """Case 3: Empty file (0 bytes) -> Validation failed."""
        filepath = self._create_temp_file("empty_recording.mp4", b"")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="empty_recording.mp4",
                file_path=filepath,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=0,
                completed_time=datetime.now(timezone.utc),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertFalse(res["success"])
            self.assertEqual(res["validation_status"], "Invalid")
            self.assertIsNone(res["standardized_name"])
            self.assertIn("0 bytes", res["message"])

            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertIsNone(db_item.standardized_name)
            self.assertEqual(db_item.validation_status, "Invalid")
            self.assertEqual(db_item.status, "Validation Failed")

    def test_case_4_duplicate_target_filename(self):
        """Case 4: Duplicate target filename -> Generate _1, _2, etc."""
        fixed_time = datetime(2026, 8, 6, 14, 35, 22, tzinfo=timezone.utc)

        file1 = self._create_temp_file("Clarity_Batch_A.mp4", b"DATA_A")
        file2 = self._create_temp_file("Clarity_Batch_B.mp4", b"DATA_B")
        file3 = self._create_temp_file("Clarity_Batch_C.mp4", b"DATA_C")

        with self.app.app_context():
            # First item
            item1 = ProcessingQueue(
                file_name="Clarity_Batch_A.mp4",
                file_path=file1,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=len(b"DATA_A"),
                detected_time=fixed_time,
                completed_time=fixed_time,
            )
            db.session.add(item1)
            db.session.commit()
            self.created_queue_ids.append(item1.id)

            res1 = self.service.process_item(item1)
            self.assertEqual(res1["standardized_name"], "Clarity_2026-08-06_14-35-22.mp4")

            # Second item with identical timestamp and batch -> collision!
            item2 = ProcessingQueue(
                file_name="Clarity_Batch_B.mp4",
                file_path=file2,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=len(b"DATA_B"),
                detected_time=fixed_time,
                completed_time=fixed_time,
            )
            db.session.add(item2)
            db.session.commit()
            self.created_queue_ids.append(item2.id)

            res2 = self.service.process_item(item2)
            self.assertEqual(res2["standardized_name"], "Clarity_2026-08-06_14-35-22_1.mp4")

            # Third item with identical timestamp and batch -> next collision!
            item3 = ProcessingQueue(
                file_name="Clarity_Batch_C.mp4",
                file_path=file3,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=len(b"DATA_C"),
                detected_time=fixed_time,
                completed_time=fixed_time,
            )
            db.session.add(item3)
            db.session.commit()
            self.created_queue_ids.append(item3.id)

            res3 = self.service.process_item(item3)
            self.assertEqual(res3["standardized_name"], "Clarity_2026-08-06_14-35-22_2.mp4")

    def test_case_5_unknown_batch(self):
        """Case 5: Unknown batch -> Do not generate a normal batch filename."""
        filepath = self._create_temp_file("Random_Recording.mp4", b"RANDOM_DATA")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="Random_Recording.mp4",
                file_path=filepath,
                detected_batch="Unknown",
                batch_id=None,
                status="Unknown Batch",
                file_size=len(b"RANDOM_DATA"),
                completed_time=datetime.now(timezone.utc),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertFalse(res["success"])
            self.assertEqual(res["validation_status"], "Invalid")
            self.assertIsNone(res["standardized_name"])
            self.assertEqual(res["status"], "Unknown Batch")

            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertIsNone(db_item.standardized_name)
            self.assertEqual(db_item.validation_status, "Invalid")
            self.assertEqual(db_item.status, "Unknown Batch")

    def test_file_does_not_exist(self):
        """Edge Case: File does not exist on disk -> Validation failed."""
        with self.app.app_context():
            item = ProcessingQueue(
                file_name="ghost.mp4",
                file_path=os.path.join(self.test_dir, "ghost.mp4"),
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Batch Identified",
                file_size=100,
                completed_time=datetime.now(timezone.utc),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertFalse(res["success"])
            self.assertEqual(res["validation_status"], "Invalid")
            self.assertIn("does not exist", res["message"])


if __name__ == "__main__":
    unittest.main()
