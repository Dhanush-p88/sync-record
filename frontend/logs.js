/**
 * Logs Page Script - Day 9 Implementation
 * Automated Session Recording Upload System
 *
 * Implements:
 * - Real-time streaming from GET /api/logs
 * - Filtering by INFO, WARNING, ERROR, or ALL
 * - Search by keyword/module with debouncing
 * - Auto-refresh toggle (every 3 seconds)
 * - Clear logs confirmation modal & POST /api/logs/clear
 * - Toast notifications
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const logStreamContainer = document.getElementById("log-stream-container");
  const logCountTag = document.getElementById("log-count-tag");
  const logSearchInput = document.getElementById("log-search-input");
  const btnRefreshLogs = document.getElementById("btn-refresh-logs");
  const autoRefreshCheckbox = document.getElementById("auto-refresh-checkbox");
  const terminalStatus = document.getElementById("terminal-status");
  const toastContainer = document.getElementById("toast-container");

  const filterButtons = document.querySelectorAll(".btn-filter-pill");

  // Modal Elements
  const clearConfirmModal = document.getElementById("clear-confirm-modal");
  const btnOpenClearModal = document.getElementById("btn-open-clear-modal");
  const btnCloseClearModal = document.getElementById("btn-close-clear-modal");
  const btnCancelClear = document.getElementById("btn-cancel-clear");
  const btnConfirmClear = document.getElementById("btn-confirm-clear");

  // Mobile sidebar
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const appSidebar = document.getElementById("app-sidebar");
  if (btnToggleSidebar && appSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      appSidebar.classList.toggle("open");
    });
  }

  // State
  let activeLevel = "ALL";
  let activeSearch = "";
  let autoRefreshInterval = null;
  let debounceTimer = null;

  // Toast Notification Utility
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
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="8"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
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
    setTimeout(() => dismissToast(toast), 4000);
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

  // Fetch & Render Logs
  async function fetchLogs() {
    if (!logStreamContainer) return;

    const params = new URLSearchParams();
    if (activeLevel && activeLevel !== "ALL") {
      params.append("level", activeLevel);
    }
    if (activeSearch.trim()) {
      params.append("search", activeSearch.trim());
    }
    params.append("limit", "300");

    try {
      const res = await fetch(`/api/logs?${params.toString()}`);
      const data = await res.json();

      if (data.status === "success") {
        renderLogs(data.logs || []);
        if (logCountTag) {
          logCountTag.textContent = `${data.total} Log Entr${data.total === 1 ? "y" : "ies"}`;
        }
        if (terminalStatus) {
          terminalStatus.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        }
      }
    } catch (err) {
      console.warn("Failed to fetch application logs:", err);
      if (terminalStatus) {
        terminalStatus.textContent = "Offline / Connection Error";
      }
    }
  }

  function renderLogs(logs) {
    if (!logs || logs.length === 0) {
      logStreamContainer.innerHTML = `
        <div class="empty-log-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 0.75rem; opacity: 0.5;">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <p>No log entries found matching criteria.</p>
          <span class="text-sm">Filter: ${escapeHtml(activeLevel)}${activeSearch ? ` | Search: "${escapeHtml(activeSearch)}"` : ""}</span>
        </div>`;
      return;
    }

    logStreamContainer.innerHTML = logs.map(entry => {
      const level = (entry.level || "INFO").toUpperCase();
      let levelClass = "level-info";
      let rowClass = "";

      if (level === "ERROR") {
        levelClass = "level-error";
        rowClass = "row-error";
      } else if (level === "WARNING") {
        levelClass = "level-warning";
        rowClass = "row-warning";
      } else if (level === "DEBUG") {
        levelClass = "level-debug";
      }

      return `
        <div class="log-row ${rowClass}">
          <span class="log-time">${escapeHtml(entry.timestamp)}</span>
          <span class="log-level-tag ${levelClass}">${escapeHtml(level)}</span>
          <span class="log-module-tag">[${escapeHtml(entry.module)}]</span>
          <span class="log-msg-text">${escapeHtml(entry.message)}</span>
        </div>`;
    }).join("");
  }

  // Level Filter Click Handling
  filterButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      filterButtons.forEach(b => {
        b.classList.remove("active", "filter-info", "filter-warning", "filter-error");
      });

      btn.classList.add("active");
      activeLevel = btn.dataset.level || "ALL";

      if (activeLevel === "INFO") btn.classList.add("filter-info");
      if (activeLevel === "WARNING") btn.classList.add("filter-warning");
      if (activeLevel === "ERROR") btn.classList.add("filter-error");

      fetchLogs();
    });
  });

  // Search Input with Debouncing
  if (logSearchInput) {
    logSearchInput.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        activeSearch = e.target.value;
        fetchLogs();
      }, 300);
    });
  }

  // Auto-Refresh Setup
  function setupAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    if (autoRefreshCheckbox && autoRefreshCheckbox.checked) {
      autoRefreshInterval = setInterval(fetchLogs, 3000);
    }
  }

  if (autoRefreshCheckbox) {
    autoRefreshCheckbox.addEventListener("change", setupAutoRefresh);
  }

  if (btnRefreshLogs) {
    btnRefreshLogs.addEventListener("click", () => {
      fetchLogs();
      showToast("Refreshed", "Log stream updated", "info");
    });
  }

  // Clear Logs Modal Handlers
  if (btnOpenClearModal && clearConfirmModal) {
    btnOpenClearModal.addEventListener("click", () => {
      clearConfirmModal.style.display = "flex";
    });
  }

  function closeClearModal() {
    if (clearConfirmModal) clearConfirmModal.style.display = "none";
  }

  if (btnCloseClearModal) btnCloseClearModal.addEventListener("click", closeClearModal);
  if (btnCancelClear) btnCancelClear.addEventListener("click", closeClearModal);

  if (btnConfirmClear) {
    btnConfirmClear.addEventListener("click", async () => {
      btnConfirmClear.disabled = true;
      btnConfirmClear.textContent = "Clearing...";

      try {
        const res = await fetch("/api/logs/clear", { method: "POST" });
        const data = await res.json();

        if (data.success) {
          showToast("Logs Cleared", "Application log file was successfully truncated", "success");
          closeClearModal();
          await fetchLogs();
        } else {
          showToast("Error", data.message || "Failed to clear logs", "error");
        }
      } catch (err) {
        showToast("Error", "Network error while clearing logs", "error");
      } finally {
        btnConfirmClear.disabled = false;
        btnConfirmClear.textContent = "Yes, Clear Logs";
      }
    });
  }

  // Initial load
  fetchLogs();
  setupAutoRefresh();
});
