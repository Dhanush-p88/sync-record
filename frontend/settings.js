/**
 * Settings Page Logic - Day 8 Implementation
 * Automated Session Recording Upload System
 *
 * Implements:
 * - Load all system settings from GET /api/settings
 * - Save updated settings to POST /api/settings
 * - Reset to defaults handler
 * - Operation mode radio selection sync
 * - Interactive toast notifications
 */

document.addEventListener("DOMContentLoaded", () => {
  const settingsForm = document.getElementById("settings-form");
  const btnReset = document.getElementById("btn-reset-settings");
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const appSidebar = document.getElementById("app-sidebar");
  const toastContainer = document.getElementById("toast-container");

  // Inputs
  const watchFolderInput = document.getElementById("watch-folder-input");
  const uploadRootInput = document.getElementById("upload-root-input");
  const stabilizationTimeInput = document.getElementById("stabilization-time-input");
  const autoStartInput = document.getElementById("auto-start-input");
  const minimizeTrayInput = document.getElementById("minimize-tray-input");
  const supportedExtsInput = document.getElementById("supported-exts-input");
  const ignoredPatternsInput = document.getElementById("ignored-patterns-input");
  const logLevelSelect = document.getElementById("log-level-select");

  // Google Drive inputs
  const gdriveFolderNameInput = document.getElementById("gdrive-folder-name-input");
  const gdriveDestinationFolderInput = document.getElementById("gdrive-destination-folder-input");
  const gdriveDestinationUrlInput = document.getElementById("gdrive-destination-url-input");

  const modeCopyCard = document.getElementById("mode-copy-card");
  const modeMoveCard = document.getElementById("mode-move-card");

  // Defaults definition
  const DEFAULTS = {
    watch_folder: "uploads",
    upload_root: "exports",
    stabilization_time: "5",
    operation_mode: "COPY",
    auto_start_monitoring: "true",
    minimize_to_tray: "false",
    supported_extensions: ".mp4, .avi, .mov, .webm",
    ignored_patterns: "*.tmp, *.part, *.crdownload, .*",
    log_level: "INFO",
    gdrive_folder_name: "meetings",
    gdrive_destination_folder: "G:\\My Drive\\meetings",
    gdrive_destination_url: "https://drive.google.com/drive/folders/1IfrJujHUpRZ-258dZVBBHvwTscdWwK4a?usp=drive_link"
  };

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

  // Mobile sidebar toggle
  if (btnToggleSidebar && appSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      appSidebar.classList.toggle("open");
    });
  }

  // 2. Radio Card selection styling
  function syncModeRadioStyles(selectedVal) {
    if (selectedVal === "MOVE") {
      if (modeMoveCard) modeMoveCard.classList.add("selected");
      if (modeCopyCard) modeCopyCard.classList.remove("selected");
    } else {
      if (modeCopyCard) modeCopyCard.classList.add("selected");
      if (modeMoveCard) modeMoveCard.classList.remove("selected");
    }
  }

  document.querySelectorAll("input[name='operation_mode']").forEach(radio => {
    radio.addEventListener("change", (e) => {
      syncModeRadioStyles(e.target.value);
    });
  });

  // 3. Load Settings from MySQL
  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      if (data.status === "success" && data.settings) {
        populateForm(data.settings);
      } else {
        showToast("Error", data.message || "Failed to load system settings", "error");
      }
    } catch (err) {
      console.error("Error loading settings:", err);
      showToast("Error", "Could not connect to backend server", "error");
    }
  }

  function populateForm(s) {
    if (watchFolderInput) watchFolderInput.value = s.watch_folder || DEFAULTS.watch_folder;
    if (uploadRootInput) uploadRootInput.value = s.upload_root || DEFAULTS.upload_root;
    if (stabilizationTimeInput) stabilizationTimeInput.value = s.stabilization_time || DEFAULTS.stabilization_time;

    const opMode = (s.operation_mode || DEFAULTS.operation_mode).toUpperCase();
    const radioToSelect = document.querySelector(`input[name='operation_mode'][value='${opMode}']`);
    if (radioToSelect) radioToSelect.checked = true;
    syncModeRadioStyles(opMode);

    if (autoStartInput) autoStartInput.checked = (s.auto_start_monitoring === "true" || s.auto_start_monitoring === true);
    if (minimizeTrayInput) minimizeTrayInput.checked = (s.minimize_to_tray === "true" || s.minimize_to_tray === true);

    if (supportedExtsInput) supportedExtsInput.value = s.supported_extensions || DEFAULTS.supported_extensions;
    if (ignoredPatternsInput) ignoredPatternsInput.value = s.ignored_patterns || DEFAULTS.ignored_patterns;
    if (logLevelSelect) logLevelSelect.value = s.log_level || DEFAULTS.log_level;

    if (gdriveFolderNameInput) gdriveFolderNameInput.value = s.gdrive_folder_name || DEFAULTS.gdrive_folder_name;
    if (gdriveDestinationFolderInput) gdriveDestinationFolderInput.value = s.gdrive_destination_folder || DEFAULTS.gdrive_destination_folder;
    if (gdriveDestinationUrlInput) gdriveDestinationUrlInput.value = s.gdrive_destination_url || DEFAULTS.gdrive_destination_url;
  }

  // 4. Save Settings to MySQL
  if (settingsForm) {
    settingsForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const selectedRadio = document.querySelector("input[name='operation_mode']:checked");
      const payload = {
        watch_folder: watchFolderInput.value.trim(),
        upload_root: uploadRootInput.value.trim(),
        stabilization_time: stabilizationTimeInput.value.trim(),
        operation_mode: selectedRadio ? selectedRadio.value : "COPY",
        auto_start_monitoring: autoStartInput.checked ? "true" : "false",
        minimize_to_tray: minimizeTrayInput.checked ? "true" : "false",
        supported_extensions: supportedExtsInput.value.trim(),
        ignored_patterns: ignoredPatternsInput.value.trim(),
        log_level: logLevelSelect.value,
        gdrive_folder_name: gdriveFolderNameInput ? gdriveFolderNameInput.value.trim() : "meetings",
        gdrive_destination_folder: gdriveDestinationFolderInput ? gdriveDestinationFolderInput.value.trim() : "G:\\My Drive\\meetings",
        gdrive_destination_url: gdriveDestinationUrlInput ? gdriveDestinationUrlInput.value.trim() : "",
      };

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.status === "success") {
          showToast("Settings Saved", "All configuration changes have been persisted to MySQL.", "success");
        } else {
          showToast("Error", data.message || "Failed to update settings", "error");
        }
      } catch (err) {
        showToast("Error", "Network error while saving settings", "error");
      }
    });
  }

  // 5. Reset to Defaults
  if (btnReset) {
    btnReset.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to reset all settings to system defaults?")) return;

      populateForm(DEFAULTS);

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(DEFAULTS),
        });
        const data = await res.json();
        if (data.status === "success") {
          showToast("Reset Complete", "All settings restored to system defaults.", "info");
        }
      } catch (err) {
        showToast("Error", "Failed to save reset settings", "error");
      }
    });
  }

  // Initial load
  loadSettings();
});
