"""
Google Drive Direct API Upload Service
Automated Session Recording Upload System

Provides direct server-to-cloud uploading into Google Drive folders
using Google Drive API v3 (OAuth2 and Service Account credentials).
"""

import os
import json
import logging
from backend.services.logging_service import logging_service

TARGET_FOLDER_ID = "1IfrJujHUpRZ-258dZVBBHvwTscdWwK4a"
TARGET_FOLDER_URL = "https://drive.google.com/drive/folders/1IfrJujHUpRZ-258dZVBBHvwTscdWwK4a?usp=drive_link"
TARGET_USER_EMAIL = "doll7365000@gmail.com"
SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]


class GDriveAPIService:
    def __init__(self, target_folder_id=TARGET_FOLDER_ID):
        self.target_folder_id = target_folder_id
        self.credentials_path = "credentials.json"
        self.token_path = "token.json"
        self.service_account_path = "service_account.json"
        self.user_email = TARGET_USER_EMAIL

    def get_authorization_url(self, redirect_uri="http://localhost:5000/api/gdrive/oauth2callback"):
        """Generates Google OAuth authorization URL using client credentials."""
        if not os.path.exists(self.credentials_path):
            return None, "credentials.json file not found"

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            flow.redirect_uri = redirect_uri
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                login_hint=self.user_email
            )
            return auth_url, state
        except Exception as e:
            return None, str(e)

    def exchange_code(self, code: str, redirect_uri="http://localhost:5000/api/gdrive/oauth2callback") -> bool:
        """Exchanges OAuth code for tokens and saves to token.json."""
        if not os.path.exists(self.credentials_path):
            return False

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            flow.redirect_uri = redirect_uri
            flow.fetch_token(code=code)
            creds = flow.credentials
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logging_service.log_event("INFO", "GDriveAPI", f"OAuth token saved successfully for {self.user_email}")
            return True
        except Exception as e:
            logging_service.log_event("ERROR", "GDriveAPI", f"Token exchange failed: {e}")
            return False

    def get_credentials(self):
        """
        Retrieves valid Google Drive API credentials if available.
        """
        # 1. Check Service Account credentials
        if os.path.exists(self.service_account_path):
            try:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_path, scopes=SCOPES
                )
                return creds
            except Exception as e:
                logging_service.log_event("WARNING", "GDriveAPI", f"Service account error: {e}")

        # 2. Check token.json
        if os.path.exists(self.token_path):
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                if creds and creds.valid:
                    return creds
                if creds and creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                    with open(self.token_path, "w") as token:
                        token.write(creds.to_json())
                    return creds
            except Exception as e:
                logging_service.log_event("WARNING", "GDriveAPI", f"Token error: {e}")

        # 3. Check credentials.json
        if os.path.exists(self.credentials_path):
            try:
                with open(self.credentials_path, "r") as f:
                    data = json.load(f)
                if "type" in data and data["type"] == "service_account":
                    from google.oauth2 import service_account
                    return service_account.Credentials.from_service_account_info(data, scopes=SCOPES)
            except Exception as e:
                logging_service.log_event("WARNING", "GDriveAPI", f"Credentials read error: {e}")

        return None

    def is_authenticated(self) -> bool:
        """Returns True if Google Drive API credentials are configured and valid."""
        return self.get_credentials() is not None

    def upload_file(self, file_path: str, folder_id: str = None) -> dict:
        """
        Uploads a video file directly to the Google Drive cloud folder.
        """
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File does not exist: {file_path}"}

        target_id = folder_id or self.target_folder_id
        creds = self.get_credentials()

        if not creds:
            return {
                "success": False,
                "error": "Google Drive API credentials not found. Please connect your Google account or provide credentials.json.",
                "needs_auth": True,
                "folder_id": target_id,
                "folder_url": TARGET_FOLDER_URL
            }

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            drive_service = build("drive", "v3", credentials=creds)
            file_name = os.path.basename(file_path)

            file_metadata = {
                "name": file_name,
                "parents": [target_id]
            }

            media = MediaFileUpload(
                file_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 5
            )

            request = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, size"
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logging_service.log_event("INFO", "GDriveAPI", f"Uploading {file_name}: {int(status.progress() * 100)}%")

            logging_service.log_event(
                "INFO",
                "GDriveAPI",
                f"Successfully uploaded '{file_name}' to Google Drive folder '{target_id}' (File ID: {response.get('id')})"
            )

            return {
                "success": True,
                "file_id": response.get("id"),
                "file_name": response.get("name"),
                "web_view_link": response.get("webViewLink"),
                "folder_url": TARGET_FOLDER_URL,
                "folder_id": target_id
            }

        except Exception as exc:
            logging_service.log_event("ERROR", "GDriveAPI", f"Failed to upload '{file_path}' to Google Drive: {exc}")
            return {"success": False, "error": str(exc), "folder_url": TARGET_FOLDER_URL}

    def upload_all_in_folder(self, local_folder="exports/meetings", folder_id=None) -> dict:
        """
        Uploads all video recordings in a local directory to Google Drive.
        """
        if not os.path.exists(local_folder):
            return {"success": False, "error": f"Folder does not exist: {local_folder}"}

        target_id = folder_id or self.target_folder_id
        uploaded = []
        errors = []

        for fname in os.listdir(local_folder):
            fpath = os.path.join(local_folder, fname)
            if os.path.isfile(fpath) and fname.lower().endswith((".mp4", ".avi", ".mov", ".webm")):
                res = self.upload_file(fpath, folder_id=target_id)
                if res.get("success"):
                    uploaded.append(res)
                else:
                    errors.append({"file": fname, "error": res.get("error")})

        return {
            "success": len(errors) == 0 or len(uploaded) > 0,
            "uploaded_count": len(uploaded),
            "uploaded_files": uploaded,
            "errors": errors,
            "folder_url": TARGET_FOLDER_URL
        }


gdrive_api_service = GDriveAPIService()
