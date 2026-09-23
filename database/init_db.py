import sys
import os

# Add parent directory to sys.path to allow backend imports
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pymysql
from dotenv import load_dotenv

load_dotenv()

from backend.config import Config
from backend.app import create_app
from backend.models import db, Setting

def init_database():
    """Initializes the MySQL database and all required tables."""
    host = Config.DB_HOST
    port = Config.DB_PORT
    user = Config.DB_USER
    password = Config.DB_PASSWORD
    dbname = Config.DB_NAME

    print("=" * 60)
    print("  AUTOMATED SESSION RECORDING UPLOAD SYSTEM")
    print("  MySQL Database Initialization")
    print("=" * 60)
    print(f"Connecting to MySQL server at {host}:{port} as user '{user}'...")

    # Step 1: Connect to server and create database if it doesn't exist
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
            autocommit=True
        )
        with connection.cursor() as cursor:
            print(f"Ensuring database '{dbname}' exists...")
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{dbname}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        connection.close()
        print(f"Database '{dbname}' is ready.")
    except Exception as exc:
        print(f"[ERROR] Failed to connect to MySQL server or create database: {exc}")
        sys.exit(1)

    # Step 2: Initialize tables using Flask-SQLAlchemy
    print("\nCreating application tables via SQLAlchemy...")
    app = create_app()

    with app.app_context():
        try:
            db.create_all()
            
            # Ensure new columns exist on processing_queue if already created
            with db.engine.connect() as conn:
                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'file_name'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN file_name VARCHAR(255) NULL AFTER upload_id"))
                
                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'file_path'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN file_path VARCHAR(500) NULL AFTER file_name"))
                    conn.execute(db.text("ALTER TABLE processing_queue ADD UNIQUE INDEX uq_file_path (file_path)"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'detected_time'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN detected_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER error_message"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'file_size'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN file_size BIGINT NOT NULL DEFAULT 0 AFTER error_message"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'completed_time'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN completed_time DATETIME NULL AFTER detected_time"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'batch_id'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN batch_id INT NULL AFTER upload_id"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'detected_batch'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN detected_batch VARCHAR(255) NULL AFTER file_path"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'standardized_name'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN standardized_name VARCHAR(255) NULL AFTER detected_batch"))

                result = conn.execute(db.text("SHOW COLUMNS FROM processing_queue LIKE 'validation_status'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE processing_queue ADD COLUMN validation_status VARCHAR(50) NOT NULL DEFAULT 'Pending' AFTER standardized_name"))

                # Ensure columns on batches
                result = conn.execute(db.text("SHOW COLUMNS FROM batches LIKE 'keywords'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE batches ADD COLUMN keywords VARCHAR(500) NULL AFTER batch_name"))

                result = conn.execute(db.text("SHOW COLUMNS FROM batches LIKE 'destination_folder'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE batches ADD COLUMN destination_folder VARCHAR(500) NULL AFTER keywords"))

                result = conn.execute(db.text("SHOW COLUMNS FROM batches LIKE 'is_enabled'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE batches ADD COLUMN is_enabled BOOLEAN NOT NULL DEFAULT TRUE AFTER destination_folder"))

                # Ensure columns on uploads (Day 7)
                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'batch_name'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN batch_name VARCHAR(100) NULL AFTER batch_id"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'original_file_name'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN original_file_name VARCHAR(255) NULL AFTER batch_name"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'original_file_path'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN original_file_path VARCHAR(500) NULL AFTER original_file_name"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'file_extension'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN file_extension VARCHAR(20) NULL AFTER file_size"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'upload_date'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN upload_date DATE NULL AFTER file_extension"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'upload_time'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN upload_time VARCHAR(20) NULL AFTER upload_date"))

                result = conn.execute(db.text("SHOW COLUMNS FROM uploads LIKE 'checksum'"))
                if not result.fetchone():
                    conn.execute(db.text("ALTER TABLE uploads ADD COLUMN checksum VARCHAR(64) NULL AFTER upload_time"))

                conn.commit()

            print("Successfully created/verified tables:")
            print("  - batches")
            print("  - uploads")
            print("  - settings")
            print("  - processing_queue")

            # Step 3: Insert default system settings if not already present
            defaults = [
                ("system_name", "Automated Session Recording Upload System", "Display name of system"),
                ("system_status", "initialized", "Initial setup status"),
                ("environment", "development", "Application runtime environment"),
                ("stabilization_time", "30", "File size stabilization duration in seconds"),
                ("operation_mode", "COPY", "Recording upload operation mode: COPY or MOVE"),
                ("upload_root", "exports", "Root directory for batch uploads"),
                ("watch_folder", "uploads", "Directory monitored by file watcher"),
                ("auto_start_monitoring", "false", "Automatically start monitoring on application boot"),
                ("minimize_to_tray", "false", "Minimize application to system tray"),
                ("supported_extensions", ".mp4, .avi, .mov, .webm", "Comma-separated list of recording file extensions"),
                ("ignored_patterns", "*.tmp, *.part, *.crdownload, .*", "Comma-separated list of ignored patterns"),
                ("log_level", "INFO", "Logging verbosity level (DEBUG, INFO, WARNING, ERROR)")
            ]

            for key, val, desc in defaults:
                existing = Setting.query.filter_by(key=key).first()
                if not existing:
                    new_setting = Setting(key=key, value=val, description=desc)
                    db.session.add(new_setting)

            # Step 4: Seed default sample batches for Day 4 identification
            from backend.models import Batch
            default_batches = [
                ("Clarity", "Clarity, Clarity_Batch", "exports/Clarity"),
                ("Python-10", "Python-10, Python_10", "exports/Python-10"),
                ("DS-Batch", "DS-Batch, DataScience", "exports/DS-Batch")
            ]

            for name, keywords, dest in default_batches:
                existing_batch = Batch.query.filter_by(batch_name=name).first()
                if not existing_batch:
                    batch_record = Batch(
                        batch_name=name,
                        keywords=keywords,
                        destination_folder=dest,
                        is_enabled=True,
                        status="active"
                    )
                    db.session.add(batch_record)
                else:
                    if not existing_batch.keywords:
                        existing_batch.keywords = keywords
                    if not existing_batch.destination_folder:
                        existing_batch.destination_folder = dest
            
            db.session.commit()
            print("\nDefault system settings and sample batches configured.")
            print("\n" + "=" * 60)
            print("  Database initialization completed successfully!")
            print("=" * 60)
        except Exception as exc:
            db.session.rollback()
            print(f"[ERROR] Failed to create tables: {exc}")
            sys.exit(1)

if __name__ == "__main__":
    init_database()
