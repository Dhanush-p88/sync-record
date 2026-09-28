import os
import urllib.parse
from dotenv import load_dotenv

# Base directory for the repository
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables from .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-secret-key-change-in-production")
    BASE_DIR = BASE_DIR
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
    UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
    LOGS_DIR = os.path.join(BASE_DIR, "logs")
    EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
    UNKNOWN_DIR = os.path.join(BASE_DIR, "unknown")

    # MySQL connection configuration
    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = int(os.getenv("DB_PORT", "3306")) if os.getenv("DB_PORT") else 3306
    DB_NAME = os.getenv("DB_NAME", "session_recording_db")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Encode password to handle special characters safely
    _encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    _auth_segment = f"{DB_USER}:{_encoded_password}" if _encoded_password else DB_USER

    DATABASE_URL = os.getenv("DATABASE_URL")
    is_render = os.getenv("RENDER", "false").lower() == "true"
    use_sqlite = os.getenv("USE_SQLITE", "false").lower() == "true"

    if DATABASE_URL:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    elif is_render or use_sqlite or not DB_HOST:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'session_recording.db')}"
    else:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{_auth_segment}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_recycle": 280,
            "pool_pre_ping": True,
        }

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
