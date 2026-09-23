import os
import sys
import time
import unittest
import tempfile
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app
from backend.models import db, ProcessingQueue
from backend.services.file_watcher import FileWatcherService

class TestFileWatcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_watch_")
        self.app = create_app()
        self.app.config["WATCH_FOLDER"] = self.test_dir
        self.client = self.app.test_client()

        self.service = FileWatcherService(app=self.app, watch_folder=self.test_dir)
        with self.app.app_context():
            ProcessingQueue.query.filter(ProcessingQueue.file_name.like("unit_test_%")).delete()
            db.session.commit()

    def tearDown(self):
        self.service.stop()
        with self.app.app_context():
            ProcessingQueue.query.filter(ProcessingQueue.file_name.like("unit_test_%")).delete()
            db.session.commit()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_monitor_lifecycle(self):
        """Test start, pause, resume, and stop lifecycle transitions."""
        # 1. Start
        res = self.service.start()
        self.assertTrue(res["success"])
        self.assertEqual(self.service.state, FileWatcherService.STATUS_RUNNING)

        # 2. Pause
        res = self.service.pause()
        self.assertTrue(res["success"])
        self.assertEqual(self.service.state, FileWatcherService.STATUS_PAUSED)

        # 3. Resume
        res = self.service.resume()
        self.assertTrue(res["success"])
        self.assertEqual(self.service.state, FileWatcherService.STATUS_RUNNING)

        # 4. Stop
        res = self.service.stop()
        self.assertTrue(res["success"])
        self.assertEqual(self.service.state, FileWatcherService.STATUS_STOPPED)

    def test_file_detection_and_queue_insertion(self):
        """Test that supported video files are added to processing_queue."""
        self.service.start()

        sample_file = os.path.join(self.test_dir, "unit_test_recording.mp4")
        with open(sample_file, "wb") as f:
            f.write(b"SAMPLE_VIDEO_CONTENT")

        # Explicitly process detected file
        self.service.process_detected_file(sample_file)

        norm_sample_path = os.path.abspath(sample_file)
        with self.app.app_context():
            item = ProcessingQueue.query.filter_by(file_path=norm_sample_path).first()
            self.assertIsNotNone(item)
            self.assertIn(item.status, ["Pending", "Stabilizing"])
            self.assertEqual(item.file_name, "unit_test_recording.mp4")
            self.assertIsNotNone(item.detected_time)

            # Test de-duplication: process again and ensure count doesn't increase
            initial_count = ProcessingQueue.query.filter_by(file_path=norm_sample_path).count()
            self.service.process_detected_file(sample_file)
            new_count = ProcessingQueue.query.filter_by(file_path=norm_sample_path).count()
            self.assertEqual(initial_count, new_count)

            # Cleanup test record
            db.session.delete(item)
            db.session.commit()

    def test_ignored_and_unsupported_files(self):
        """Test that temporary and unsupported files are ignored."""
        self.service.start()

        ignored_files = [
            os.path.join(self.test_dir, "download.crdownload"),
            os.path.join(self.test_dir, "tempfile.tmp"),
            os.path.join(self.test_dir, "video.mp4.part"),
            os.path.join(self.test_dir, "document.txt")
        ]

        for filepath in ignored_files:
            with open(filepath, "w") as f:
                f.write("test content")
            self.service.process_detected_file(filepath)

            with self.app.app_context():
                item = ProcessingQueue.query.filter_by(file_name=os.path.basename(filepath)).first()
                self.assertIsNone(item, f"{filepath} should not be queued")

    def test_api_endpoints(self):
        """Test REST API control endpoints."""
        # 1. Start monitor via API
        res = self.client.post("/api/monitor/start")
        self.assertEqual(res.status_code, 200)

        # 2. Get status via API
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "RUNNING")
        self.assertIn("pending_files", data)
        self.assertIn("recent_files", data)

        # 3. Pause
        res = self.client.post("/api/monitor/pause")
        self.assertEqual(res.status_code, 200)

        # 4. Resume
        res = self.client.post("/api/monitor/resume")
        self.assertEqual(res.status_code, 200)

        # 5. Stop
        res = self.client.post("/api/monitor/stop")
        self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
