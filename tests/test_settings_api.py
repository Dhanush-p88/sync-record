"""
Unit Tests for Day 8: Settings and Batch Management APIs
Automated Session Recording Upload System

Tests:
1. GET /api/settings - retrieve dictionary of all configuration settings.
2. POST /api/settings - update multiple settings and verify persistence in MySQL.
3. GET /api/uploads/recent - retrieve recent upload records.
4. Batch Management CRUD - add, retrieve, update, toggle, and delete batch.
"""

import json
import unittest

from backend.app import create_app
from backend.models import db, Setting, Batch, Upload


class TestSettingsAndBatches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_get_settings(self):
        """Test GET /api/settings returns settings dictionary."""
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("settings", data)
        settings = data["settings"]
        self.assertIn("operation_mode", settings)
        self.assertIn("stabilization_time", settings)
        self.assertIn("upload_root", settings)
        self.assertIn("watch_folder", settings)

    def test_update_settings(self):
        """Test POST /api/settings saves new/updated values into MySQL settings table."""
        payload = {
            "stabilization_time": "15",
            "log_level": "DEBUG",
            "auto_start_monitoring": "true",
            "custom_test_key": "custom_value_888",
        }
        response = self.client.post(
            "/api/settings",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("custom_test_key", data["settings"])
        self.assertEqual(data["settings"]["stabilization_time"], "15")
        self.assertEqual(data["settings"]["log_level"], "DEBUG")

        # Verify directly in MySQL
        with self.app.app_context():
            s = Setting.query.filter_by(key="custom_test_key").first()
            self.assertIsNotNone(s)
            self.assertEqual(s.value, "custom_value_888")
            # Clean up test key
            db.session.delete(s)
            # Restore stabilization_time
            stab = Setting.query.filter_by(key="stabilization_time").first()
            if stab:
                stab.value = "30"
            db.session.commit()

    def test_get_recent_uploads(self):
        """Test GET /api/uploads/recent returns uploads list."""
        response = self.client.get("/api/uploads/recent?limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("uploads", data)
        self.assertIsInstance(data["uploads"], list)

    def test_batch_crud_operations(self):
        """Test full Batch CRUD lifecycle: Add, Get, Edit, Toggle, Delete."""
        # 1. Add Batch
        add_res = self.client.post(
            "/api/batches",
            data=json.dumps({
                "batch_name": "Test_Batch_Day8",
                "keywords": "Test_Day8, Day8Sample",
                "destination_folder": "exports/Test_Batch_Day8",
                "is_enabled": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(add_res.status_code, 201)
        created = add_res.get_json()["batch"]
        batch_id = created["id"]
        self.assertEqual(created["batch_name"], "Test_Batch_Day8")

        # 2. Get Batch
        get_res = self.client.get(f"/api/batches/{batch_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["batch"]["batch_name"], "Test_Batch_Day8")

        # 3. Edit Batch
        update_res = self.client.put(
            f"/api/batches/{batch_id}",
            data=json.dumps({
                "batch_name": "Test_Batch_Day8_Edited",
                "keywords": "UpdatedKeyword1, UpdatedKeyword2",
                "destination_folder": "exports/Test_Batch_Day8_Edited",
            }),
            content_type="application/json",
        )
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.get_json()["batch"]
        self.assertEqual(updated["batch_name"], "Test_Batch_Day8_Edited")
        self.assertEqual(updated["keywords"], "UpdatedKeyword1, UpdatedKeyword2")

        # 4. Toggle Batch
        toggle_res = self.client.post(f"/api/batches/{batch_id}/toggle")
        self.assertEqual(toggle_res.status_code, 200)
        toggled = toggle_res.get_json()["batch"]
        self.assertFalse(toggled["is_enabled"])

        # 5. Delete Batch
        del_res = self.client.delete(f"/api/batches/{batch_id}")
        self.assertEqual(del_res.status_code, 200)

        # Verify deleted
        get_deleted = self.client.get(f"/api/batches/{batch_id}")
        self.assertEqual(get_deleted.status_code, 404)


if __name__ == "__main__":
    unittest.main()
