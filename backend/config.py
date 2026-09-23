import os
import urllib.parse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-secret-key-change-in-production")

    # MySQL connection configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "session_recording_db")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Encode password to handle special characters safely
    _encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    _auth_segment = f"{DB_USER}:{_encoded_password}" if _encoded_password else DB_USER

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{_auth_segment}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    # Directory paths
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
    UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
    LOGS_DIR = os.path.join(BASE_DIR, "logs")
    EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
    UNKNOWN_DIR = os.path.join(BASE_DIR, "unknown")

    # Watch Folder Configuration
    _configured_watch_folder = os.getenv("WATCH_FOLDER", "uploads")
    if os.path.isabs(_configured_watch_folder):
        WATCH_FOLDER = _configured_watch_folder
    else:
        WATCH_FOLDER = os.path.abspath(os.path.join(BASE_DIR, _configured_watch_folder))

    # Supported and Ignored Extensions / Patterns
    SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mov", ".webm"}
    IGNORED_EXTENSIONS = {".tmp", ".part", ".crdownload"}
    IGNORED_PATTERNS = {"~*", ".*", "desktop.ini", "thumbs.db"}
