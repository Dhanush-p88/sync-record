# Automated Session Recording Upload System

An enterprise-grade, automated session recording detection, stabilization, standardized renaming, batch routing, and upload synchronization platform.

---

## 1. Project Overview

The **Automated Session Recording Upload System** is designed to automatically ingest raw session recordings from screen capture software (e.g., Zoom, OBS, Teams, Webex) dropped into a designated **Watch Folder**.

The system detects video files (`.mp4`, `.avi`, `.mov`, `.webm`), verifies that files have finished writing via a **Stabilization Engine**, identifies their course or module batch via configurable keywords and regular expressions, renames them into a **standardized timestamped naming scheme**, routes them to dedicated batch destination directories in either **COPY** or **MOVE** mode, tracks the full lifecycle audit trail in **MySQL**, streams real-time diagnostic logs, provides **Excel and CSV exports**, and presents an interactive web dashboard.

---

## 2. Key Features

- **Automated Watch Folder Monitoring**: Continuous, event-driven filesystem monitoring using Python's `watchdog` library.
- **Smart File Stabilization**: Periodically checks file size over a configurable duration (default 30 seconds) to ensure incomplete file writes, locked streams, or network copies are never prematurely processed.
- **Dynamic Batch Mapping**: Matches filenames against configured keywords and regex patterns (e.g., `Clarity`, `Python-10`, `DS-Batch`) stored in MySQL.
- **Standardized Renaming**: Converts filenames into standardized format: `[BatchName]_[YYYY-MM-DD]_[HH-MM-SS].[extension]`.
- **Collision & Overwrite Prevention**: Never overwrites existing files; automatically appends numeric suffixes (`_1`, `_2`, `_3`).
- **Flexible Transfer Modes**: Supports both `COPY` mode (preserves original recordings in watch folder) and `MOVE` mode (transfers original recordings into batch directories).
- **Asynchronous Processing Pipeline**: File stabilization and transfer tasks run in background threads, keeping the Flask REST API and web UI responsive.
- **Audit Trail & SHA-256 Checksums**: Records complete upload histories including original file paths, destination paths, file size, extension, upload date, upload time, and SHA-256 integrity checksums.
- **Live Interactive Dashboard**: Real-time counters, monitoring controls (`Start`, `Pause`, `Resume`, `Stop`), active processing queue, and recent upload listings.
- **Cloud Drive Sync & Ingestion**: Directly paste a Google Drive folder link or local cloud path to preview detected video recordings and sync them into the pipeline with one click.
- **Excel & CSV Export**: One-click export of MySQL upload history to `uploads_summary.xlsx` and `uploads_summary.csv`.
- **Centralized Application Logging**: Detailed logs written to `logs/app.log` with rotating file handlers and automatic credential scrubbing to mask database passwords.
- **Real-Time Notification System**: Non-intrusive browser toasts for recording completion, batch creation, settings changes, unknown batch warnings, and error diagnostics.

---

## 3. Architecture & Processing Flow

```text
[Watch Folder]
       │
       ▼ (Watchdog Event)
[File Detection] ── Filter ignored (.tmp, .part, hidden) ──► [processing_queue: 'Pending']
       │
       ▼
[File Stabilization] ── Checks size stability across configured seconds ──► [status: 'Ready']
       │
       ▼
[Batch Identification] ── Matches keywords/patterns in MySQL 'batches' ──► [status: 'Batch Identified']
       │                                                                  (or 'Unknown Batch')
       ▼
[File Validation] ── Validates size > 0, extension, readability
       │
       ▼
[Standardized Renaming] ── Generates [Batch]_[YYYY-MM-DD]_[HH-MM-SS].[ext] (with duplicate _N handling)
       │
       ▼
[Copy / Move Engine] ── Transfers file to [Upload Root]/[Batch Name]/
       │
       ▼
[Integrity Verification] ── Verifies file exists & size matches source
       │
       ▼
[MySQL Upload History] ── Inserts upload record + SHA-256 checksum ──► [status: 'Uploaded']
       │
       ▼
[Dashboard & Toast Notification] ── Updates live counters, recent uploads, and fires user toast
```

---

## 4. Technology Stack

- **Frontend**: Vanilla HTML5, CSS3, JavaScript (ES6+), Google Fonts (Inter & JetBrains Mono)
- **Backend Framework**: Python Flask 3.x with Flask-CORS
- **Database**: MySQL 8.x / MariaDB
- **ORM & Driver**: Flask-SQLAlchemy 3.x, PyMySQL, cryptography
- **File System Observer**: Watchdog 4.x
- **Data Export**: Pandas, OpenPyXL
- **Configuration**: Python-dotenv

---

## 5. Project Directory Structure

```text
sync record/
├── backend/
│   ├── __init__.py
│   ├── app.py                      # Flask application factory, REST APIs & web routes
│   ├── config.py                   # Configuration & environment variable mappings
│   ├── models.py                   # SQLAlchemy models (batches, uploads, settings, processing_queue)
│   └── services/
│       ├── __init__.py
│       ├── file_watcher.py         # Watchdog filesystem monitoring service
│       ├── stabilization.py        # File size stabilization service
│       ├── batch_manager.py        # Batch identification & keyword mapping service
│       ├── file_processor.py       # File validation & standardized renaming service
│       ├── upload_engine.py        # File copy/move and destination verification engine
│       ├── upload_service.py       # Asynchronous end-to-end pipeline orchestrator
│       ├── export_service.py       # Excel (.xlsx) and CSV (.csv) summary exporter
│       └── logging_service.py      # Centralized logging, credential masking & log APIs
├── frontend/
│   ├── index.html                  # Live Dashboard UI
│   ├── dashboard.js                # Dashboard polling, controls & toast notifications
│   ├── batches.html                # Batch Management UI (CRUD & keyword patterns)
│   ├── batches.js                  # Batch CRUD client script
│   ├── settings.html               # System configuration UI
│   ├── settings.js                 # Settings client script
│   ├── history.html                # Historical upload audit trail UI
│   ├── history.js                  # Audit trail client script with Excel/CSV triggers
│   ├── logs.html                   # Real-time application logs viewer UI
│   ├── logs.js                     # Log streaming & level filtering client script
│   └── style.css                   # Unified dark theme design system
├── database/
│   ├── __init__.py
│   └── init_db.py                  # Automated MySQL schema migrations & default seeds
├── tests/                          # 60 automated unit and integration tests
├── logs/                           # logs/app.log and rotation archives
├── uploads/                        # Default incoming recording Watch Folder
├── exports/                        # Default Upload Root directory
├── unknown/                        # Unrecognized recording storage
├── .env.example                    # Environment variable template
├── .env                            # Active environment configuration (git-ignored)
├── requirements.txt                # Python package dependencies
└── README.md                       # Complete documentation
```

---

## 6. Prerequisites

- **Python**: Version 3.10 or higher (Python 3.13 supported)
- **MySQL**: MySQL 8.x or MariaDB (via XAMPP, MySQL Server, or Docker)
- **PowerShell** or any standard command-line shell

---

## 7. Installation & Setup

### Step 1: Clone or Open Workspace
Ensure your working directory is the project root:
```powershell
cd "c:\Users\danus\OneDrive\Documents\Antigravity projects\sync record"
```

### Step 2: Create & Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to create your local `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` and set your MySQL credentials:
```ini
DB_HOST=127.0.0.1
DB_PORT=3307
DB_NAME=session_recording_db
DB_USER=root
DB_PASSWORD=

FLASK_ENV=development
FLASK_PORT=5000
SECRET_KEY=session-recording-secret-key-2026

WATCH_FOLDER=uploads
UPLOAD_ROOT=exports
```

### Step 5: Initialize MySQL Database & Tables
Run the database initialization script to create the schema and seed default settings and batches:
```powershell
python database/init_db.py
```

---

## 8. Running the Application

Start the Flask application server:
```powershell
python backend/app.py
```

The application will start on `http://127.0.0.1:5000`.

### Web Interface URLs

| Page | URL | Description |
| :--- | :--- | :--- |
| **Dashboard** | [http://localhost:5000/](http://localhost:5000/) | Live counters, monitoring controls, active queue, and recent uploads. |
| **Batch Management** | [http://localhost:5000/batches](http://localhost:5000/batches) | Add, edit, delete, and enable/disable batch patterns. |
| **Settings** | [http://localhost:5000/settings](http://localhost:5000/settings) | Configure watch folder, upload root, COPY/MOVE mode, and stabilization time. |
| **Upload History** | [http://localhost:5000/history](http://localhost:5000/history) | Searchable, paginated audit trail with SHA-256 checksums and Excel/CSV export. |
| **Application Logs** | [http://localhost:5000/logs](http://localhost:5000/logs) | Real-time terminal log viewer with level filters (INFO, WARNING, ERROR). |

---

## 9. Configuration & Operational Guide

### Configuring the Watch Folder
- By default, incoming recordings are monitored in `uploads/`.
- Change this path in **Settings** (`/settings`) or via `.env` (`WATCH_FOLDER=...`).

### Configuring the Upload Root
- Destination batch directories are created inside `exports/` (e.g., `exports/Clarity/`).
- Change this in **Settings** (`/settings`) or via `.env` (`UPLOAD_ROOT=...`).

### Adding and Managing Batches
1. Navigate to **Batches** (`/batches`).
2. Click **+ Add New Batch**.
3. Provide:
   - **Batch Name**: e.g., `Clarity`
   - **Keywords / Patterns**: comma-separated list, e.g., `Clarity, Clarity_Batch, ClaritySession`
   - **Destination Folder**: destination path, e.g., `exports/Clarity`
   - **Active Status**: Enabled / Disabled
4. Click **Save Batch**.

### COPY Mode vs. MOVE Mode
- **COPY Mode**:
  - Keeps the original video recording in the Watch Folder.
  - Copies the file into the batch destination directory with the standardized filename.
  - Recommended during testing and verification.
- **MOVE Mode**:
  - Moves the original video recording into the batch destination directory with the standardized filename.
  - Recommended for production environments to save disk space.
- Toggle between modes on the **Dashboard** or in **Settings**.

---

## 10. Data Export (Excel & CSV)

- **Excel Export**: Click **Export Excel** on `/history` or request `GET /api/export/excel`.
  - Downloads `uploads_summary.xlsx`.
  - Contains columns: `S.No`, `Batch Name`, `Recording Name`, `Upload Date`, `Upload Time`, `File Path`, `Size`, `Status`.
- **CSV Export**: Click **Export CSV** on `/history` or request `GET /api/export/csv`.
  - Downloads `uploads_summary.csv` with the same columns.

---

## 11. REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | GET | Health check status endpoint. |
| `/api/db-status` | GET | MySQL connection check and table row counts. |
| `/api/monitor/start` | POST | Starts watch folder filesystem monitoring. |
| `/api/monitor/pause` | POST | Pauses watch folder event processing. |
| `/api/monitor/resume` | POST | Resumes watch folder event processing. |
| `/api/monitor/stop` | POST | Stops file observer completely. |
| `/api/status` | GET | Returns current monitoring state, config, and active queue. |
| `/api/batches` | GET, POST | List all batches or create a new batch mapping. |
| `/api/batches/<id>` | PUT, DELETE | Update or delete a batch mapping. |
| `/api/batches/<id>/toggle` | POST | Toggle batch active/disabled state. |
| `/api/settings` | GET, POST | Retrieve or update application configuration settings. |
| `/api/settings/mode` | POST | Quickly toggle operation mode (`COPY` / `MOVE`). |
| `/api/uploads` | GET | Paginated upload history with search, batch, date, and status filters. |
| `/api/uploads/<id>` | GET | Detailed metadata and SHA-256 checksum for a specific upload record. |
| `/api/uploads/recent` | GET | Returns top recent completed uploads. |
| `/api/export/excel` | GET | Generates and downloads `uploads_summary.xlsx`. |
| `/api/export/csv` | GET | Generates and downloads `uploads_summary.csv`. |
| `/api/logs` | GET | Returns parsed application logs with level and keyword filtering. |
| `/api/logs/clear` | POST | Truncates `logs/app.log`. |
| `/api/drive/preview` | POST | Inspects Google Drive or local cloud folder and returns detected videos. |
| `/api/drive/sync` | POST | Downloads/ingests selected Drive recordings into the watch folder. |

---

## 12. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Can't connect to MySQL server` | MySQL service stopped or port mismatch | Start MySQL in XAMPP or service manager; ensure `DB_PORT` in `.env` matches your MySQL port (e.g. `3306` or `3307`). |
| Files remain in `Stabilizing` status | Video file is still being written by capture tool | Wait until the recording software finishes saving; the default stabilization period is 30 seconds. |
| Recording marked as `Unknown Batch` | Filename does not contain any configured batch keywords | Add the filename keyword to an existing batch or create a new batch in `/batches`. |
| `File size is 0 bytes` | Incomplete or empty video recording | The system will not process 0-byte recordings to prevent corrupted destination files. |
| Logs show `Permission denied` | File locked exclusively by recording tool | Stabilization waits for write handles to be released; check if another process is locking the file. |

---

## 13. Running Automated Tests

Run the full automated test suite (60 unit and integration tests):
```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

To run individual test modules:
```powershell
# Run final 16-case system test
python -m unittest tests/test_final_system.py

# Run export and logging tests
python -m unittest tests/test_export_and_logging.py

# Run settings and batch API tests
python -m unittest tests/test_settings_api.py

# Run complete upload service pipeline tests
python -m unittest tests/test_upload_service.py
```

---

## 14. License

Internal Enterprise Application &bull; Automated Session Recording Upload System
