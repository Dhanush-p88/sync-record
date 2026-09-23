/**
 * History Dashboard Script - Day 7 Implementation
 * Automated Session Recording Upload System
 *
 * Handles:
 * - Fetching and rendering upload history from GET /api/uploads
 * - Search by filename/batch with debouncing
 * - Filtering by batch, status, and upload date
 * - Server-side pagination
 * - Detailed upload view modal from GET /api/uploads/<id>
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const searchInput = document.getElementById("search-input");
  const batchFilter = document.getElementById("batch-filter");
  const statusFilter = document.getElementById("status-filter");
  const dateFilter = document.getElementById("date-filter");
  const btnClearFilters = document.getElementById("btn-clear-filters");
  const btnRefresh = document.getElementById("btn-refresh-history");
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const appSidebar = document.getElementById("app-sidebar");

  if (btnToggleSidebar && appSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      appSidebar.classList.toggle("open");
    });
  }

  const historyTbody = document.getElementById("history-tbody");
  const historyTotalTag = document.getElementById("history-total-tag");
  const paginationInfo = document.getElementById("pagination-info");
  const pageIndicator = document.getElementById("page-indicator");
  const btnPrevPage = document.getElementById("btn-prev-page");
  const btnNextPage = document.getElementById("btn-next-page");

  // Modal Elements
  const detailModal = document.getElementById("detail-modal");
  const modalContent = document.getElementById("modal-content");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnModalDismiss = document.getElementById("btn-modal-dismiss");

  // State
  let currentPage = 1;
  const perPage = 10;
  let totalPages = 1;
  let totalRecords = 0;
  let debounceTimer = null;

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

  // 1. Populate Batch Filter Dropdown
  async function loadBatches() {
    try {
      const res = await fetch("/api/batches");
      const data = await res.json();
      if (data.status === "success" && data.batches) {
        batchFilter.innerHTML = `<option value="all">All Batches</option>`;
        data.batches.forEach(b => {
          const opt = document.createElement("option");
          opt.value = b.batch_name;
          opt.textContent = b.batch_name;
          batchFilter.appendChild(opt);
        });
      }
    } catch (err) {
      console.warn("Could not load batches for filter:", err);
    }
  }

  // 2. Fetch Upload History
  async function loadUploadHistory() {
    const searchVal = (searchInput ? searchInput.value : "").trim();
    const batchVal = batchFilter ? batchFilter.value : "all";
    const statusVal = statusFilter ? statusFilter.value : "all";
    const dateVal = dateFilter ? dateFilter.value : "";

    const params = new URLSearchParams({
      page: currentPage,
      per_page: perPage,
    });

    if (searchVal) params.append("search", searchVal);
    if (batchVal && batchVal !== "all") params.append("batch", batchVal);
    if (statusVal && statusVal !== "all") params.append("status", statusVal);
    if (dateVal) params.append("date", dateVal);

    try {
      historyTbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="8">
            <div class="empty-state">
              <p>Loading upload records...</p>
            </div>
          </td>
        </tr>`;

      const res = await fetch(`/api/uploads?${params.toString()}`);
      const data = await res.json();

      if (data.status === "success") {
        totalRecords = data.total || 0;
        totalPages = data.pages || 1;
        currentPage = data.page || 1;

        renderTable(data.items || []);
        renderPagination();
      } else {
        renderEmptyState("Failed to retrieve upload records: " + (data.message || "Unknown error"));
      }
    } catch (err) {
      console.error("Error loading uploads:", err);
      renderEmptyState("Could not connect to backend server");
    }
  }

  // 3. Render Table
  function renderTable(items) {
    historyTotalTag.textContent = `${totalRecords} Record${totalRecords === 1 ? "" : "s"}`;

    if (!items || items.length === 0) {
      renderEmptyState("No matching upload records found.");
      return;
    }

    historyTbody.innerHTML = items.map(u => {
      const batchDisplay = u.batch_name || "Unknown";
      const originalName = u.original_file_name || u.file_name || "-";
      const uploadedName = u.file_name || "-";
      const sizeDisplay = formatBytes(u.file_size);
      const dateTimeDisplay = (u.upload_date || "") + (u.upload_time ? ` ${u.upload_time}` : "");

      let statusBadge = `<span class="status-pill status-uploaded">&#10003; Uploaded</span>`;
      if (u.status && u.status.toLowerCase() === "failed") {
        statusBadge = `<span class="status-pill status-invalid" title="${escapeHtml(u.error_message || '')}">&#9888; Failed</span>`;
      } else if (u.status && u.status.toLowerCase() === "pending") {
        statusBadge = `<span class="status-pill status-pending">Pending</span>`;
      }

      return `
        <tr>
          <td class="mono font-semibold text-muted">#${u.id}</td>
          <td>
            <span class="batch-badge">${escapeHtml(batchDisplay)}</span>
          </td>
          <td>
            <div class="file-cell" title="${escapeHtml(originalName)}">
              <span class="file-name-text">${escapeHtml(originalName)}</span>
            </div>
          </td>
          <td>
            <span class="standardized-pill" title="${escapeHtml(uploadedName)}">
              ${escapeHtml(uploadedName)}
            </span>
          </td>
          <td class="mono">${sizeDisplay}</td>
          <td class="text-muted text-sm">${escapeHtml(dateTimeDisplay || "-")}</td>
          <td>${statusBadge}</td>
          <td>
            <div style="display: flex; gap: 0.35rem; align-items: center;">
              <button class="btn-action-play" title="Watch Video" onclick="window.playUploadVideo(${u.id}, '${escapeHtml(uploadedName)}', '${escapeHtml(batchDisplay)}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Watch
              </button>
              <button class="btn btn-secondary btn-sm btn-view-detail" data-id="${u.id}">
                Details
              </button>
            </div>
          </td>
        </tr>`;
    }).join("");

    // Attach click listeners to Details buttons
    document.querySelectorAll(".btn-view-detail").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        openDetailModal(id);
      });
    });
  }

  function renderEmptyState(message) {
    historyTotalTag.textContent = `${totalRecords} Records`;
    historyTbody.innerHTML = `
      <tr class="empty-row">
        <td colspan="8">
          <div class="empty-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <p>${escapeHtml(message)}</p>
            <span>Try adjusting your search keywords or filter criteria</span>
          </div>
        </td>
      </tr>`;
  }

  // 4. Render Pagination Controls
  function renderPagination() {
    if (totalRecords === 0) {
      paginationInfo.textContent = "Showing 0-0 of 0";
      pageIndicator.textContent = "Page 1 of 1";
      btnPrevPage.disabled = true;
      btnNextPage.disabled = true;
      return;
    }

    const startIdx = (currentPage - 1) * perPage + 1;
    const endIdx = Math.min(currentPage * perPage, totalRecords);
    paginationInfo.textContent = `Showing ${startIdx}-${endIdx} of ${totalRecords} uploads`;
    pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;

    btnPrevPage.disabled = currentPage <= 1;
    btnNextPage.disabled = currentPage >= totalPages;
  }

  // 5. Open Detail Modal
  async function openDetailModal(uploadId) {
    modalContent.innerHTML = `<p class="text-muted">Loading upload details for #${uploadId}...</p>`;
    detailModal.style.display = "flex";

    try {
      const res = await fetch(`/api/uploads/${uploadId}`);
      const data = await res.json();
      if (data.status === "success" && data.upload) {
        const u = data.upload;
        modalContent.innerHTML = `
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">Record ID</span>
              <span class="detail-val mono font-bold">#${u.id}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">Status</span>
              <span class="detail-val">
                <span class="status-pill ${u.status === 'Uploaded' ? 'status-uploaded' : 'status-invalid'}">
                  ${escapeHtml(u.status)}
                </span>
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">Batch ID &amp; Name</span>
              <span class="detail-val">
                <span class="batch-badge">${escapeHtml(u.batch_name || 'Unknown')}</span>
                <span class="text-muted mono text-sm">(ID: ${u.batch_id || 'N/A'})</span>
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">File Size</span>
              <span class="detail-val mono">${formatBytes(u.file_size)} (${(u.file_size || 0).toLocaleString()} bytes)</span>
            </div>
            <div class="detail-item full-width">
              <span class="detail-label">Original Filename</span>
              <span class="detail-val mono">${escapeHtml(u.original_file_name || '-')}</span>
            </div>
            <div class="detail-item full-width">
              <span class="detail-label">Standardized Filename</span>
              <span class="detail-val mono font-semibold" style="color: #a78bfa;">${escapeHtml(u.file_name)}</span>
            </div>
            <div class="detail-item full-width">
              <span class="detail-label">Original Source Path</span>
              <span class="detail-val mono text-sm text-muted">${escapeHtml(u.original_file_path || '-')}</span>
            </div>
            <div class="detail-item full-width">
              <span class="detail-label">Final Destination Path</span>
              <span class="detail-val mono text-sm" style="color: #34d399;">${escapeHtml(u.file_path)}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">Upload Timestamp</span>
              <span class="detail-val mono">${escapeHtml((u.upload_date || '') + ' ' + (u.upload_time || ''))}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">File Extension</span>
              <span class="detail-val mono uppercase">${escapeHtml(u.file_extension || '-')}</span>
            </div>
            <div class="detail-item full-width">
              <span class="detail-label">SHA-256 Checksum</span>
              <span class="detail-val mono text-sm text-muted checksum-box">${escapeHtml(u.checksum || 'N/A')}</span>
            </div>
            ${u.error_message ? `
            <div class="detail-item full-width error-box">
              <span class="detail-label" style="color: #fb7185;">Error Message</span>
              <span class="detail-val mono" style="color: #fb7185;">${escapeHtml(u.error_message)}</span>
            </div>` : ''}
          </div>`;
      } else {
        modalContent.innerHTML = `<p class="text-danger">Could not load record #${uploadId}: ${data.message || 'Record not found'}</p>`;
      }
    } catch (err) {
      modalContent.innerHTML = `<p class="text-danger">Failed to fetch record details: ${err}</p>`;
    }
  }

  function closeModal() {
    detailModal.style.display = "none";
  }

  if (btnCloseModal) btnCloseModal.addEventListener("click", closeModal);
  if (btnModalDismiss) btnModalDismiss.addEventListener("click", closeModal);
  detailModal.addEventListener("click", (e) => {
    if (e.target === detailModal) closeModal();
  });

  // 6. Filter Event Handlers
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentPage = 1;
        loadUploadHistory();
      }, 300);
    });
  }

  if (batchFilter) {
    batchFilter.addEventListener("change", () => {
      currentPage = 1;
      loadUploadHistory();
    });
  }

  if (statusFilter) {
    statusFilter.addEventListener("change", () => {
      currentPage = 1;
      loadUploadHistory();
    });
  }

  if (dateFilter) {
    dateFilter.addEventListener("change", () => {
      currentPage = 1;
      loadUploadHistory();
    });
  }

  if (btnClearFilters) {
    btnClearFilters.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      if (batchFilter) batchFilter.value = "all";
      if (statusFilter) statusFilter.value = "all";
      if (dateFilter) dateFilter.value = "";
      currentPage = 1;
      loadUploadHistory();
    });
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      loadUploadHistory();
    });
  }

  // Pagination clicks
  if (btnPrevPage) {
    btnPrevPage.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        loadUploadHistory();
      }
    });
  }

  if (btnNextPage) {
    btnNextPage.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage++;
        loadUploadHistory();
      }
    });
  }

  // Export Buttons Handlers
  const btnExportExcel = document.getElementById("btn-export-excel");
  const btnExportCsv = document.getElementById("btn-export-csv");
  const toastContainer = document.getElementById("toast-container");

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

  if (btnExportExcel) {
    btnExportExcel.addEventListener("click", () => {
      showToast("Exporting Excel", "Generating uploads_summary.xlsx...", "info");
      const downloadLink = document.createElement("a");
      downloadLink.href = "/api/export/excel";
      downloadLink.download = "uploads_summary.xlsx";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
      setTimeout(() => {
        showToast("Export completed", "Excel file 'uploads_summary.xlsx' downloaded successfully", "success");
      }, 800);
    });
  }

  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", () => {
      showToast("Exporting CSV", "Generating uploads_summary.csv...", "info");
      const downloadLink = document.createElement("a");
      downloadLink.href = "/api/export/csv";
      downloadLink.download = "uploads_summary.csv";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
      setTimeout(() => {
        showToast("Export completed", "CSV file 'uploads_summary.csv' downloaded successfully", "success");
      }, 800);
    });
  }

  // Video Player Modal Controller
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
      if (e.target === videoPlayerModal) closeVideoPlayer();
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

  // Initial Load
  loadBatches();
  loadUploadHistory();
});
