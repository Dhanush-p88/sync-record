"""
Test Cloud Drive Sync Feature
Automated Session Recording Upload System
"""

import os
import shutil
import tempfile
import unittest

from backend.app import create_app
from backend.services.cloud_sync_service import cloud_sync_service


class TestCloudSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.test_dir = tempfile.mkdtemp(prefix="test_drive_sync_")
        self.watch_folder = os.path.join(self.test_dir, "watch")
        os.makedirs(self.watch_folder, exist_ok=True)
        cloud_sync_service.watch_folder = self.watch_folder

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        self.app_context.pop()

    def test_01_parse_drive_links(self):
        # 1. Google Drive folder URL
        gdrive_url = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ"
        parsed = cloud_sync_service.parse_drive_link(gdrive_url)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type"], "gdrive_folder")
        self.assertEqual(parsed["identifier"], "1aBcDeFgHiJkLmNoPqRsTuVwXyZ")

        # 2. Google Drive open?id= link
        gdrive_open = "https://drive.google.com/open?id=12345ABCDEF"
        parsed_open = cloud_sync_service.parse_drive_link(gdrive_open)
        self.assertIsNotNone(parsed_open)
        self.assertEqual(parsed_open["type"], "gdrive_folder")

        # 3. Local path
        local_parsed = cloud_sync_service.parse_drive_link(self.test_dir)
        self.assertIsNotNone(local_parsed)
        self.assertEqual(local_parsed["type"], "local_path")

    def test_02_preview_local_drive(self):
        # Create a sample local cloud-synced folder with 2 video files
        cloud_folder = os.path.join(self.test_dir, "My Drive Recordings")
        os.makedirs(cloud_folder, exist_ok=True)
        with open(os.path.join(cloud_folder, "Clarity_Session_Drive1.mp4"), "wb") as f:
            f.write(b"SAMPLE_DRIVE_VIDEO_1")
        with open(os.path.join(cloud_folder, "Python-10_Session_Drive2.avi"), "wb") as f:
            f.write(b"SAMPLE_DRIVE_VIDEO_2")
        with open(os.path.join(cloud_folder, "notes.txt"), "wb") as f:
            f.write(b"NOT_A_VIDEO")

        res = cloud_sync_service.preview_drive_contents(cloud_folder)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_videos"], 2)
        video_names = [v["name"] for v in res["videos"]]
        self.assertIn("Clarity_Session_Drive1.mp4", video_names)
        self.assertIn("Python-10_Session_Drive2.avi", video_names)
        self.assertNotIn("notes.txt", video_names)

    def test_03_preview_gdrive_url(self):
        gdrive_url = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz"
        res = cloud_sync_service.preview_drive_contents(gdrive_url)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["total_videos"], 1)
        self.assertTrue(res["videos"][0]["name"].endswith(".mp4"))

    def test_04_sync_drive_videos(self):
        # Create a sample local folder
        cloud_folder = os.path.join(self.test_dir, "Drive_Sync_Src")
        os.makedirs(cloud_folder, exist_ok=True)
        with open(os.path.join(cloud_folder, "Clarity_Cloud_Sync_Test.mp4"), "wb") as f:
            f.write(b"CLOUD_VIDEO_CONTENT_TEST")

        sync_res = cloud_sync_service.sync_drive_videos(cloud_folder)
        self.assertTrue(sync_res["success"])
        self.assertEqual(sync_res["synced_count"], 1)

        # Verify file is in watch folder
        dest_path = os.path.join(self.watch_folder, "Clarity_Cloud_Sync_Test.mp4")
        self.assertTrue(os.path.exists(dest_path))
        self.assertEqual(os.path.getsize(dest_path), len(b"CLOUD_VIDEO_CONTENT_TEST"))

    def test_05_api_endpoints(self):
        # 1. Test POST /api/drive/preview
        res = self.client.post("/api/drive/preview", json={
            "drive_link": "https://drive.google.com/drive/folders/1xyzFolderId"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("videos", data)

        # 2. Test POST /api/drive/sync
        res_sync = self.client.post("/api/drive/sync", json={
            "drive_link": "https://drive.google.com/drive/folders/1xyzFolderId",
            "file_names": [data["videos"][0]["name"]]
        })
        self.assertEqual(res_sync.status_code, 200)
        sync_data = res_sync.get_json()
        self.assertTrue(sync_data["success"])
        self.assertGreaterEqual(sync_data["synced_count"], 1)


if __name__ == "__main__":
    unittest.main()
