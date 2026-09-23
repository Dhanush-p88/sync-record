import os
import sys
import time
import unittest
import tempfile
import shutil
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app
from backend.models import db, ProcessingQueue, Setting
from backend.services.stabilization import StabilizationService

class TestStabilizationService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_stab_")
        self.app = create_app()
        self.client = self.app.test_client()

        # Fast stabilization time for testing (1.0 second)
        self.stabilizer = StabilizationService(
            app=self.app,
            check_interval=0.2,
            default_stab_time=1.0
        )

    def tearDown(self):
        self.stabilizer.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_read_setting_from_db(self):
        """Test reading stabilization_time from MySQL Setting table."""
        with self.app.app_context():
            setting = Setting.query.filter_by(key="stabilization_time").first()
            if not setting:
                setting = Setting(key="stabilization_time", value="15")
                db.session.add(setting)
            else:
                setting.value = "15"
            db.session.commit()

            stab_time = self.stabilizer.get_configured_stabilization_time()
            self.assertEqual(stab_time, 15.0)

            # Restore to 30
            setting.value = "30"
            db.session.commit()

    def test_stabilization_progression_to_ready(self):
        """Test transition from Pending -> Stabilizing -> Ready once file size is unchanged."""
        test_file = os.path.join(self.test_dir, "test_session.mp4")
        with open(test_file, "wb") as f:
            f.write(b"INITIAL_CHUNK_DATA_12345")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="test_session.mp4",
                file_path=os.path.abspath(test_file),
                status="Pending",
                detected_time=datetime.now(timezone.utc)
            )
            db.session.add(item)
            db.session.commit()
            queue_id = item.id

        # First evaluation: starts tracking, transitions to Stabilizing
        now_ts = time.time()
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts, stab_time=1.0)
            self.assertEqual(item.status, "Stabilizing")
            self.assertGreater(item.file_size, 0)

        # Still within stabilization period (0.3s < 1.0s) -> should remain Stabilizing
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts + 0.3, stab_time=1.0)
            self.assertEqual(item.status, "Stabilizing")
            self.assertIsNone(item.completed_time)

        # After stabilization period (1.2s >= 1.0s) -> should transition to Ready
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts + 1.2, stab_time=1.0)
            self.assertIn(item.status, ["Ready", "Batch Identified", "Unknown Batch"])
            self.assertIsNotNone(item.completed_time)
            self.assertEqual(item.file_size, len(b"INITIAL_CHUNK_DATA_12345"))

            # Clean up test item
            db.session.delete(item)
            db.session.commit()

    def test_file_still_changing_resets_timer(self):
        """Test that writing more data to file resets the stability timer and prevents Ready."""
        test_file = os.path.join(self.test_dir, "growing_session.mp4")
        with open(test_file, "wb") as f:
            f.write(b"PART_ONE")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="growing_session.mp4",
                file_path=os.path.abspath(test_file),
                status="Pending",
                detected_time=datetime.now(timezone.utc)
            )
            db.session.add(item)
            db.session.commit()
            queue_id = item.id

        now_ts = time.time()
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts, stab_time=1.0)
            self.assertEqual(item.status, "Stabilizing")

        # Now simulate file growing (e.g. streaming recording)
        with open(test_file, "ab") as f:
            f.write(b"_PART_TWO_APPENDED")

        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts + 0.8, stab_time=1.0)
            self.assertEqual(item.status, "Stabilizing")
            self.assertIsNone(item.completed_time)

        # Even at now_ts + 1.2, since size changed at +0.8, it should NOT be ready yet (elapsed 0.4s < 1.0s)
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts + 1.2, stab_time=1.0)
            self.assertEqual(item.status, "Stabilizing")
            self.assertIsNone(item.completed_time)

        # Clean up
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            if item:
                db.session.delete(item)
                db.session.commit()

    def test_file_deleted_before_stabilization(self):
        """Test handling of file deletion before stabilization completes."""
        test_file = os.path.join(self.test_dir, "deleted_session.mp4")
        with open(test_file, "wb") as f:
            f.write(b"TEMPORARY_DATA")

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="deleted_session.mp4",
                file_path=os.path.abspath(test_file),
                status="Pending",
                detected_time=datetime.now(timezone.utc)
            )
            db.session.add(item)
            db.session.commit()
            queue_id = item.id

        now_ts = time.time()
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts, stab_time=1.0)

        # Now delete the file before it stabilizes
        os.remove(test_file)

        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts + 0.5, stab_time=1.0)
            self.assertEqual(item.status, "Failed")
            self.assertIn("deleted", item.error_message.lower())

            # Clean up
            db.session.delete(item)
            db.session.commit()

    def test_zero_byte_file_handling(self):
        """Test that a 0-byte file is not marked Ready."""
        test_file = os.path.join(self.test_dir, "empty_session.mp4")
        with open(test_file, "wb") as f:
            pass  # 0 bytes

        with self.app.app_context():
            item = ProcessingQueue(
                file_name="empty_session.mp4",
                file_path=os.path.abspath(test_file),
                status="Pending",
                detected_time=datetime.now(timezone.utc)
            )
            db.session.add(item)
            db.session.commit()
            queue_id = item.id

        now_ts = time.time()
        with self.app.app_context():
            item = ProcessingQueue.query.get(queue_id)
            self.stabilizer._evaluate_file(item, now_ts, stab_time=1.0)
            # Evaluate after time expired:
            self.stabilizer._evaluate_file(item, now_ts + 2.0, stab_time=1.0)
            # Must still NOT be ready
            self.assertNotEqual(item.status, "Ready")
            self.assertIsNone(item.completed_time)

            # Clean up
            db.session.delete(item)
            db.session.commit()

if __name__ == "__main__":
    unittest.main()
