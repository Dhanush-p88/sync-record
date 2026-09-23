"""
Unit Tests for Day 7: Upload History & Complete Pipeline
Automated Session Recording Upload System

Test Cases:
1. Complete pipeline execution from queue item to MySQL Upload record.
2. Search filtering by filename and batch name.
3. Batch filtering.
4. Status filtering (Uploaded vs Failed).
5. Date filtering.
6. Server-side pagination.
7. Single upload detail lookup by ID.
8. Dashboard statistics aggregation from real MySQL data.
9. Failure recording and error handling.
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, date

from backend.app import create_app
from backend.models import db, ProcessingQueue, Batch, Setting, Upload
from backend.services.upload_service import upload_service


class TestUploadService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.service = upload_service
        cls.service.init_app(cls.app)

        cls.test_base = tempfile.mkdtemp(prefix="test_upload_service_")
        cls.watch_dir = os.path.join(cls.test_base, "watch")
        cls.export_dir = os.path.join(cls.test_base, "exports")
        os.makedirs(cls.watch_dir, exist_ok=True)
        os.makedirs(cls.export_dir, exist_ok=True)

        with cls.app.app_context():
            # Set upload root to test exports dir
            root_s = Setting.query.filter_by(key="upload_root").first()
            if not root_s:
                root_s = Setting(key="upload_root", value=cls.export_dir, description="Test export root")
                db.session.add(root_s)
            else:
                root_s.value = cls.export_dir

            # Ensure Clarity batch
            cls.clarity_dest = os.path.join(cls.export_dir, "Clarity")
            os.makedirs(cls.clarity_dest, exist_ok=True)
            batch = Batch.query.filter_by(batch_name="Clarity").first()
            if not batch:
                batch = Batch(
                    batch_name="Clarity",
                    keywords="Clarity, Clarity_Batch",
                    destination_folder=cls.clarity_dest,
                    is_enabled=True,
                )
                db.session.add(batch)
            else:
                batch.destination_folder = cls.clarity_dest

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

    def _create_source_file(self, filename, content=b"VIDEO_PAYLOAD_TEST_DATA_777"):
        src_path = os.path.join(self.watch_dir, filename)
        with open(src_path, "wb") as f:
            f.write(content)
        return src_path

    def test_complete_pipeline_flow(self):
        """Test full pipeline: Ready queue item -> Process -> MySQL Upload record with all Day 7 fields."""
        with self.app.app_context():
            content = b"DAY7_PIPELINE_COMPLETE_STREAM"
            src_file = self._create_source_file("Clarity_Batch_Session1.mp4", content)

            item = ProcessingQueue(
                file_name="Clarity_Batch_Session1.mp4",
                file_path=src_file,
                detected_batch=None,
                batch_id=None,
                status="Ready",
                file_size=len(content),
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            res = self.service.process_pipeline_item(item.id)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "Uploaded")
            self.assertEqual(res["batch"], "Clarity")

            # Verify queue item status
            db.session.commit()
            db_item = db.session.get(ProcessingQueue, item.id)
            self.assertEqual(db_item.status, "Uploaded")
            self.assertIsNotNone(db_item.upload_id)
            self.created_upload_ids.append(db_item.upload_id)

            # Verify Upload record in MySQL
            upload = db.session.get(Upload, db_item.upload_id)
            self.assertIsNotNone(upload)
            self.assertEqual(upload.batch_name, "Clarity")
            self.assertEqual(upload.original_file_name, "Clarity_Batch_Session1.mp4")
            self.assertEqual(upload.file_size, len(content))
            self.assertEqual(upload.file_extension, ".mp4")
            self.assertIsNotNone(upload.checksum)
            self.assertEqual(len(upload.checksum), 64)  # Valid SHA-256
            self.assertIsNotNone(upload.upload_date)
            self.assertIsNotNone(upload.upload_time)
            self.assertTrue(os.path.exists(upload.file_path))

    def test_history_search_and_filters(self):
        """Test get_upload_history with search, batch, status, and date filters."""
        with self.app.app_context():
            today = date.today()
            u1 = Upload(
                batch_id=self.batch_id,
                batch_name="Clarity",
                original_file_name="Clarity_Intro.mp4",
                file_name="Clarity_2026-09-02_10-00-00.mp4",
                file_path="/exports/Clarity/1.mp4",
                file_size=1024,
                file_extension=".mp4",
                upload_date=today,
                upload_time="10:00:00",
                status="Uploaded",
            )
            u2 = Upload(
                batch_id=None,
                batch_name="Python-10",
                original_file_name="Python_Session.mp4",
                file_name="Python-10_2026-09-02_11-00-00.mp4",
                file_path="/exports/Python-10/2.mp4",
                file_size=2048,
                file_extension=".mp4",
                upload_date=today,
                upload_time="11:00:00",
                status="Uploaded",
            )
            u3 = Upload(
                batch_id=self.batch_id,
                batch_name="Clarity",
                original_file_name="Clarity_Corrupt.mp4",
                file_name="Clarity_Corrupt.mp4",
                file_path="",
                file_size=0,
                file_extension=".mp4",
                upload_date=today,
                upload_time="12:00:00",
                status="Failed",
                error_message="Corrupted video file",
            )
            db.session.add_all([u1, u2, u3])
            db.session.commit()
            self.created_upload_ids.extend([u1.id, u2.id, u3.id])

            # 1. Search by filename
            res_search = self.service.get_upload_history(search="Intro")
            self.assertEqual(res_search["total"], 1)
            self.assertEqual(res_search["items"][0]["original_file_name"], "Clarity_Intro.mp4")

            # 2. Filter by batch
            res_batch = self.service.get_upload_history(batch="Python-10")
            self.assertGreaterEqual(res_batch["total"], 1)
            self.assertTrue(all(it["batch_name"] == "Python-10" for it in res_batch["items"]))

            # 3. Filter by status
            res_status = self.service.get_upload_history(status="Failed")
            self.assertGreaterEqual(res_status["total"], 1)
            self.assertTrue(all(it["status"] == "Failed" for it in res_status["items"]))

            # 4. Filter by date
            res_date = self.service.get_upload_history(date_filter=today.isoformat())
            self.assertGreaterEqual(res_date["total"], 3)

    def test_pagination(self):
        """Test server-side pagination with page and per_page."""
        with self.app.app_context():
            today = date.today()
            uploads = []
            for i in range(15):
                u = Upload(
                    batch_name="Clarity",
                    file_name=f"Clarity_PageTest_{i}.mp4",
                    file_path=f"/exports/Clarity/{i}.mp4",
                    file_size=100,
                    upload_date=today,
                    status="Uploaded",
                )
                uploads.append(u)
            db.session.add_all(uploads)
            db.session.commit()
            for u in uploads:
                self.created_upload_ids.append(u.id)

            # Page 1, 5 per page
            p1 = self.service.get_upload_history(page=1, per_page=5)
            self.assertEqual(len(p1["items"]), 5)
            self.assertEqual(p1["page"], 1)
            self.assertGreaterEqual(p1["total"], 15)
            self.assertTrue(p1["has_next"])

            # Page 2, 5 per page
            p2 = self.service.get_upload_history(page=2, per_page=5)
            self.assertEqual(len(p2["items"]), 5)
            self.assertEqual(p2["page"], 2)
            self.assertTrue(p2["has_prev"])

    def test_get_upload_by_id(self):
        """Test single upload detail lookup."""
        with self.app.app_context():
            u = Upload(
                batch_name="Clarity",
                original_file_name="Clarity_DetailTest.mp4",
                file_name="Clarity_2026-09-02_15-00-00.mp4",
                file_path="/exports/Clarity/det.mp4",
                file_size=500,
                file_extension=".mp4",
                checksum="abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                status="Uploaded",
            )
            db.session.add(u)
            db.session.commit()
            self.created_upload_ids.append(u.id)

            detail = self.service.get_upload_by_id(u.id)
            self.assertIsNotNone(detail)
            self.assertEqual(detail["id"], u.id)
            self.assertEqual(detail["checksum"], u.checksum)
            self.assertEqual(detail["status"], "Uploaded")

            # Non-existent ID
            missing = self.service.get_upload_by_id(999999)
            self.assertIsNone(missing)

    def test_dashboard_stats(self):
        """Test real MySQL dashboard statistics aggregation."""
        with self.app.app_context():
            stats = self.service.get_dashboard_stats()
            self.assertIn("total_recordings", stats)
            self.assertIn("successful_uploads", stats)
            self.assertIn("failed_uploads", stats)
            self.assertIn("pending", stats)
            self.assertIn("unknown_batch", stats)
            self.assertIsInstance(stats["total_recordings"], int)
            self.assertIsInstance(stats["successful_uploads"], int)

    def test_failure_handling(self):
        """Test failure recording sets status to Failed and creates error record."""
        with self.app.app_context():
            item = ProcessingQueue(
                file_name="Failed_Recording.mp4",
                file_path="/non/existent/path/fail.mp4",
                detected_batch="Clarity",
                batch_id=self.batch_id,
                status="Validated",
                file_size=10,
            )
            db.session.add(item)
            db.session.commit()
            self.created_queue_ids.append(item.id)

            upload_rec = self.service.record_upload_failure(item, "Simulated disk error")

            self.assertEqual(item.status, "Failed")
            self.assertIn("Simulated disk error", item.error_message)
            if upload_rec:
                self.created_upload_ids.append(upload_rec.id)
                self.assertEqual(upload_rec.status, "Failed")
                self.assertIn("Simulated disk error", upload_rec.error_message)


if __name__ == "__main__":
    unittest.main()
