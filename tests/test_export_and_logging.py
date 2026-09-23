"""
Unit and Integration Tests for Day 9: Export, Logging & Notifications
Automated Session Recording Upload System

Tests:
1. Excel Export (GET /api/export/excel) with pandas/openpyxl and required columns
2. CSV Export (GET /api/export/csv) with required columns
3. Application Logging Service writing to logs/app.log
4. Credential and sensitive data redaction in logs
5. Application Logs API (GET /api/logs) and level filtering (INFO, WARNING, ERROR)
6. Clear Logs API (POST /api/logs/clear)
"""

import io
import os
import unittest
import pandas as pd
from datetime import datetime, timezone

from backend.app import create_app
from backend.config import Config
from backend.models import db, Upload, Batch
from backend.services.export_service import export_service
from backend.services.logging_service import logging_service, sanitize_log_message


class TestExportAndLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Seed sample upload records for testing exports
        self.now_utc = datetime.now(timezone.utc)
        self.test_upload = Upload(
            batch_name="Clarity",
            original_file_name="Clarity_Batch_Session_ExportTest.mp4",
            file_name="Clarity_2026-09-02_12-00-00.mp4",
            file_path="exports/Clarity/Clarity_2026-09-02_12-00-00.mp4",
            file_size=1024,
            file_extension=".mp4",
            upload_date=self.now_utc.date(),
            upload_time=self.now_utc.strftime("%H:%M:%S"),
            status="Uploaded",
            error_message=None,
            uploaded_at=self.now_utc,
        )
        db.session.add(self.test_upload)
        db.session.commit()

    def tearDown(self):
        try:
            if self.test_upload and self.test_upload.id:
                u = db.session.get(Upload, self.test_upload.id)
                if u:
                    db.session.delete(u)
                    db.session.commit()
        except Exception:
            db.session.rollback()
        self.app_context.pop()

    def test_01_export_excel_api(self):
        """Test GET /api/export/excel returns valid Excel file with required columns."""
        response = self.client.get("/api/export/excel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response.content_type)
        self.assertIn("uploads_summary.xlsx", response.headers.get("Content-Disposition", ""))

        # Verify Excel content using pandas
        excel_buffer = io.BytesIO(response.data)
        df = pd.read_excel(excel_buffer, sheet_name="Uploads Summary")

        expected_columns = [
            "S.No", "Batch Name", "Recording Name", "Upload Date",
            "Upload Time", "File Path", "Size", "Status"
        ]
        for col in expected_columns:
            self.assertIn(col, df.columns)

        self.assertGreaterEqual(len(df), 1)
        # Check that the test record appears in the exported data
        matching = df[df["Recording Name"] == "Clarity_2026-09-02_12-00-00.mp4"]
        self.assertFalse(matching.empty)
        self.assertEqual(matching.iloc[0]["Batch Name"], "Clarity")

    def test_02_export_csv_api(self):
        """Test GET /api/export/csv returns valid CSV file with required columns."""
        response = self.client.get("/api/export/csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn("uploads_summary.csv", response.headers.get("Content-Disposition", ""))

        # Verify CSV content using pandas
        csv_buffer = io.StringIO(response.data.decode("utf-8"))
        df = pd.read_csv(csv_buffer)

        expected_columns = [
            "S.No", "Batch Name", "Recording Name", "Upload Date",
            "Upload Time", "File Path", "Size", "Status"
        ]
        for col in expected_columns:
            self.assertIn(col, df.columns)

        matching = df[df["Recording Name"] == "Clarity_2026-09-02_12-00-00.mp4"]
        self.assertFalse(matching.empty)
        self.assertEqual(matching.iloc[0]["Status"], "Uploaded")

    def test_03_logging_service_lifecycle_events(self):
        """Test application logging service records events with timestamp, level, and module."""
        test_marker = f"TestEvent_{datetime.now().timestamp()}"
        logging_service.log_event("INFO", "TestModule", f"Lifecycle event test marker: {test_marker}")

        # Check logs/app.log file directly
        log_file = os.path.join("logs", "app.log")
        self.assertTrue(os.path.exists(log_file))

        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(test_marker, content)
        self.assertIn("[INFO]", content)
        self.assertIn("[TestModule]", content)

    def test_04_credential_sanitization(self):
        """Test that sensitive database passwords and secrets are masked in logs."""
        raw_msg = "Connecting with password=SecretPassword123 and mysql://root:TopSecretDbPass@127.0.0.1:3307/db"
        sanitized = sanitize_log_message(raw_msg)

        self.assertNotIn("SecretPassword123", sanitized)
        self.assertNotIn("TopSecretDbPass", sanitized)
        self.assertIn("********", sanitized)

    def test_05_logs_api_and_level_filter(self):
        """Test GET /api/logs with level filtering and search."""
        unique_err_marker = f"ErrMarker_{datetime.now().timestamp()}"
        unique_warn_marker = f"WarnMarker_{datetime.now().timestamp()}"
        unique_info_marker = f"InfoMarker_{datetime.now().timestamp()}"

        logging_service.log_event("ERROR", "ErrModule", unique_err_marker)
        logging_service.log_event("WARNING", "WarnModule", unique_warn_marker)
        logging_service.log_event("INFO", "InfoModule", unique_info_marker)

        # 1. Fetch ERROR logs only
        res_err = self.client.get("/api/logs?level=ERROR")
        self.assertEqual(res_err.status_code, 200)
        data_err = res_err.get_json()
        self.assertEqual(data_err["status"], "success")
        levels = [l["level"] for l in data_err["logs"]]
        self.assertTrue(all(lvl == "ERROR" for lvl in levels))
        messages = [l["message"] for l in data_err["logs"]]
        self.assertTrue(any(unique_err_marker in m for m in messages))

        # 2. Search filter
        res_search = self.client.get(f"/api/logs?search={unique_warn_marker}")
        self.assertEqual(res_search.status_code, 200)
        data_search = res_search.get_json()
        self.assertGreaterEqual(len(data_search["logs"]), 1)
        self.assertIn(unique_warn_marker, data_search["logs"][0]["message"])

    def test_06_clear_logs_api(self):
        """Test POST /api/logs/clear truncates logs/app.log and logs the clear action."""
        response = self.client.post("/api/logs/clear")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])

        # Fetch logs again
        res_logs = self.client.get("/api/logs")
        logs_data = res_logs.get_json()
        self.assertLessEqual(len(logs_data["logs"]), 2)
        # Should contain the clear confirmation event
        self.assertTrue(any("cleared by user" in l["message"] for l in logs_data["logs"]))


if __name__ == "__main__":
    unittest.main()
