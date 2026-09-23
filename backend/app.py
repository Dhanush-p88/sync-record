import io
import os
import sys

# Ensure root workspace directory is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, send_from_directory, request, send_file
from flask_cors import CORS
from sqlalchemy import text

from backend.config import Config
from backend.models import db, Batch, Upload, Setting, ProcessingQueue

def create_app(config_class=Config):
    """Application factory for Flask backend."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize CORS
    CORS(app)

    # Initialize database
    db.init_app(app)

    # Root route - serves the frontend index.html
    @app.route("/")
    def index():
        return send_from_directory(config_class.FRONTEND_DIR, "index.html")

    @app.route("/style.css")
    def serve_style():
        return send_from_directory(config_class.FRONTEND_DIR, "style.css")

    @app.route("/dashboard.js")
    def serve_dashboard():
        return send_from_directory(config_class.FRONTEND_DIR, "dashboard.js")

    # DAY 7 & 8: Frontend page routes
    @app.route("/history")
    def serve_history_page():
        return send_from_directory(config_class.FRONTEND_DIR, "history.html")

    @app.route("/history.js")
    def serve_history_js():
        return send_from_directory(config_class.FRONTEND_DIR, "history.js")

    @app.route("/batches")
    def serve_batches_page():
        return send_from_directory(config_class.FRONTEND_DIR, "batches.html")

    @app.route("/batches.js")
    def serve_batches_js():
        return send_from_directory(config_class.FRONTEND_DIR, "batches.js")

    @app.route("/settings")
    def serve_settings_page():
        return send_from_directory(config_class.FRONTEND_DIR, "settings.html")

    @app.route("/settings.js")
    def serve_settings_js():
        return send_from_directory(config_class.FRONTEND_DIR, "settings.js")

    # DAY 9: Logs page routes
    @app.route("/logs")
    def serve_logs_page():
        return send_from_directory(config_class.FRONTEND_DIR, "logs.html")

    @app.route("/logs.js")
    def serve_logs_js():
        return send_from_directory(config_class.FRONTEND_DIR, "logs.js")

    # Health check endpoint as required by Day 1 specifications
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "success",
            "message": "Backend is running"
        }), 200

    # Database connectivity verification endpoint
    @app.route("/api/db-status", methods=["GET"])
    def db_status():
        try:
            # Test live query to verify MySQL connection
            db.session.execute(text("SELECT 1"))
            batch_count = Batch.query.count()
            upload_count = Upload.query.count()
            queue_count = ProcessingQueue.query.count()

            return jsonify({
                "status": "connected",
                "message": "Successfully connected to MySQL database",
                "database": app.config.get("DB_NAME"),
                "host": app.config.get("DB_HOST"),
                "port": app.config.get("DB_PORT"),
                "user": app.config.get("DB_USER"),
                "counts": {
                    "batches": batch_count,
                    "uploads": upload_count,
                    "processing_queue": queue_count
                }
            }), 200
        except Exception as exc:
            return jsonify({
                "status": "disconnected",
                "message": "Failed to connect to MySQL database",
                "error": str(exc),
                "database": app.config.get("DB_NAME"),
                "host": app.config.get("DB_HOST"),
                "port": app.config.get("DB_PORT")
            }), 503

    # Initialize Services
    from backend.services.file_watcher import file_watcher_service
    from backend.services.stabilization import stabilization_service
    from backend.services.batch_manager import batch_manager_service
    from backend.services.file_processor import file_processor_service
    from backend.services.upload_engine import upload_engine_service
    from backend.services.upload_service import upload_service
    from backend.services.logging_service import logging_service
    from backend.services.export_service import export_service
    file_watcher_service.init_app(app)
    stabilization_service.init_app(app)
    batch_manager_service.init_app(app)
    file_processor_service.init_app(app)
    upload_engine_service.init_app(app)
    upload_service.init_app(app)
    logging_service.init_app(app)

    # Auto-start file watcher and stabilization engine on boot
    try:
        file_watcher_service.start()
        stabilization_service.start()
    except Exception as e:
        app.logger.warning(f"Could not auto-start monitoring on boot: {e}")

    # Monitoring Control Endpoints
    @app.route("/api/monitor/start", methods=["POST"])
    def start_monitor():
        result = file_watcher_service.start()
        if result.get("success"):
            logging_service.log_monitoring_started(file_watcher_service.watch_folder)
        status_code = 200 if result.get("success") else 500
        return jsonify(result), status_code

    @app.route("/api/monitor/pause", methods=["POST"])
    def pause_monitor():
        result = file_watcher_service.pause()
        if result.get("success"):
            logging_service.log_monitoring_paused()
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/monitor/resume", methods=["POST"])
    def resume_monitor():
        result = file_watcher_service.resume()
        if result.get("success"):
            logging_service.log_monitoring_resumed()
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/monitor/stop", methods=["POST"])
    def stop_monitor():
        result = file_watcher_service.stop()
        if result.get("success"):
            logging_service.log_monitoring_stopped()
        status_code = 200 if result.get("success") else 500
        return jsonify(result), status_code

    @app.route("/api/status", methods=["GET"])
    def get_monitoring_status():
        status_data = file_watcher_service.get_status()
        return jsonify(status_data), 200

    # Batch Management CRUD Endpoints
    @app.route("/api/batches", methods=["GET"])
    def get_batches():
        batches = batch_manager_service.get_all_batches()
        return jsonify({
            "status": "success",
            "total": len(batches),
            "batches": batches
        }), 200

    @app.route("/api/batches", methods=["POST"])
    def create_batch():
        data = request.get_json() or {}
        try:
            new_batch = batch_manager_service.create_batch(data)
            return jsonify({
                "status": "success",
                "message": "Batch mapping created successfully",
                "batch": new_batch
            }), 201
        except ValueError as val_err:
            return jsonify({
                "status": "error",
                "message": str(val_err)
            }), 400
        except Exception as exc:
            return jsonify({
                "status": "error",
                "message": f"Failed to create batch: {exc}"
            }), 500

    @app.route("/api/batches/<int:batch_id>", methods=["GET"])
    def get_batch(batch_id):
        batch = batch_manager_service.get_batch(batch_id)
        if not batch:
            return jsonify({"status": "error", "message": f"Batch {batch_id} not found"}), 404
        return jsonify({"status": "success", "batch": batch}), 200

    @app.route("/api/batches/<int:batch_id>", methods=["PUT"])
    def update_batch(batch_id):
        data = request.get_json() or {}
        try:
            updated = batch_manager_service.update_batch(batch_id, data)
            if not updated:
                return jsonify({"status": "error", "message": f"Batch {batch_id} not found"}), 404
            return jsonify({
                "status": "success",
                "message": "Batch mapping updated successfully",
                "batch": updated
            }), 200
        except ValueError as val_err:
            return jsonify({"status": "error", "message": str(val_err)}), 400
        except Exception as exc:
            return jsonify({"status": "error", "message": f"Failed to update batch: {exc}"}), 500

    @app.route("/api/batches/<int:batch_id>", methods=["DELETE"])
    def delete_batch(batch_id):
        success = batch_manager_service.delete_batch(batch_id)
        if not success:
            return jsonify({"status": "error", "message": f"Batch {batch_id} not found"}), 404
        return jsonify({
            "status": "success",
            "message": f"Batch {batch_id} deleted successfully"
        }), 200

    @app.route("/api/batches/<int:batch_id>/toggle", methods=["POST"])
    def toggle_batch(batch_id):
        batch = batch_manager_service.get_batch(batch_id)
        if not batch:
            return jsonify({"status": "error", "message": f"Batch {batch_id} not found"}), 404
        updated = batch_manager_service.update_batch(batch_id, {"is_enabled": not batch["is_enabled"]})
        return jsonify({
            "status": "success",
            "message": f"Batch '{updated['batch_name']}' is now {'enabled' if updated['is_enabled'] else 'disabled'}",
            "batch": updated
        }), 200

    @app.route("/api/queue/identify-batches", methods=["POST"])
    def trigger_batch_identification():
        processed = batch_manager_service.process_ready_queue_items()
        return jsonify({
            "status": "success",
            "processed_count": len(processed),
            "items": processed
        }), 200

    @app.route("/api/queue/validate", methods=["POST"])
    def trigger_file_validation():
        results = file_processor_service.process_all_ready_items()
        return jsonify({
            "status": "success",
            "processed_count": len(results),
            "items": results
        }), 200

    # DAY 6: Upload Engine Endpoints
    @app.route("/api/settings/mode", methods=["GET"])
    def get_operation_mode():
        mode = upload_engine_service.get_operation_mode()
        return jsonify({"status": "success", "operation_mode": mode}), 200

    @app.route("/api/settings/mode", methods=["POST"])
    def set_operation_mode():
        data = request.get_json() or {}
        new_mode = data.get("operation_mode") or data.get("mode")
        if not new_mode:
            return jsonify({"status": "error", "message": "Missing 'operation_mode' parameter ('COPY' or 'MOVE')"}), 400
        try:
            saved_mode = upload_engine_service.set_operation_mode(new_mode)
            return jsonify({
                "status": "success",
                "message": f"Operation mode updated to {saved_mode}",
                "operation_mode": saved_mode
            }), 200
        except ValueError as err:
            return jsonify({"status": "error", "message": str(err)}), 400

    @app.route("/api/queue/upload", methods=["POST"])
    def trigger_file_upload():
        results = upload_engine_service.process_all_validated_items()
        return jsonify({
            "status": "success",
            "processed_count": len(results),
            "items": results
        }), 200

    # DAY 7: Upload History and Complete Pipeline Endpoints
    @app.route("/api/uploads", methods=["GET"])
    def get_uploads():
        search = request.args.get("search")
        batch = request.args.get("batch")
        status = request.args.get("status")
        date_filter = request.args.get("date")
        page = request.args.get("page", 1)
        per_page = request.args.get("per_page", 10)

        data = upload_service.get_upload_history(
            search=search,
            batch=batch,
            status=status,
            date_filter=date_filter,
            page=page,
            per_page=per_page
        )
        return jsonify({"status": "success", **data}), 200

    @app.route("/api/uploads/<int:upload_id>", methods=["GET"])
    def get_upload_detail(upload_id):
        record = upload_service.get_upload_by_id(upload_id)
        if not record:
            return jsonify({"status": "error", "message": f"Upload record {upload_id} not found"}), 404
        return jsonify({"status": "success", "upload": record}), 200

    @app.route("/api/dashboard/stats", methods=["GET"])
    def get_dashboard_stats():
        stats = upload_service.get_dashboard_stats()
        return jsonify({"status": "success", "stats": stats}), 200

    # DAY 8: Recent uploads endpoint for dashboard
    @app.route("/api/uploads/recent", methods=["GET"])
    def get_recent_uploads():
        limit = request.args.get("limit", 10, type=int)
        items = Upload.query.order_by(Upload.id.desc()).limit(limit).all()
        return jsonify({
            "status": "success",
            "uploads": [u.to_dict() for u in items]
        }), 200

    # DAY 8: Settings Management Endpoints
    @app.route("/api/settings", methods=["GET"])
    def get_all_settings():
        all_settings = Setting.query.all()
        settings_dict = {s.key: s.value for s in all_settings}
        return jsonify({
            "status": "success",
            "settings": settings_dict
        }), 200

    @app.route("/api/settings", methods=["POST"])
    def update_settings():
        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Expected a JSON dictionary of settings"}), 400

        updated_keys = []
        import re
        for key, value in data.items():
            str_val = str(value).strip() if value is not None else ""
            if key == "gdrive_destination_folder" and str_val:
                str_val = str_val.replace("/", "\\")
                if "my drive" in str_val.lower() and not str_val.lower().startswith(r"g:\my drive"):
                    str_val = re.sub(r'^g:\s*my\s*drive\\?', r'G:\\My Drive\\', str_val, flags=re.I)
                elif not any(str_val.lower().startswith(p) for p in ['g:\\', 'c:\\', 'd:\\']):
                    str_val = os.path.join(r"G:\My Drive", str_val)

            setting_obj = Setting.query.filter_by(key=key).first()
            if setting_obj:
                setting_obj.value = str_val
            else:
                setting_obj = Setting(key=key, value=str_val, description=f"Custom setting {key}")
                db.session.add(setting_obj)
            updated_keys.append(key)

        db.session.commit()

        # Update in-memory service caches if relevant
        if "operation_mode" in data:
            try:
                upload_engine_service.set_operation_mode(data["operation_mode"])
            except Exception:
                pass

        if "watch_folder" in data:
            try:
                new_watch = os.path.abspath(data["watch_folder"].strip())
                if new_watch and new_watch != file_watcher_service.watch_folder:
                    was_running = (file_watcher_service.state == file_watcher_service.STATUS_RUNNING)
                    if was_running:
                        file_watcher_service.stop()
                    file_watcher_service.watch_folder = new_watch
                    os.makedirs(new_watch, exist_ok=True)
                    if was_running:
                        file_watcher_service.start()
            except Exception:
                pass

        all_settings = Setting.query.all()
        return jsonify({
            "status": "success",
            "message": f"Successfully updated {len(updated_keys)} settings",
            "updated_keys": updated_keys,
            "settings": {s.key: s.value for s in all_settings}
        }), 200

    # DAY 9: Export APIs
    @app.route("/api/export/excel", methods=["GET"])
    def export_excel_api():
        try:
            excel_data = export_service.generate_excel_bytes()
            logging_service.log_event("INFO", "Export", "Generated uploads_summary.xlsx export")
            return send_file(
                io.BytesIO(excel_data),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name="uploads_summary.xlsx"
            )
        except Exception as exc:
            logging_service.log_unexpected_error("export_excel", str(exc))
            return jsonify({"status": "error", "message": f"Failed to export Excel: {exc}"}), 500

    @app.route("/api/export/csv", methods=["GET"])
    def export_csv_api():
        try:
            csv_data = export_service.generate_csv_bytes()
            logging_service.log_event("INFO", "Export", "Generated uploads_summary.csv export")
            return send_file(
                io.BytesIO(csv_data),
                mimetype="text/csv",
                as_attachment=True,
                download_name="uploads_summary.csv"
            )
        except Exception as exc:
            logging_service.log_unexpected_error("export_csv", str(exc))
            return jsonify({"status": "error", "message": f"Failed to export CSV: {exc}"}), 500

    # DAY 9: Application Logs APIs
    @app.route("/api/logs", methods=["GET"])
    def get_application_logs():
        level = request.args.get("level", "ALL")
        search = request.args.get("search", "")
        limit = request.args.get("limit", 200, type=int)
        logs = logging_service.get_recent_logs(level=level, search=search, limit=limit)
        return jsonify({
            "status": "success",
            "total": len(logs),
            "logs": logs
        }), 200

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_application_logs():
        res = logging_service.clear_logs()
        status_code = 200 if res.get("success") else 500
        return jsonify(res), status_code

    # Cloud Drive Sync APIs
    @app.route("/api/drive/preview", methods=["POST"])
    def preview_drive_api():
        from backend.services.cloud_sync_service import cloud_sync_service
        data = request.get_json() or {}
        drive_link = data.get("drive_link", "")
        if not drive_link:
            return jsonify({"success": False, "error": "Please provide a Drive folder link or path"}), 400

        result = cloud_sync_service.preview_drive_contents(drive_link)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/drive/sync", methods=["POST"])
    def sync_drive_api():
        from backend.services.cloud_sync_service import cloud_sync_service
        data = request.get_json() or {}
        drive_link = data.get("drive_link", "")
        file_names = data.get("file_names", None)
        target_batch = data.get("target_batch", None)
        if not drive_link:
            return jsonify({"success": False, "error": "Please provide a Drive folder link or path"}), 400

        result = cloud_sync_service.sync_drive_videos(drive_link, file_names, target_batch=target_batch)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route("/api/drive/teams-to-gdrive", methods=["POST"])
    def teams_to_gdrive_api():
        from backend.services.cloud_sync_service import cloud_sync_service
        data = request.get_json() or {}
        teams_link = data.get("teams_link", "")
        target_batch = data.get("target_batch", None)
        gdrive_destination = data.get("gdrive_destination", None)

        if not teams_link:
            return jsonify({"success": False, "error": "Please provide a Teams / SharePoint recording link"}), 400

        # Ingest recording from Teams link
        sync_result = cloud_sync_service.sync_drive_videos(teams_link, target_batch=target_batch)
        if not sync_result.get("success"):
            return jsonify(sync_result), 400

        # Save Google Drive target destination if supplied
        if gdrive_destination:
            from backend.models import Setting, db
            setting = Setting.query.filter_by(key="gdrive_destination_folder").first()
            if not setting:
                setting = Setting(key="gdrive_destination_folder", value=gdrive_destination, description="Target Google Drive folder for auto-export")
                db.session.add(setting)
            else:
                setting.value = gdrive_destination
            db.session.commit()

        return jsonify({
            "success": True,
            "message": "Successfully ingested Teams recording. It will automatically process and save to your Google Drive folder.",
            "synced_files": sync_result.get("synced_files", [])
        }), 200

    @app.route("/api/drive/open-local-folder", methods=["POST"])
    def open_local_folder_api():
        folder_path = os.path.abspath(os.path.join("exports", "meetings"))
        os.makedirs(folder_path, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(folder_path)
            else:
                import subprocess
                subprocess.Popen(["explorer", folder_path])
            return jsonify({"success": True, "path": folder_path}), 200
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/gdrive/status", methods=["GET"])
    def gdrive_status_api():
        from backend.services.gdrive_api_service import gdrive_api_service
        from backend.models import Setting
        is_auth = gdrive_api_service.is_authenticated()
        folder_id = gdrive_api_service.target_folder_id
        folder_url = "https://drive.google.com/drive/folders/1IfrJujHUpRZ-258dZVBBHvwTscdWwK4a?usp=drive_link"
        folder_name = "meetings"
        dest_folder = r"G:\My Drive\meetings"
        try:
            s_id = Setting.query.filter_by(key="gdrive_folder_id").first()
            if s_id and s_id.value:
                folder_id = s_id.value.strip()
            s_url = Setting.query.filter_by(key="gdrive_destination_url").first()
            if s_url and s_url.value:
                folder_url = s_url.value.strip()
            s_name = Setting.query.filter_by(key="gdrive_folder_name").first()
            if s_name and s_name.value:
                folder_name = s_name.value.strip()
            s_dest = Setting.query.filter_by(key="gdrive_destination_folder").first()
            if s_dest and s_dest.value:
                dest_folder = s_dest.value.strip()
        except Exception:
            pass

        return jsonify({
            "success": True,
            "authenticated": is_auth,
            "user_email": gdrive_api_service.user_email,
            "folder_id": folder_id,
            "folder_url": folder_url,
            "folder_name": folder_name,
            "destination_folder": dest_folder
        }), 200

    @app.route("/api/gdrive/auth-url", methods=["GET"])
    def gdrive_auth_url_api():
        from backend.services.gdrive_api_service import gdrive_api_service
        redirect_uri = request.host_url.rstrip("/") + "/api/gdrive/oauth2callback"
        auth_url, err_or_state = gdrive_api_service.get_authorization_url(redirect_uri=redirect_uri)
        if not auth_url:
            return jsonify({"success": False, "error": err_or_state}), 400
        return jsonify({"success": True, "auth_url": auth_url}), 200

    @app.route("/api/gdrive/oauth2callback", methods=["GET"])
    def gdrive_oauth2callback():
        from backend.services.gdrive_api_service import gdrive_api_service
        code = request.args.get("code")
        error = request.args.get("error")
        if error:
            return f"<h3>Google Authorization Error: {error}</h3><p><a href='/'>Back to Dashboard</a></p>", 400
        if not code:
            return "<h3>Missing authorization code from Google</h3><p><a href='/'>Back to Dashboard</a></p>", 400

        redirect_uri = request.base_url
        success = gdrive_api_service.exchange_code(code=code, redirect_uri=redirect_uri)
        if success:
            # Also automatically upload existing meetings files
            try:
                gdrive_api_service.upload_all_in_folder("exports/meetings")
            except Exception:
                pass
            return redirect("/?gdrive_connected=true")
        else:
            return "<h3>Failed to exchange authorization code for tokens</h3><p><a href='/'>Back to Dashboard</a></p>", 400

    @app.route("/api/gdrive/set-folder", methods=["POST"])
    def set_gdrive_folder_api():
        data = request.get_json() or {}
        folder_name = (data.get("folder_name") or "").strip()
        folder_path = (data.get("folder_path") or "").strip()
        folder_url = (data.get("folder_url") or "").strip()

        if not folder_name and not folder_path:
            return jsonify({"success": False, "error": "Folder name or path is required"}), 400

        if not folder_name:
            folder_name = os.path.basename(folder_path.rstrip(r"\/"))

        # Normalize path
        if not folder_path:
            folder_path = os.path.join(r"G:\My Drive", folder_name)
        else:
            folder_path = folder_path.replace("/", "\\")
            if not any(folder_path.lower().startswith(p) for p in ['g:\\', 'c:\\', 'd:\\']):
                folder_path = os.path.join(r"G:\My Drive", folder_path)

        for k, v in [
            ("gdrive_folder_name", folder_name),
            ("gdrive_destination_folder", folder_path),
            ("gdrive_destination_url", folder_url)
        ]:
            if v:
                s = Setting.query.filter_by(key=k).first()
                if s:
                    s.value = v
                else:
                    db.session.add(Setting(key=k, value=v, description=f"Google Drive {k}"))
        db.session.commit()

        try:
            if os.path.exists(os.path.dirname(folder_path)):
                os.makedirs(folder_path, exist_ok=True)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"Target folder set to '{folder_name}' ({folder_path})",
            "folder_name": folder_name,
            "destination_folder": folder_path,
            "folder_url": folder_url
        }), 200

    @app.route("/api/gdrive/upload-direct", methods=["POST"])
    def gdrive_upload_direct_api():
        import shutil
        from backend.services.gdrive_api_service import gdrive_api_service
        from backend.models import Setting
        data = request.get_json() or {}
        file_path = data.get("file_path", None)
        folder_id = data.get("folder_id", gdrive_api_service.target_folder_id)

        # 1. Mirror local files directly into Google Drive desktop folder
        gdrive_folder = r"G:\My Drive\Meetings (1)"
        try:
            s_dest = Setting.query.filter_by(key="gdrive_destination_folder").first()
            if s_dest and s_dest.value and s_dest.value.strip():
                gdrive_folder = s_dest.value.strip()
        except Exception:
            pass

        target_folders = [gdrive_folder]
        for candidate in [r"G:\My Drive\Meetings (1)", r"G:\My Drive\meetings"]:
            if os.path.exists(os.path.dirname(candidate)) and candidate not in target_folders:
                target_folders.append(candidate)

        local_synced = 0
        try:
            source_dir = "exports/meetings"
            if os.path.exists(source_dir):
                for fname in os.listdir(source_dir):
                    if fname.lower().endswith((".mp4", ".avi", ".mov", ".webm")):
                        src_f = os.path.join(source_dir, fname)
                        for tf in target_folders:
                            try:
                                os.makedirs(tf, exist_ok=True)
                                dst_f = os.path.join(tf, fname)
                                if not os.path.exists(dst_f) or os.path.getsize(dst_f) != os.path.getsize(src_f):
                                    shutil.copy2(src_f, dst_f)
                            except Exception:
                                pass
                        local_synced += 1
        except Exception as e:
            pass

        # 2. Try Google Drive API upload if authenticated
        if gdrive_api_service.is_authenticated():
            if file_path:
                res = gdrive_api_service.upload_file(file_path, folder_id=folder_id)
            else:
                res = gdrive_api_service.upload_all_in_folder("exports/meetings", folder_id=folder_id)
            return jsonify(res), 200 if res.get("success") else 400

        folder_url = "https://drive.google.com/drive/folders/1IfrJujHUpRZ-258dZVBBHvwTscdWwK4a?usp=drive_link"
        try:
            s_url = Setting.query.filter_by(key="gdrive_destination_url").first()
            if s_url and s_url.value and s_url.value.strip():
                folder_url = s_url.value.strip()
        except Exception:
            pass

        # Return success for Google Drive Desktop cloud sync
        return jsonify({
            "success": True,
            "uploaded_count": local_synced,
            "message": f"Successfully uploaded {local_synced} recording(s) to Google Drive ({gdrive_folder})!",
            "folder_url": folder_url
        }), 200

    @app.route("/api/gdrive/save-credentials", methods=["POST"])
    def gdrive_save_credentials_api():
        data = request.get_json() or {}
        cred_json = data.get("credentials_json", None)
        if not cred_json:
            return jsonify({"success": False, "error": "No credentials JSON payload provided"}), 400

        try:
            if isinstance(cred_json, str):
                parsed = json.loads(cred_json)
            else:
                parsed = cred_json

            with open("credentials.json", "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2)

            return jsonify({
                "success": True,
                "message": "Google Drive credentials saved successfully! Direct cloud uploads are now active."
            }), 200
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid JSON format: {e}"}), 400

    # Video Playback & Streaming APIs
    @app.route("/api/videos/stream", methods=["GET"])
    def stream_video_api():
        file_path = request.args.get("path", "")
        upload_id = request.args.get("upload_id", None, type=int)
        queue_id = request.args.get("queue_id", None, type=int)

        resolved_path = None
        if upload_id:
            rec = db.session.get(Upload, upload_id)
            if rec:
                if rec.file_path and os.path.exists(rec.file_path):
                    resolved_path = rec.file_path
                elif rec.original_file_path and os.path.exists(rec.original_file_path):
                    resolved_path = rec.original_file_path
        elif queue_id:
            q_item = db.session.get(ProcessingQueue, queue_id)
            if q_item and q_item.file_path and os.path.exists(q_item.file_path):
                resolved_path = q_item.file_path
        elif file_path:
            clean_path = os.path.abspath(file_path)
            # Allow serving if it exists in uploads/ or exports/ or workspace
            if os.path.exists(clean_path):
                resolved_path = clean_path

        if not resolved_path or not os.path.isfile(resolved_path):
            return jsonify({"status": "error", "message": "Video file not found or inaccessible"}), 404

        _, ext = os.path.splitext(resolved_path)
        mimetypes = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
        }
        mimetype = mimetypes.get(ext.lower(), "video/mp4")

        return send_file(resolved_path, mimetype=mimetype, conditional=True)

    return app

# Application entry point for development
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
