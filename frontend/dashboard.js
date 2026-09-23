/**
 * Dashboard Logic - Day 8 Implementation
 * Automated Session Recording Upload System
 *
 * Implements:
 * - Immediate Monitoring Controls: Start, Pause, Resume, Stop
 * - Real MySQL Statistics Cards
 * - Live Current Processing Queue Table
 * - Live Recent Completed Uploads Table
 * - Immediate Status Badges (Running, Paused, Stopped, Processing, Uploaded, Failed, Unknown Batch, Pending)
 * - Auto-refresh without page reload (every 2.5s)
 * - Toast feedback and sidebar mobile toggle
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const appSidebar = document.getElementById("app-sidebar");
  const systemTimeEl = document.getElementById("system-time");
  const overallStatusEl = document.getElementById("overall-status");
  const refreshBtn = document.getElementById("refresh-btn");
  const toastContainer = document.getElementById("toast-container");

  // Stat Counters
  const statTotal = document.getElementById("stat-total-recordings");
  const statSuccess = document.getElementById("stat-successful-uploads");
  const statFailed = document.getElementById("stat-failed-uploads");
  const statPending = document.getElementById("stat-pending");
  const statUnknown = document.getElementById("stat-unknown-batch");

  // Monitoring elements
  const monitorBadge = document.getElementById("monitor-badge");
  const monitorStateText = document.getElementById("monitor-state-text");
  const watchFolderPath = document.getElementById("watch-folder-path");
  const uploadRootPath = document.getElementById("upload-root-path");
  const btnToggleMode = document.getElementById("btn-toggle-mode");
  const modeBadgePill = document.getElementById("mode-badge-pill");
  const monitorControlMsg = document.getElementById("monitor-control-msg");

  const btnStart = document.getElementById("btn-start-monitor");
  const btnPause = document.getElementById("btn-pause-monitor");
  const btnResume = document.getElementById("btn-resume-monitor");
  const btnStop = document.getElementById("btn-stop-monitor");

  // Tables
  const queueTbody = document.getElementById("queue-tbody");
  const queueTotalTag = document.getElementById("queue-total-tag");
  const recentUploadsTbody = document.getElementById("recent-uploads-tbody");

  let currentOpMode = "COPY";
  let isActionInProgress = false;

  // Day 9 Notification Tracking
  const seenUploadIds = new Set();
  const seenUnknownQueueIds = new Set();
  const seenFailedQueueIds = new Set();
  let isInitialLoad = true;
  let hasShownDbError = false;

  // 1. Toast Notification Utility
  function showToast(title, message, type = "success") {
    if (!toastContainer) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    let iconSvg = "";
    if (type === "success") {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === "error") {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="8"></line></svg>`;
    }

    toast.innerHTML = `
      <div class="toast-icon">${iconSvg}</div>
      <div class="toast-body">
        <div class="toast-title">${escapeHtml(title)}</div>
        <div class="toast-message">${escapeHtml(message)}</div>
      </div>
      <button class="toast-close">&times;</button>
    `;

    toast.querySelector(".toast-close").addEventListener("click", () => {
      dismissToast(toast);
    });

    toastContainer.appendChild(toast);

    setTimeout(() => {
      dismissToast(toast);
    }, 4000);
  }

  function dismissToast(toast) {
    toast.classList.add("toast-hiding");
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function formatTimestamp(isoStr) {
    if (!isoStr) return "-";
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleTimeString() + " " + d.toLocaleDateString();
    } catch {
      return isoStr;
    }
  }

  // Mobile sidebar toggle
  if (btnToggleSidebar && appSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      appSidebar.classList.toggle("open");
    });
  }

  // Update Clock
  function updateTime() {
    if (systemTimeEl) {
      systemTimeEl.textContent = new Date().toLocaleTimeString();
    }
  }
  setInterval(updateTime, 1000);
  updateTime();

  // 2. Status Badge Helper
  function getStatusBadgeHtml(status) {
    if (!status) return `<span class="badge-status badge-stopped">Unknown</span>`;
    const s = status.trim();

    switch (s.toLowerCase()) {
      case "running":
        return `<span class="badge-status badge-running">&#9679; Running</span>`;
      case "paused":
        return `<span class="badge-status badge-paused">&#10074;&#10074; Paused</span>`;
      case "stopped":
        return `<span class="badge-status badge-stopped">&#9632; Stopped</span>`;
      case "processing":
      case "ready":
      case "batch identified":
      case "validated":
        return `<span class="badge-status badge-processing">&#9881; Processing</span>`;
      case "uploaded":
      case "completed":
        return `<span class="badge-status badge-uploaded">&#10003; Uploaded</span>`;
      case "failed":
      case "validation failed":
        return `<span class="badge-status badge-failed">&#9888; Failed</span>`;
      case "unknown batch":
        return `<span class="badge-status badge-unknown">&#63; Unknown Batch</span>`;
      case "pending":
      case "stabilizing":
        return `<span class="badge-status badge-pending">&#9203; Pending</span>`;
      default:
        return `<span class="badge-status badge-stopped">${escapeHtml(s)}</span>`;
    }
  }

  // 3. Update Monitoring UI Immediately
  function applyMonitoringState(state) {
    const s = (state || "STOPPED").toUpperCase();
    if (monitorStateText) monitorStateText.textContent = s;

    if (monitorBadge) {
      if (s === "RUNNING") {
        monitorBadge.className = "badge-status badge-running";
        monitorBadge.innerHTML = "&#9679; RUNNING";
      } else if (s === "PAUSED") {
        monitorBadge.className = "badge-status badge-paused";
        monitorBadge.innerHTML = "&#10074;&#10074; PAUSED";
      } else {
        monitorBadge.className = "badge-status badge-stopped";
        monitorBadge.innerHTML = "&#9632; STOPPED";
      }
    }

    // Toggle button enabled states
    if (btnStart) btnStart.disabled = (s === "RUNNING");
    if (btnPause) btnPause.disabled = (s !== "RUNNING");
    if (btnResume) btnResume.disabled = (s !== "PAUSED");
    if (btnStop) btnStop.disabled = (s === "STOPPED");
  }

  // 4. Monitoring Action Handler
  async function handleMonitorAction(action, url, label) {
    if (isActionInProgress) return;
    isActionInProgress = true;

    if (monitorControlMsg) {
      monitorControlMsg.textContent = `${label}...`;
      monitorControlMsg.style.color = "#38bdf8";
    }

    try {
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();

      if (data.status) {
        applyMonitoringState(data.status);
      } else if (data.success && action === "start") {
        applyMonitoringState("RUNNING");
      }

      if (data.success || data.status === "RUNNING" || data.status === "PAUSED" || data.status === "STOPPED") {
        showToast("Monitor Updated", data.message || `Monitoring ${action} succeeded`, "success");
        if (monitorControlMsg) {
          monitorControlMsg.textContent = data.message || `Monitoring ${action} complete`;
          monitorControlMsg.style.color = "#10b981";
        }
      } else {
        showToast("Monitor Error", data.message || `Failed to ${action} monitor`, "error");
        if (monitorControlMsg) {
          monitorControlMsg.textContent = data.message || `Error during ${action}`;
          monitorControlMsg.style.color = "#fb7185";
        }
      }
    } catch (err) {
      showToast("Error", `Network error while attempting to ${action} monitor`, "error");
      if (monitorControlMsg) {
        monitorControlMsg.textContent = "Network error";
        monitorControlMsg.style.color = "#fb7185";
      }
    } finally {
      isActionInProgress = false;
      // Refresh state from server
      await fetchMonitoringStatus();
    }
  }

  if (btnStart) btnStart.addEventListener("click", () => handleMonitorAction("start", "/api/monitor/start", "Starting monitoring"));
  if (btnPause) btnPause.addEventListener("click", () => handleMonitorAction("pause", "/api/monitor/pause", "Pausing monitoring"));
  if (btnResume) btnResume.addEventListener("click", () => handleMonitorAction("resume", "/api/monitor/resume", "Resuming monitoring"));
  if (btnStop) btnStop.addEventListener("click", () => handleMonitorAction("stop", "/api/monitor/stop", "Stopping monitoring"));

  // 5. Operation Mode Toggle Handler
  if (btnToggleMode) {
    btnToggleMode.addEventListener("click", async () => {
      const newMode = currentOpMode === "COPY" ? "MOVE" : "COPY";
      try {
        const res = await fetch("/api/settings/mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation_mode: newMode })
        });
        const data = await res.json();
        if (data.status === "success" && data.operation_mode) {
          currentOpMode = data.operation_mode;
          applyOperationMode(currentOpMode);
          showToast("Operation Mode Changed", `Mode updated to ${currentOpMode}`, "info");
        }
      } catch (err) {
        showToast("Error", "Could not toggle operation mode", "error");
      }
    });
  }

  function applyOperationMode(mode) {
    currentOpMode = mode || "COPY";
    if (modeBadgePill) {
      modeBadgePill.textContent = `${currentOpMode} MODE`;
      if (currentOpMode === "MOVE") {
        modeBadgePill.className = "badge";
        modeBadgePill.style.background = "rgba(168, 85, 247, 0.2)";
        modeBadgePill.style.color = "#c084fc";
        modeBadgePill.style.borderColor = "rgba(168, 85, 247, 0.4)";
      } else {
        modeBadgePill.className = "badge badge-online";
        modeBadgePill.style.background = "";
        modeBadgePill.style.color = "";
        modeBadgePill.style.borderColor = "";
      }
    }
  }

  // 6. Fetch Real MySQL Dashboard Stats
  async function fetchDashboardStats() {
    try {
      const res = await fetch("/api/dashboard/stats");
      const data = await res.json();
      if (data.status === "success" && data.stats) {
        const s = data.stats;
        if (statTotal) statTotal.textContent = s.total_recordings || 0;
        if (statSuccess) statSuccess.textContent = s.successful_uploads || 0;
        if (statFailed) statFailed.textContent = s.failed_uploads || 0;
        if (statPending) statPending.textContent = s.pending || 0;
        if (statUnknown) statUnknown.textContent = s.unknown_batch || 0;
      }
    } catch (err) {
      console.warn("Could not fetch dashboard stats:", err);
    }
  }

  // 7. Fetch Monitoring Status & Queue
  async function fetchMonitoringStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();

      applyMonitoringState(data.status);

      if (data.watch_folder && watchFolderPath) {
        watchFolderPath.textContent = data.watch_folder;
      }
      if (data.upload_root && uploadRootPath) {
        uploadRootPath.textContent = data.upload_root;
      }
      if (data.operation_mode) {
        applyOperationMode(data.operation_mode);
      }

      renderQueueTable(data.recent_files || []);

      // Proactive Notification Dispatch for Queue Events
      const items = data.recent_files || [];
      items.forEach(item => {
        if (!isInitialLoad) {
          if (item.status === "Unknown Batch" && !seenUnknownQueueIds.has(item.id)) {
            showToast(
              "Unknown Batch",
              `File '${item.file_name}' detected but no configured batch pattern matched`,
              "warning"
            );
          } else if (item.status === "Failed" && !seenFailedQueueIds.has(item.id)) {
            showToast(
              "Upload Failed",
              `File '${item.file_name}': ${item.error_message || 'Validation or transfer failed'}`,
              "error"
            );
          }
        }
        if (item.status === "Unknown Batch") seenUnknownQueueIds.add(item.id);
        if (item.status === "Failed") seenFailedQueueIds.add(item.id);
      });
    } catch (err) {
      console.warn("Could not fetch monitoring status:", err);
    }
  }

  function renderQueueTable(items) {
    if (!queueTbody) return;
    if (queueTotalTag) queueTotalTag.textContent = `${items.length} Queue Item${items.length === 1 ? "" : "s"}`;

    if (!items || items.length === 0) {
      queueTbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="7">
            <div class="empty-state">
              <p>Queue is currently empty.</p>
              <span>Drop recording files (.mp4, .avi, .mov, .webm) into the Watch Folder to begin.</span>
            </div>
          </td>
        </tr>`;
      return;
    }

    queueTbody.innerHTML = items.map(item => {
      const batchName = item.detected_batch || "Unknown";
      const sizeDisplay = formatBytes(item.file_size);
      const timeDisplay = formatTimestamp(item.detected_time || item.created_at);
      const statusBadge = getStatusBadgeHtml(item.status);

      return `
        <tr>
          <td class="mono font-semibold text-muted">#${item.id}</td>
          <td>
            <div class="file-cell" title="${escapeHtml(item.file_path || item.file_name)}">
              <span class="file-name-text">${escapeHtml(item.file_name)}</span>
            </div>
          </td>
          <td>
            <span class="batch-badge">${escapeHtml(batchName)}</span>
          </td>
          <td class="mono">${sizeDisplay}</td>
          <td class="text-muted text-sm">${escapeHtml(timeDisplay)}</td>
          <td>${statusBadge}</td>
          <td>
            <button class="btn-action-play" onclick="window.playQueueVideo(${item.id}, '${escapeHtml(item.file_name)}', '${escapeHtml(batchName)}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              Watch
            </button>
          </td>
        </tr>`;
    }).join("");
  }

  // 8. Fetch Recent Completed Uploads
  async function fetchRecentUploads() {
    if (!recentUploadsTbody) return;

    try {
      const res = await fetch("/api/uploads/recent?limit=6");
      const data = await res.json();

      if (data.status === "success" && data.uploads) {
        renderRecentUploadsTable(data.uploads);

        // Proactive Notification Dispatch for Completed/Failed Uploads
        data.uploads.forEach(u => {
          if (!isInitialLoad && !seenUploadIds.has(u.id)) {
            if (u.status === "Uploaded") {
              showToast(
                "Recording Uploaded",
                `Recording '${u.file_name || u.original_file_name}' uploaded successfully to ${u.batch_name || 'batch'}!`,
                "success"
              );
            } else if (u.status === "Failed") {
              showToast(
                "Upload Failed",
                `Recording '${u.original_file_name}': ${u.error_message || 'Processing error'}`,
                "error"
              );
            }
          }
          seenUploadIds.add(u.id);
        });
      }
    } catch (err) {
      console.warn("Could not fetch recent uploads:", err);
    }
  }

  function renderRecentUploadsTable(uploads) {
    if (!uploads || uploads.length === 0) {
      recentUploadsTbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="7">
            <div class="empty-state">
              <p>No recent uploads recorded yet.</p>
            </div>
          </td>
        </tr>`;
      return;
    }

    recentUploadsTbody.innerHTML = uploads.map(u => {
      const batchName = u.batch_name || "Unknown";
      const targetName = u.file_name || "-";
      const sizeDisplay = formatBytes(u.file_size);
      const timeDisplay = (u.upload_date || "") + (u.upload_time ? ` ${u.upload_time}` : "");
      const statusBadge = getStatusBadgeHtml(u.status);

      return `
        <tr>
          <td class="mono font-semibold text-muted">#${u.id}</td>
          <td>
            <span class="batch-badge">${escapeHtml(batchName)}</span>
          </td>
          <td>
            <span class="standardized-pill" title="${escapeHtml(targetName)}">
              ${escapeHtml(targetName)}
            </span>
          </td>
          <td class="mono">${sizeDisplay}</td>
          <td class="text-muted text-sm">${escapeHtml(timeDisplay)}</td>
          <td>${statusBadge}</td>
          <td>
            <button class="btn-action-play" onclick="window.playUploadVideo(${u.id}, '${escapeHtml(targetName)}', '${escapeHtml(batchName)}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
              Watch
            </button>
          </td>
        </tr>`;
    }).join("");
  }

  // 8b. Fetch Google Drive Target Cloud Status
  async function fetchGDriveTargetStatus() {
    try {
      const res = await fetch("/api/gdrive/status");
      const data = await res.json();
      if (data.success) {
        const displayEl = document.getElementById("gdrive-target-display");
        const pathEl = document.getElementById("gdrive-target-path");
        const openLinkEl = document.getElementById("gdrive-open-link");

        if (displayEl && data.folder_name) {
          displayEl.innerHTML = `My Drive &gt; <strong style="color: #38bdf8;">${escapeHtml(data.folder_name)}</strong>`;
        }
        if (pathEl && data.destination_folder) {
          pathEl.textContent = `(${data.destination_folder})`;
        }
        if (openLinkEl && data.folder_url) {
          openLinkEl.href = data.folder_url;
        }
      }
    } catch {
      // Ignore background polling error
    }
  }

  // 9. Full Orchestrated Poll Loop
  async function refreshDashboard() {
    try {
      await Promise.all([
        fetchDashboardStats(),
        fetchMonitoringStatus(),
        fetchRecentUploads(),
        fetchGDriveTargetStatus(),
      ]);
      hasShownDbError = false;
    } catch (err) {
      if (!hasShownDbError) {
        showToast("Database Error", "Unable to connect to database or backend", "error");
        hasShownDbError = true;
      }
    } finally {
      isInitialLoad = false;
    }
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      refreshDashboard();
      showToast("Refreshed", "Dashboard data updated from MySQL", "info");
    });
  }

  // 10. Cloud Drive Sync Integration
  const inputDriveLink = document.getElementById("input-drive-link");
  const btnClearDriveInput = document.getElementById("btn-clear-drive-input");
  const btnPreviewDrive = document.getElementById("btn-preview-drive");
  const btnSyncDrive = document.getElementById("btn-sync-drive");
  const driveFeedbackAlert = document.getElementById("drive-feedback-alert");
  const drivePreviewContainer = document.getElementById("drive-preview-container");
  const driveFolderTitle = document.getElementById("drive-folder-title");
  const driveVideoCountBadge = document.getElementById("drive-video-count-badge");
  const driveVideosGrid = document.getElementById("drive-videos-grid");

  let currentDriveVideos = [];

  function showDriveAlert(msg, type = "error") {
    if (!driveFeedbackAlert) return;
    driveFeedbackAlert.className = `drive-feedback-alert alert-${type}`;
    driveFeedbackAlert.textContent = msg;
    driveFeedbackAlert.style.display = "block";
  }

  function hideDriveAlert() {
    if (driveFeedbackAlert) driveFeedbackAlert.style.display = "none";
  }

  if (inputDriveLink) {
    inputDriveLink.addEventListener("input", () => {
      if (btnClearDriveInput) {
        btnClearDriveInput.style.display = inputDriveLink.value.trim() ? "block" : "none";
      }
      hideDriveAlert();
    });

    inputDriveLink.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const btnQuickAuto = document.getElementById("btn-quick-auto-sync");
        if (btnQuickAuto) btnQuickAuto.click();
        else if (btnPreviewDrive) btnPreviewDrive.click();
      }
    });

    inputDriveLink.addEventListener("paste", () => {
      setTimeout(() => {
        const pastedVal = (inputDriveLink.value || "").trim();
        if (pastedVal && (pastedVal.startsWith("http://") || pastedVal.startsWith("https://") || pastedVal.includes("drive.google.com") || pastedVal.includes("sharepoint.com") || pastedVal.includes("teams.microsoft.com") || pastedVal.includes("1drv.ms"))) {
          showToast("Link Detected", "Auto-scanning recording link...", "info");
          if (btnPreviewDrive) btnPreviewDrive.click();
        }
      }, 150);
    });
  }

  if (btnClearDriveInput) {
    btnClearDriveInput.addEventListener("click", () => {
      if (inputDriveLink) {
        inputDriveLink.value = "";
        btnClearDriveInput.style.display = "none";
        hideDriveAlert();
        if (drivePreviewContainer) drivePreviewContainer.style.display = "none";
      }
    });
  }

  if (btnPreviewDrive) {
    btnPreviewDrive.addEventListener("click", async () => {
      const link = (inputDriveLink ? inputDriveLink.value : "").trim();
      if (!link) {
        showDriveAlert("Please enter or paste a Google Drive folder link or local cloud path.");
        return;
      }

      hideDriveAlert();
      btnPreviewDrive.disabled = true;
      btnPreviewDrive.innerHTML = `
        <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
        </svg>
        Scanning Drive...
      `;

      try {
        const resp = await fetch("/api/drive/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ drive_link: link })
        });
        const data = await resp.json();

        if (!resp.ok || !data.success) {
          showDriveAlert(data.error || "Failed to preview videos from the provided link.", "error");
          showToast("Drive Preview Failed", data.error || "Could not read drive link", "warning");
          if (drivePreviewContainer) drivePreviewContainer.style.display = "none";
          return;
        }

        currentDriveVideos = data.videos || [];
        if (driveFolderTitle) driveFolderTitle.textContent = data.folder_name || "Cloud Folder";
        if (driveVideoCountBadge) driveVideoCountBadge.textContent = `${currentDriveVideos.length} Video${currentDriveVideos.length === 1 ? "" : "s"} Found`;

        if (driveTargetBatch && (data.source_type === "teams_recording" || (data.folder_name && data.folder_name.toLowerCase().includes("teams")))) {
          // Auto-select meetings batch for Teams recordings
          const hasMeetingsOpt = Array.from(driveTargetBatch.options).some(o => o.value.toLowerCase() === "meetings");
          if (hasMeetingsOpt) {
            driveTargetBatch.value = "meetings";
          }
        }

        if (driveVideosGrid) {
          if (currentDriveVideos.length === 0) {
            driveVideosGrid.innerHTML = `
              <div class="empty-state" style="grid-column: 1 / -1; padding: 2rem;">
                <p>No supported recordings (.mp4, .avi, .mov, .webm) found in this Drive folder.</p>
              </div>`;
          } else {
            driveVideosGrid.innerHTML = currentDriveVideos.map(v => {
              const extClean = (v.ext || ".mp4").replace(".", "").toUpperCase();
              const sizeFormatted = v.size ? formatBytes(v.size) : "Cloud Drive Video";
              const batchName = v.batch || "Unknown";
              return `
                <div class="drive-video-card">
                  <div class="drive-video-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                  </div>
                  <div class="drive-video-info">
                    <div class="drive-video-title" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</div>
                    <div class="drive-video-meta-tags">
                      <span class="drive-tag-format">${extClean}</span>
                      <span class="drive-tag-size">${sizeFormatted}</span>
                      <span class="drive-tag-batch">${escapeHtml(batchName)}</span>
                    </div>
                  </div>
                  <div class="drive-card-actions" style="margin-left: auto;">
                    <button class="btn-action-play" title="Watch Recording" onclick="window.playFilePath('uploads/${escapeHtml(v.name)}', '${escapeHtml(v.name)}', '${escapeHtml(batchName)}')">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                      </svg>
                      Watch
                    </button>
                  </div>
                </div>`;
            }).join("");
          }
        }

        if (drivePreviewContainer) drivePreviewContainer.style.display = "block";
        showToast("Drive Inspected", `Found ${currentDriveVideos.length} recording(s) in Drive folder`, "info");

      } catch (err) {
        showDriveAlert(`Connection error: ${err.message}`, "error");
        showToast("Drive Error", "Could not connect to backend drive service", "error");
      } finally {
        btnPreviewDrive.disabled = false;
        btnPreviewDrive.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          Preview Videos
        `;
      }
    });
  }

  const btnQuickAutoSync = document.getElementById("btn-quick-auto-sync");
  if (btnQuickAutoSync) {
    btnQuickAutoSync.addEventListener("click", async () => {
      const link = (inputDriveLink ? inputDriveLink.value : "").trim();
      if (!link) {
        showDriveAlert("Please enter or paste a Teams / SharePoint / Google Drive link.");
        if (inputDriveLink) inputDriveLink.focus();
        return;
      }

      hideDriveAlert();
      btnQuickAutoSync.disabled = true;
      btnQuickAutoSync.innerHTML = `
        <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
        </svg>
        Uploading to Drive...
      `;

      try {
        const targetBatchVal = (driveTargetBatch && driveTargetBatch.value) ? driveTargetBatch.value : "meetings";
        const resp = await fetch("/api/drive/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            drive_link: link,
            target_batch: targetBatchVal
          })
        });
        const data = await resp.json();

        if (!resp.ok || !data.success) {
          showDriveAlert(data.error || "Failed to process recording link.", "error");
          showToast("Upload Failed", data.error || "Could not process link", "error");
          return;
        }

        // Trigger direct cloud mirror to ensure Google Drive Desktop has all files
        fetch("/api/gdrive/upload-direct", {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        }).catch(() => {});

        showDriveAlert(
          "⚡ Success! Ingested and uploaded recording directly to Google Drive target folder!",
          "success"
        );
        showToast("Drive Upload Success", "Recording uploaded to Google Drive folder!", "success");

        refreshDashboard();

      } catch (err) {
        showDriveAlert(`Error: ${err.message}`, "error");
        showToast("Upload Error", err.message, "error");
      } finally {
        btnQuickAutoSync.disabled = false;
        btnQuickAutoSync.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          ⚡ Auto-Upload to Drive
        `;
      }
    });
  }

  const driveTargetBatch = document.getElementById("drive-target-batch");

  async function loadDriveBatches() {
    if (!driveTargetBatch) return;
    try {
      const resp = await fetch("/api/batches");
      const data = await resp.json();
      if (data.status === "success" && data.batches) {
        const activeBatches = data.batches.filter(b => b.is_active);
        const optionsHtml = ['<option value="">Auto-Detect Batch</option>']
          .concat(activeBatches.map(b => `<option value="${escapeHtml(b.batch_name)}">${escapeHtml(b.batch_name)}</option>`))
          .join("");
        driveTargetBatch.innerHTML = optionsHtml;
      }
    } catch (err) {
      console.warn("Could not load batches for drive sync dropdown:", err);
    }
  }
  loadDriveBatches();

  if (btnSyncDrive) {
    btnSyncDrive.addEventListener("click", async () => {
      const link = (inputDriveLink ? inputDriveLink.value : "").trim();
      if (!link) {
        showDriveAlert("Please enter a Drive folder link.");
        return;
      }

      btnSyncDrive.disabled = true;
      btnSyncDrive.innerHTML = `
        <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
        </svg>
        Syncing Records...
      `;

      try {
        const targetBatchVal = driveTargetBatch ? driveTargetBatch.value : null;
        const resp = await fetch("/api/drive/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            drive_link: link,
            file_names: currentDriveVideos.map(v => v.name),
            target_batch: targetBatchVal || null
          })
        });
        const data = await resp.json();

        if (!resp.ok || !data.success) {
          showDriveAlert(data.error || "Failed to sync videos from Drive.", "error");
          showToast("Sync Failed", data.error || "Sync could not be completed", "error");
          return;
        }

        showDriveAlert(data.message || "Successfully synced recordings to Watch Folder!", "success");
        showToast("Sync Successful", `Imported ${data.synced_count} recording(s) into pipeline!`, "success");

        // Refresh dashboard immediately
        refreshDashboard();

      } catch (err) {
        showDriveAlert(`Sync error: ${err.message}`, "error");
        showToast("Sync Error", "Could not complete sync request", "error");
      } finally {
        btnSyncDrive.disabled = false;
        btnSyncDrive.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          Sync Records Now
        `;
      }
    });
  }

  // 11. Video Player Modal Controller
  const videoPlayerModal = document.getElementById("video-player-modal");
  const globalVideoPlayer = document.getElementById("global-video-player");
  const videoModalTitle = document.getElementById("video-modal-title");
  const videoModalBatch = document.getElementById("video-modal-batch");
  const videoModalPath = document.getElementById("video-modal-path");
  const videoModalDownloadLink = document.getElementById("video-modal-download-link");
  const btnCloseVideoModal = document.getElementById("btn-close-video-modal");

  function openVideoPlayer(title, batch, streamUrl, downloadUrl) {
    if (!videoPlayerModal || !globalVideoPlayer) return;

    if (videoModalTitle) videoModalTitle.textContent = title || "Recording Playback";
    if (videoModalBatch) videoModalBatch.textContent = batch || "Session";
    if (videoModalPath) videoModalPath.textContent = streamUrl;

    if (videoModalDownloadLink) {
      videoModalDownloadLink.href = downloadUrl || streamUrl;
      videoModalDownloadLink.download = title || "recording.mp4";
    }

    globalVideoPlayer.src = streamUrl;
    globalVideoPlayer.load();
    globalVideoPlayer.play().catch(() => {});

    videoPlayerModal.style.display = "flex";
  }

  function closeVideoPlayer() {
    if (globalVideoPlayer) {
      globalVideoPlayer.pause();
      globalVideoPlayer.src = "";
    }
    if (videoPlayerModal) {
      videoPlayerModal.style.display = "none";
    }
  }

  if (btnCloseVideoModal) {
    btnCloseVideoModal.addEventListener("click", closeVideoPlayer);
  }

  if (videoPlayerModal) {
    videoPlayerModal.addEventListener("click", (e) => {
      if (e.target === videoPlayerModal) {
        closeVideoPlayer();
      }
    });
  }

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && videoPlayerModal && videoPlayerModal.style.display !== "none") {
      closeVideoPlayer();
    }
  });

  window.playUploadVideo = function(uploadId, title, batch) {
    const streamUrl = `/api/videos/stream?upload_id=${uploadId}`;
    openVideoPlayer(title, batch, streamUrl, streamUrl);
  };

  window.playQueueVideo = function(queueId, title, batch) {
    const streamUrl = `/api/videos/stream?queue_id=${queueId}`;
    openVideoPlayer(title, batch, streamUrl, streamUrl);
  };

  const btnOpenLocalFolder = document.getElementById("btn-open-local-folder");
  if (btnOpenLocalFolder) {
    btnOpenLocalFolder.addEventListener("click", async () => {
      try {
        const resp = await fetch("/api/drive/open-local-folder", { method: "POST" });
        const data = await resp.json();
        if (data.success) {
          showToast("Opened Folder", "Opened exports/meetings folder in File Explorer", "success");
        } else {
          showToast("Open Folder", data.error || "Could not open folder", "warning");
        }
      } catch (err) {
        showToast("Error", "Could not open local folder", "error");
      }
    });
  }

  const btnConnectGoogle = document.getElementById("btn-connect-google");
  if (btnConnectGoogle) {
    btnConnectGoogle.addEventListener("click", async () => {
      try {
        const resp = await fetch("/api/gdrive/auth-url");
        const data = await resp.json();
        if (data.success && data.auth_url) {
          window.location.href = data.auth_url;
        } else {
          showToast("Connection", data.error || "Could not generate Google Auth URL", "warning");
        }
      } catch (err) {
        showToast("Error", err.message, "error");
      }
    });
  }

  const btnUploadDirectGDrive = document.getElementById("btn-upload-direct-gdrive");
  if (btnUploadDirectGDrive) {
    btnUploadDirectGDrive.addEventListener("click", async () => {
      btnUploadDirectGDrive.disabled = true;
      btnUploadDirectGDrive.innerHTML = `
        <svg class="spin-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
        </svg>
        Uploading to Cloud...
      `;

      try {
        const resp = await fetch("/api/gdrive/upload-direct", {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        });
        const data = await resp.json();

        if (resp.ok && data.success) {
          showToast("Cloud Upload Complete", `Uploaded ${data.uploaded_count} video(s) directly to Google Drive!`, "success");
          if (data.folder_url) {
            window.open(data.folder_url, "_blank");
          }
        } else if (data.needs_auth) {
          showToast("Connect Google Account", "Please click 'Connect Google' to authorize doll7365000@gmail.com once.", "warning");
          if (btnConnectGoogle) btnConnectGoogle.click();
        } else {
          showToast("Upload Result", data.error || "Upload completed with notes.", "info");
        }
      } catch (err) {
        showToast("Upload Error", err.message, "error");
      } finally {
        btnUploadDirectGDrive.disabled = false;
        btnUploadDirectGDrive.innerHTML = "⚡ Upload to Drive Cloud";
      }
    });
  }

  // 12. Change Google Drive Target Folder Modal Controller
  const changeFolderModal = document.getElementById("change-folder-modal");
  const btnOpenChangeFolderModal = document.getElementById("btn-open-change-folder-modal");
  const btnCloseFolderModal = document.getElementById("btn-close-folder-modal");
  const btnCancelFolderModal = document.getElementById("btn-cancel-folder-modal");
  const changeFolderForm = document.getElementById("change-folder-form");
  const modalFolderNameInput = document.getElementById("modal-folder-name-input");
  const modalFolderPathInput = document.getElementById("modal-folder-path-input");
  const modalFolderUrlInput = document.getElementById("modal-folder-url-input");

  function openChangeFolderModal() {
    if (!changeFolderModal) return;
    fetch("/api/gdrive/status")
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          if (modalFolderNameInput) modalFolderNameInput.value = data.folder_name || "Meetings (1)";
          if (modalFolderPathInput) modalFolderPathInput.value = data.destination_folder || "G:\\My Drive\\Meetings (1)";
          if (modalFolderUrlInput) modalFolderUrlInput.value = data.folder_url || "";
        }
      })
      .catch(() => {});
    changeFolderModal.style.display = "flex";
  }

  function closeChangeFolderModal() {
    if (changeFolderModal) changeFolderModal.style.display = "none";
  }

  if (btnOpenChangeFolderModal) {
    btnOpenChangeFolderModal.addEventListener("click", openChangeFolderModal);
  }
  if (btnCloseFolderModal) {
    btnCloseFolderModal.addEventListener("click", closeChangeFolderModal);
  }
  if (btnCancelFolderModal) {
    btnCancelFolderModal.addEventListener("click", closeChangeFolderModal);
  }
  if (changeFolderModal) {
    changeFolderModal.addEventListener("click", (e) => {
      if (e.target === changeFolderModal) closeChangeFolderModal();
    });
  }

  document.querySelectorAll(".btn-preset-folder").forEach(btn => {
    btn.addEventListener("click", () => {
      const fName = btn.getAttribute("data-folder");
      const fPath = btn.getAttribute("data-path");
      if (modalFolderNameInput) modalFolderNameInput.value = fName;
      if (modalFolderPathInput) modalFolderPathInput.value = fPath;
    });
  });

  if (changeFolderForm) {
    changeFolderForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const folderName = (modalFolderNameInput ? modalFolderNameInput.value : "").trim();
      const folderPath = (modalFolderPathInput ? modalFolderPathInput.value : "").trim();
      const folderUrl = (modalFolderUrlInput ? modalFolderUrlInput.value : "").trim();

      try {
        const resp = await fetch("/api/gdrive/set-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            folder_name: folderName,
            folder_path: folderPath,
            folder_url: folderUrl
          })
        });
        const data = await resp.json();
        if (data.success) {
          closeChangeFolderModal();
          showToast("Target Folder Changed", `Switched to '${data.folder_name}'!`, "success");
          fetchGDriveTargetStatus();
        } else {
          showToast("Error", data.error || "Failed to update folder", "error");
        }
      } catch (err) {
        showToast("Error", err.message, "error");
      }
    });
  }

  // Initial Load and Auto-Refresh Interval (2.5s)
  refreshDashboard();
  setInterval(refreshDashboard, 2500);
});


