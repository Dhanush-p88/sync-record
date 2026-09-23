"""
Unit Tests for Day 6: Copy/Move Engine
Automated Session Recording Upload System

Test Cases:
1. Test COPY mode:
   - Copies file to destination
   - Original file remains in source folder
   - Destination size matches source
   - Status transitions to 'Uploaded'
   - Upload table record created
2. Test MOVE mode:
   - Moves file to destination
   - Original file removed from source folder
   - Destination file exists and matches size
   - Status transitions to 'Uploaded'
3. Test duplicate target filename:
   - Existing destination file is preserved
   - New file receives '_1' suffix
4. Test missing source file error handling:
   - Fails gracefully with status 'Failed'
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from backend.app import create_app
from backend.models import db, ProcessingQueue, Batch, Setting, Upload
from backend.services.upload_engine import upload_engine_service


class TestUploadEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.service = upload_engine_service
        cls.service.init_app(cls.app)

        cls.test_base = tempfile.mkdtemp(prefix="test_upload_engine_")
        cls.watch_dir = os.path.join(cls.test_base, "watch")
        cls.export_dir = os.path.join(cls.test_base, "exports")
        os.makedirs(cls.watch_dir, exist_ok=True)
        os.makedirs(cls.export_dir, exist_ok=True)

        with cls.app.app_context():
            # Configure upload_root to our test export dir
            root_s = Setting.query.filter_by(key="upload_root").first()
            if not root_s:
                root_s = Setting(key="upload_root", value=cls.export_dir, description="Test export root")
                db.session.add(root_s)
            else:
                root_s.value = cls.export_dir

            # Ensure sample batch Clarity exists with test destination folder
            batch = Batch.query.filter_by(batch_name="Clarity").first()
            cls.batch_dest = os.path.join(cls.export_dir, "Clarity")
            if not batch:
                batch = Batch(
                    batch_name="Clarity",
                    keywords="Clarity, Clarity_Batch",
                    destination_folder=cls.batch_dest,
                    is_enabled=True,
                )
                db.session.add(batch)
            else:
                batch.destination_folder = cls.batch_dest

            db.session.commit()
            cls.batch_id = batch.id

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_base):
            shutil.rmtree(cls.test_base, ignore_errors=True)
        with cls.app.app_context():
            root_s = Setting.query.filter_by(key="upload_root").first()
            if root_s:
                root_s.value = "exports"
            batch = Batch.query.filter_by(batch_name="Clarity").first()
            if batch:
                batch.destination_folder = "exports/Clarity"
            mode_s = Setting.query.filter_by(key="operation_mode").first()
            if mode_s:
                mode_s.value = "COPY"
            db.session.commit()

    def setUp(self):
        self.created_queue_ids = []
        self.created_upload_ids = []

    def tearDown(self):
        with self.app.app_context():
            for q_id in self.created_queue_ids:
                item = db.session.get(ProcessingQueue, q_id)
                if item:
                    db.session.delete(item)
            for u_id in self.created_upload_ids:
                upload = db.session.get(Upload, u_id)
                if upload:
                    db.session.delete(upload)
            db.session.commit()

    def _create_source_file(self, filename, content=b"VIDEO_PAYLOAD_ABC_123"):
        src_path = os.path.join(self.watch_dir, filename)
        with open(src_path, "wb") as f:
            f.write(content)
        return src_path

    def test_copy_mode(self):
        """Test COPY mode: file is copied, original remains in watch folder."""
        with self.app.app_context():
            self.service.set_operation_mode("COPY")

            content = b"COPY_MODE_STREAM_DATA_BYTES"
            src_file = self._create_source_file("Clarity_CopyTest.mp4", content)

            item = ProcessingQueue(
                file_name="Clarity_CopyTest.mp4",
                file_path=src_file,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                standardized_name="Clarity_2026-08-06_10-00-00.mp4",
                validation_status="Valid",
                status="Validated",
                file_size=len(content),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "Uploaded")
            self.assertEqual(res["mode"], "COPY")

            dest_path = res["destination_path"]

            # 1. Verify destination file exists
            self.assertTrue(os.path.exists(dest_path))
            # 2. Verify destination size matches source
            self.assertEqual(os.path.getsize(dest_path), len(content))
            # 3. Verify original file STILL exists in watch folder (COPY mode)
            self.assertTrue(os.path.exists(src_file))

            # 4. Verify database updates
            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertEqual(db_item.status, "Uploaded")
            self.assertIsNotNone(db_item.upload_id)
            self.created_upload_ids.append(db_item.upload_id)

            upload = db.session.get(Upload, db_item.upload_id)
            self.assertIsNotNone(upload)
            self.assertIn(upload.status, ["completed", "Uploaded"])
            self.assertEqual(upload.file_size, len(content))

    def test_move_mode(self):
        """Test MOVE mode: file is moved, original no longer remains in watch folder."""
        with self.app.app_context():
            self.service.set_operation_mode("MOVE")

            content = b"MOVE_MODE_STREAM_DATA_BYTES"
            src_file = self._create_source_file("Clarity_MoveTest.mp4", content)

            item = ProcessingQueue(
                file_name="Clarity_MoveTest.mp4",
                file_path=src_file,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                standardized_name="Clarity_2026-08-06_11-00-00.mp4",
                validation_status="Valid",
                status="Validated",
                file_size=len(content),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "Uploaded")
            self.assertEqual(res["mode"], "MOVE")

            dest_path = res["destination_path"]

            # 1. Verify destination file exists
            self.assertTrue(os.path.exists(dest_path))
            # 2. Verify destination size matches source
            self.assertEqual(os.path.getsize(dest_path), len(content))
            # 3. Verify original file NO LONGER exists in watch folder (MOVE mode)
            self.assertFalse(os.path.exists(src_file))

            # 4. Verify database updates
            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertEqual(db_item.status, "Uploaded")
            self.assertIsNotNone(db_item.upload_id)
            self.created_upload_ids.append(db_item.upload_id)

    def test_duplicate_target_filename_resolution(self):
        """Test duplicate filename collision in destination folder: assigns _1 suffix without overwrite."""
        with self.app.app_context():
            self.service.set_operation_mode("COPY")

            dest_folder = self.batch_dest
            os.makedirs(dest_folder, exist_ok=True)
            existing_target = os.path.join(dest_folder, "Clarity_2026-08-06_12-00-00.mp4")

            # Pre-create conflicting file in destination
            with open(existing_target, "wb") as f:
                f.write(b"ORIGINAL_EXISTING_DESTINATION_FILE")

            new_content = b"NEW_FILE_SAME_STANDARDIZED_NAME"
            src_file = self._create_source_file("Clarity_DupTest.mp4", new_content)

            item = ProcessingQueue(
                file_name="Clarity_DupTest.mp4",
                file_path=src_file,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                standardized_name="Clarity_2026-08-06_12-00-00.mp4",
                validation_status="Valid",
                status="Validated",
                file_size=len(new_content),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "Uploaded")

            # Must have generated _1 suffix
            self.assertEqual(res["standardized_name"], "Clarity_2026-08-06_12-00-00_1.mp4")

            # Both files must exist intact
            self.assertTrue(os.path.exists(existing_target))
            self.assertEqual(os.path.getsize(existing_target), len(b"ORIGINAL_EXISTING_DESTINATION_FILE"))

            new_dest_path = res["destination_path"]
            self.assertTrue(os.path.exists(new_dest_path))
            self.assertEqual(os.path.getsize(new_dest_path), len(new_content))

            if item.upload_id:
                self.created_upload_ids.append(item.upload_id)

    def test_missing_source_file_error(self):
        """Test missing source file fails gracefully."""
        with self.app.app_context():
            non_existent = os.path.join(self.watch_dir, "ghost_recording.mp4")

            item = ProcessingQueue(
                file_name="ghost_recording.mp4",
                file_path=non_existent,
                detected_batch="Clarity",
                batch_id=self.batch_id,
                standardized_name="Clarity_ghost.mp4",
                validation_status="Valid",
                status="Validated",
                file_size=100,
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_item(item)

            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "Failed")
            self.assertIn("Source file missing", res["error"])

            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertEqual(db_item.status, "Failed")
            self.assertIn("Source file missing", db_item.error_message)


if __name__ == "__main__":
    unittest.main()
