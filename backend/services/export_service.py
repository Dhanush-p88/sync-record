"""
Export Service - Day 9 Implementation
Automated Session Recording Upload System

Generates:
1. Excel Export (uploads_summary.xlsx) using pandas and openpyxl
2. CSV Export (uploads_summary.csv)
Columns:
- S.No
- Batch Name
- Recording Name
- Upload Date
- Upload Time
- File Path
- Size
- Status
Data is fetched live from MySQL 'uploads' table.
"""

import io
import csv
from datetime import datetime
from backend.models import db, Upload


def get_export_rows():
    """
    Fetches real MySQL upload records and formats them for tabular export.
    Columns: S.No, Batch Name, Recording Name, Upload Date, Upload Time, File Path, Size, Status
    """
    uploads = Upload.query.order_by(Upload.id.asc()).all()
    rows = []

    for idx, u in enumerate(uploads, start=1):
        # Format Date and Time
        if u.upload_date:
            date_str = u.upload_date.strftime("%Y-%m-%d")
        elif u.uploaded_at:
            date_str = u.uploaded_at.strftime("%Y-%m-%d")
        else:
            date_str = "-"

        if u.upload_time:
            time_str = str(u.upload_time)
        elif u.uploaded_at:
            time_str = u.uploaded_at.strftime("%H:%M:%S")
        else:
            time_str = "-"

        # Format Size in bytes
        size_val = u.file_size if u.file_size is not None else 0

        rows.append({
            "S.No": idx,
            "Batch Name": u.batch_name or "Unknown",
            "Recording Name": u.file_name or u.original_file_name or "Unknown",
            "Upload Date": date_str,
            "Upload Time": time_str,
            "File Path": u.file_path or "-",
            "Size": size_val,
            "Status": u.status or "Uploaded",
        })

    return rows


class ExportService:
    """Service to handle Excel and CSV exports of upload history."""

    @staticmethod
    def generate_excel_bytes() -> bytes:
        """
        Generates Excel workbook bytes using pandas and openpyxl.
        """
        try:
            import pandas as pd
            rows = get_export_rows()
            df = pd.DataFrame(rows)

            # Ensure correct column order even if rows is empty
            columns = [
                "S.No", "Batch Name", "Recording Name", "Upload Date",
                "Upload Time", "File Path", "Size", "Status"
            ]
            if df.empty:
                df = pd.DataFrame(columns=columns)
            else:
                df = df[columns]

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Uploads Summary")

                # Auto-fit column widths
                worksheet = writer.sheets["Uploads Summary"]
                for col in worksheet.columns:
                    max_len = max(len(str(cell.value or "")) for cell in col)
                    col_letter = col[0].column_letter
                    worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

            buffer.seek(0)
            return buffer.getvalue()

        except ImportError:
            # Fallback to pure openpyxl if pandas is unavailable
            return ExportService._generate_excel_openpyxl_fallback()

    @staticmethod
    def _generate_excel_openpyxl_fallback() -> bytes:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Uploads Summary"

        headers = [
            "S.No", "Batch Name", "Recording Name", "Upload Date",
            "Upload Time", "File Path", "Size", "Status"
        ]
        ws.append(headers)

        rows = get_export_rows()
        for r in rows:
            ws.append([
                r["S.No"], r["Batch Name"], r["Recording Name"], r["Upload Date"],
                r["Upload Time"], r["File Path"], r["Size"], r["Status"]
            ])

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_csv_bytes() -> bytes:
        """
        Generates CSV format bytes containing real MySQL upload history.
        """
        rows = get_export_rows()
        headers = [
            "S.No", "Batch Name", "Recording Name", "Upload Date",
            "Upload Time", "File Path", "Size", "Status"
        ]

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        return buffer.getvalue().encode("utf-8")


export_service = ExportService()
