"""
Application Logging Service - Day 9 Implementation
Automated Session Recording Upload System

Provides:
1. Centralized logging to logs/app.log with date/time, log levels (INFO, WARNING, ERROR).
2. Credential/password sanitization.
3. Event log helpers across application lifecycle:
   - Application started / stopped
   - Monitoring started / paused / resumed / stopped
   - File detected / stabilized
   - Batch identified / unknown batch
   - Validation success / failure
   - Copy/move success / failure
   - Upload success / failure
   - Database and unexpected errors
4. Log retrieval with level and keyword filtering for /logs page.
5. Log clearing mechanism with confirmation.
"""

import os
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone


SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|pwd|secret|key)(\s*[:=]\s*)([^\s,;]+)', re.IGNORECASE), r'\1\2********'),
    (re.compile(r'(mysql(?:\+pymysql)?://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1********\3'),
]


def sanitize_log_message(msg: str) -> str:
    """Masks database passwords, secrets, and credentials in log text."""
    if not msg:
        return ""
    result = str(msg)
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class SanitizingFormatter(logging.Formatter):
    """Custom logging formatter that scrubs sensitive credentials."""
    def format(self, record):
        orig_msg = record.msg
        if isinstance(orig_msg, str):
            record.msg = sanitize_log_message(orig_msg)
        formatted = super().format(record)
        record.msg = orig_msg  # restore original
        return formatted


def _setup_app_logger():
    """Configures rotating file handler for logs/app.log."""
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", "app.log")

    logger = logging.getLogger("AppCentral")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        formatter = SanitizingFormatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Attach to root logger so all existing services automatically log to logs/app.log
        root_logger = logging.getLogger()
        if file_handler not in root_logger.handlers:
            root_logger.addHandler(file_handler)

    return logger


app_logger = _setup_app_logger()


class LoggingService:
    """Service providing event tracking and log retrieval for the application."""

    def __init__(self, logger=app_logger):
        self.logger = logger
        self.log_file_path = os.path.join("logs", "app.log")

    def init_app(self, app):
        """Bind and log application startup."""
        self.log_event("INFO", "Application", "Automated Session Recording Upload System started")

    def log_event(self, level: str, module: str, message: str):
        """Logs a standardized event with level, module tag, and message."""
        clean_msg = sanitize_log_message(message)
        log_line = f"[{module}] {clean_msg}"
        lvl = level.upper()

        if lvl == "ERROR":
            self.logger.error(log_line)
        elif lvl == "WARNING":
            self.logger.warning(log_line)
        elif lvl == "DEBUG":
            self.logger.debug(log_line)
        else:
            self.logger.info(log_line)

    # Specific Lifecycle Logging Helpers
    def log_monitoring_started(self, folder: str):
        self.log_event("INFO", "FileWatcher", f"Monitoring started on watch folder: '{folder}'")

    def log_monitoring_paused(self):
        self.log_event("WARNING", "FileWatcher", "Monitoring paused by user")

    def log_monitoring_resumed(self):
        self.log_event("INFO", "FileWatcher", "Monitoring resumed by user")

    def log_monitoring_stopped(self):
        self.log_event("WARNING", "FileWatcher", "Monitoring stopped by user")

    def log_file_detected(self, filename: str, path: str):
        self.log_event("INFO", "FileWatcher", f"Recording detected: '{filename}' (Path: '{path}')")

    def log_file_stabilized(self, filename: str, size: int, wait_sec: float):
        self.log_event("INFO", "Stabilization", f"File stabilized: '{filename}' (Size: {size} bytes, Duration: {wait_sec}s)")

    def log_batch_identified(self, filename: str, batch_name: str):
        self.log_event("INFO", "BatchManager", f"Batch identified: '{batch_name}' for file '{filename}'")

    def log_unknown_batch(self, filename: str):
        self.log_event("WARNING", "BatchManager", f"Unknown batch detected for file '{filename}'")

    def log_validation_result(self, filename: str, success: bool, error: str = None):
        if success:
            self.log_event("INFO", "FileProcessor", f"Validation successful for '{filename}'")
        else:
            self.log_event("WARNING", "FileProcessor", f"Validation failed for '{filename}': {error}")

    def log_transfer_result(self, filename: str, mode: str, dest_path: str, success: bool, error: str = None):
        if success:
            self.log_event("INFO", "UploadEngine", f"{mode} completed successfully for '{filename}' to '{dest_path}'")
        else:
            self.log_event("ERROR", "UploadEngine", f"{mode} failed for '{filename}': {error}")

    def log_upload_success(self, filename: str, batch_name: str, upload_id: int):
        self.log_event("INFO", "UploadService", f"Upload recorded in MySQL (ID #{upload_id}): '{filename}' mapped to '{batch_name}'")

    def log_upload_failure(self, filename: str, error: str):
        self.log_event("ERROR", "UploadService", f"Upload failed for '{filename}': {error}")

    def log_db_error(self, operation: str, error: str):
        self.log_event("ERROR", "Database", f"Database error during '{operation}': {error}")

    def log_unexpected_error(self, context: str, error: str):
        self.log_event("ERROR", "System", f"Unexpected error in '{context}': {error}")

    def get_recent_logs(self, level: str = None, search: str = None, limit: int = 200):
        """
        Reads, parses, filters, and returns recent log lines from logs/app.log.
        Returns list of dicts: [{ timestamp, level, module, message }]
        """
        if not os.path.exists(self.log_file_path):
            return []

        parsed_entries = []
        pattern = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(?P<level>[A-Z]+)\] \[(?P<module>[^\]]+)\] (?P<message>.*)$")

        try:
            with open(self.log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue

                m = pattern.match(line_str)
                if m:
                    entry_level = m.group("level").upper()
                    entry_module = m.group("module")
                    entry_msg = sanitize_log_message(m.group("message"))
                    timestamp = m.group("timestamp")

                    # Level filter
                    if level and level.upper() != "ALL":
                        if entry_level != level.upper():
                            continue

                    # Keyword search filter
                    if search and search.strip():
                        s_term = search.strip().lower()
                        if (
                            s_term not in entry_msg.lower()
                            and s_term not in entry_module.lower()
                            and s_term not in entry_level.lower()
                        ):
                            continue

                    parsed_entries.append({
                        "timestamp": timestamp,
                        "level": entry_level,
                        "module": entry_module,
                        "message": entry_msg,
                        "raw": line_str,
                    })
                else:
                    # Append unstructured or traceback lines to the previous entry if present
                    if parsed_entries:
                        parsed_entries[-1]["message"] += "\n" + sanitize_log_message(line_str)

        except Exception as exc:
            self.logger.error(f"Error reading app log file: {exc}")

        # Return latest entries first
        parsed_entries.reverse()
        return parsed_entries[:limit]

    def clear_logs(self):
        """Clears/truncates the logs/app.log file."""
        try:
            with open(self.log_file_path, "w", encoding="utf-8") as f:
                f.write("")
            self.log_event("INFO", "LoggingService", "Application logs cleared by user")
            return {"success": True, "message": "Logs cleared successfully"}
        except Exception as exc:
            self.logger.error(f"Failed to clear logs: {exc}")
            return {"success": False, "message": f"Failed to clear logs: {exc}"}


logging_service = LoggingService()
