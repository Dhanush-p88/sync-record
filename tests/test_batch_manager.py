import os
import sys
import unittest
import json
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app
from backend.models import db, Batch, ProcessingQueue
from backend.services.batch_manager import BatchManagerService

class TestBatchManager(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.service = BatchManagerService(app=self.app)

        with self.app.app_context():
            # Ensure standard batches exist
            test_batches = [
                ("Clarity", "Clarity, Clarity_Batch", "exports/Clarity"),
                ("Python-10", "Python-10, Python_10", "exports/Python-10"),
                ("DS-Batch", "DS-Batch, DataScience", "exports/DS-Batch")
            ]
            for name, kw, dest in test_batches:
                b = Batch.query.filter_by(batch_name=name).first()
                if not b:
                    b = Batch(batch_name=name, keywords=kw, destination_folder=dest, is_enabled=True)
                    db.session.add(b)
                else:
                    b.keywords = kw
                    b.destination_folder = dest
                    b.is_enabled = True
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            # Clean up any test queue items and temporary test batches
            ProcessingQueue.query.filter(ProcessingQueue.file_name.like("unit_test_%")).delete()
            Batch.query.filter(Batch.batch_name.like("TestBatch_%")).delete()
            db.session.commit()

    def test_spec_filename_matching(self):
        """Test all sample filenames from user specification."""
        with self.app.app_context():
            # 1. Clarity_Batch_Session1_2026-08-06.mp4 -> Clarity
            _, b1 = self.service.identify_batch("Clarity_Batch_Session1_2026-08-06.mp4")
            self.assertEqual(b1, "Clarity")

            # 2. Python-10_Recording_Week2.mp4 -> Python-10
            _, b2 = self.service.identify_batch("Python-10_Recording_Week2.mp4")
            self.assertEqual(b2, "Python-10")

            # 3. DS-Batch_Module3_Session1.mp4 -> DS-Batch
            _, b3 = self.service.identify_batch("DS-Batch_Module3_Session1.mp4")
            self.assertEqual(b3, "DS-Batch")

            # 4. 2026-08-06_Clarity_Session.mp4 -> Clarity
            _, b4 = self.service.identify_batch("2026-08-06_Clarity_Session.mp4")
            self.assertEqual(b4, "Clarity")

            # 5. Random_Recording.mp4 -> Unknown
            batch_id, b5 = self.service.identify_batch("Random_Recording.mp4")
            self.assertIsNone(batch_id)
            self.assertEqual(b5, "Unknown")

    def test_case_insensitivity(self):
        """Test case-insensitive matching."""
        with self.app.app_context():
            _, b_lower = self.service.identify_batch("clarity_session.mp4")
            self.assertEqual(b_lower, "Clarity")

            _, b_upper = self.service.identify_batch("PYTHON-10_WEEK1.MP4")
            self.assertEqual(b_upper, "Python-10")

    def test_disabled_batch_ignored(self):
        """Test that disabled batches are not matched."""
        with self.app.app_context():
            b = Batch.query.filter_by(batch_name="Clarity").first()
            self.assertIsNotNone(b)
            b.is_enabled = False
            db.session.commit()

            # Now clarity file should not match
            _, detected = self.service.identify_batch("Clarity_Batch_Session1.mp4")
            self.assertEqual(detected, "Unknown")

            # Re-enable
            b.is_enabled = True
            db.session.commit()

    def test_process_item_queue_status_transition(self):
        """Test queue item status transition to 'Batch Identified' or 'Unknown Batch'."""
        with self.app.app_context():
            # Matched file
            item1 = ProcessingQueue(
                file_name="unit_test_Clarity_Batch_01.mp4",
                file_path="/tmp/unit_test_Clarity_Batch_01.mp4",
                status="Ready",
                detected_time=datetime.now(timezone.utc)
            )
            # Unmatched file
            item2 = ProcessingQueue(
                file_name="unit_test_Unknown_Sample.mp4",
                file_path="/tmp/unit_test_Unknown_Sample.mp4",
                status="Ready",
                detected_time=datetime.now(timezone.utc)
            )
            db.session.add(item1)
            db.session.add(item2)
            db.session.commit()

            # Process items
            self.service.process_item(item1)
            self.service.process_item(item2)

            self.assertEqual(item1.status, "Batch Identified")
            self.assertEqual(item1.detected_batch, "Clarity")
            self.assertIsNotNone(item1.batch_id)

            self.assertEqual(item2.status, "Unknown Batch")
            self.assertEqual(item2.detected_batch, "Unknown")
            self.assertIsNone(item2.batch_id)

            db.session.delete(item1)
            db.session.delete(item2)
            db.session.commit()

    def test_batch_crud_api_endpoints(self):
        """Test REST API CRUD endpoints for batch mappings."""
        # 1. GET /api/batches
        res = self.client.get("/api/batches")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["total"], 3)

        # 2. POST /api/batches
        create_payload = {
            "batch_name": "TestBatch_CRUD",
            "keywords": "Test_Keyword_A, Test_Keyword_B",
            "destination_folder": "exports/TestBatch_CRUD",
            "is_enabled": True
        }
        res_create = self.client.post("/api/batches", json=create_payload)
        self.assertEqual(res_create.status_code, 201)
        created_data = json.loads(res_create.data)["batch"]
        batch_id = created_data["id"]
        self.assertEqual(created_data["batch_name"], "TestBatch_CRUD")

        # 3. PUT /api/batches/<id>
        update_payload = {
            "keywords": "Updated_Keyword_C",
            "destination_folder": "exports/Updated_Folder"
        }
        res_update = self.client.put(f"/api/batches/{batch_id}", json=update_payload)
        self.assertEqual(res_update.status_code, 200)
        updated_data = json.loads(res_update.data)["batch"]
        self.assertEqual(updated_data["keywords"], "Updated_Keyword_C")

        # 4. POST /api/batches/<id>/toggle
        res_toggle = self.client.post(f"/api/batches/{batch_id}/toggle")
        self.assertEqual(res_toggle.status_code, 200)
        toggled_data = json.loads(res_toggle.data)["batch"]
        self.assertFalse(toggled_data["is_enabled"])

        # 5. DELETE /api/batches/<id>
        res_delete = self.client.delete(f"/api/batches/{batch_id}")
        self.assertEqual(res_delete.status_code, 200)

        # Verify 404 after deletion
        res_get_deleted = self.client.get(f"/api/batches/{batch_id}")
        self.assertEqual(res_get_deleted.status_code, 404)

if __name__ == "__main__":
    unittest.main()
