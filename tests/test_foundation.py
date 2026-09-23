import os
import sys
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app
from backend.models import db, Batch, Upload, Setting, ProcessingQueue

class TestSystemFoundation(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_api(self):
        """Test GET /api/health returns required JSON contract."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("message"), "Backend is running")

    def test_root_serves_html(self):
        """Test GET / serves frontend index.html."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Automated Session Recording Upload System", response.data)

    def test_db_status_endpoint(self):
        """Test GET /api/db-status returns database connectivity status."""
        response = self.client.get("/api/db-status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "connected")
        self.assertIn("counts", data)

    def test_models_exist(self):
        """Test that all required models are mapped and queryable."""
        with self.app.app_context():
            batches = Batch.query.all()
            uploads = Upload.query.all()
            settings = Setting.query.all()
            queue = ProcessingQueue.query.all()
            self.assertIsInstance(batches, list)
            self.assertIsInstance(uploads, list)
            self.assertIsInstance(settings, list)
            self.assertIsInstance(queue, list)

if __name__ == "__main__":
    unittest.main()
