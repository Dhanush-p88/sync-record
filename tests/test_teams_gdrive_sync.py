import os
import shutil
import tempfile
import unittest
from backend.app import create_app
from backend.models import db, Batch, Upload, Setting
from backend.services.cloud_sync_service import cloud_sync_service


class TestTeamsGDriveSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.test_dir = tempfile.mkdtemp(prefix="test_teams_sync_")
        self.watch_folder = os.path.join(self.test_dir, "watch")
        self.gdrive_folder = os.path.join(self.test_dir, "GoogleDrive")
        os.makedirs(self.watch_folder, exist_ok=True)
        os.makedirs(self.gdrive_folder, exist_ok=True)

        cloud_sync_service.watch_folder = self.watch_folder
        self.service = cloud_sync_service

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        self.app_context.pop()

    def test_01_parse_teams_and_sharepoint_links(self):
        """Test recognition and parsing of Microsoft Teams and SharePoint recording links."""
        sharepoint_link = "https://contoso-my.sharepoint.com/:v:/g/personal/user/EYg0Y9_Clarity_Session_Rec?e=4hjk"
        res = self.service.parse_drive_link(sharepoint_link)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "teams_recording")
        self.assertIn("sharepoint.com", res["identifier"])

        teams_link = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_Clarity_Sprint_Review%40thread.v2/0"
        res_teams = self.service.parse_drive_link(teams_link)
        self.assertIsNotNone(res_teams)
        self.assertEqual(res_teams["type"], "teams_recording")

        onedrive_link = "https://1drv.ms/v/s!AmZ9vClarityMeetingRecording"
        res_onedrive = self.service.parse_drive_link(onedrive_link)
        self.assertIsNotNone(res_onedrive)
        self.assertEqual(res_onedrive["type"], "teams_recording")

    def test_02_preview_teams_link(self):
        """Test previewing video metadata from a Teams recording link."""
        link = "https://contoso.sharepoint.com/sites/Recordings/Clarity_Batch_Teams_Session.mp4?download=1"
        res = self.service.preview_drive_contents(link)
        self.assertTrue(res["success"])
        self.assertEqual(res["source_type"], "teams_recording")
        self.assertEqual(len(res["videos"]), 1)
        self.assertEqual(res["videos"][0]["batch"], "Clarity")

    def test_03_sync_teams_to_watch_folder(self):
        """Test downloading and ingesting Teams recording into the watch folder."""
        link = "https://contoso.sharepoint.com/sites/Recordings/Clarity_Teams_Video.mp4"
        res = self.service.sync_drive_videos(link, target_batch="Clarity")
        self.assertTrue(res["success"])
        self.assertEqual(res["synced_count"], 1)

        dest_file = res["synced_files"][0]["path"]
        self.assertTrue(os.path.exists(dest_file))
        self.assertTrue(os.path.getsize(dest_file) > 0)
        self.assertTrue(os.path.basename(dest_file).startswith("Clarity_"))

    def test_04_auto_export_to_gdrive(self):
        """Test auto-exporting a completed video file to Google Drive destination."""
        sample_file = os.path.join(self.watch_folder, "Clarity_2026-09-03_10-00-00.mp4")
        with open(sample_file, "wb") as f:
            f.write(b"SAMPLE_VIDEO_CONTENT_FOR_GOOGLE_DRIVE")

        res = self.service.auto_export_to_gdrive(sample_file, gdrive_destination=self.gdrive_folder)
        self.assertTrue(res["success"])

        expected_dest = os.path.join(self.gdrive_folder, "Clarity_2026-09-03_10-00-00.mp4")
        self.assertTrue(os.path.exists(expected_dest))
        self.assertEqual(os.path.getsize(expected_dest), len(b"SAMPLE_VIDEO_CONTENT_FOR_GOOGLE_DRIVE"))

    def test_05_teams_to_gdrive_api_endpoint(self):
        """Test POST /api/drive/teams-to-gdrive API endpoint."""
        res = self.client.post("/api/drive/teams-to-gdrive", json={
            "teams_link": "https://contoso.sharepoint.com/:v:/s/Clarity_Sprint_Demo.mp4",
            "target_batch": "Clarity",
            "gdrive_destination": self.gdrive_folder
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("synced_files", data)


if __name__ == "__main__":
    unittest.main()
