/**
 * Batch Management Page Logic - Day 8 Implementation
 * Automated Session Recording Upload System
 *
 * Implements:
 * - Load and render all batches
 * - Add new batch modal form
 * - Edit batch modal form
 * - Toggle batch enabled/disabled
 * - Delete batch confirmation modal
 * - Dynamic toast notifications
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const batchesTbody = document.getElementById("batches-tbody");
  const batchesTotalTag = document.getElementById("batches-total-tag");
  const btnOpenAddModal = document.getElementById("btn-open-add-modal");
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  const appSidebar = document.getElementById("app-sidebar");
  const toastContainer = document.getElementById("toast-container");

  // Add/Edit Modal Elements
  const batchModal = document.getElementById("batch-modal");
  const modalBatchTitle = document.getElementById("modal-batch-title");
  const batchForm = document.getElementById("batch-form");
  const batchIdInput = document.getElementById("batch-id-input");
  const batchNameInput = document.getElementById("batch-name-input");
  const batchKeywordsInput = document.getElementById("batch-keywords-input");
  const batchFolderInput = document.getElementById("batch-folder-input");
  const batchEnabledInput = document.getElementById("batch-enabled-input");
  const btnCloseBatchModal = document.getElementById("btn-close-batch-modal");
  const btnCancelBatch = document.getElementById("btn-cancel-batch");

  // Delete Modal Elements
  const deleteModal = document.getElementById("delete-modal");
  const deleteBatchNameEl = document.getElementById("delete-batch-name");
  const btnCloseDeleteModal = document.getElementById("btn-close-delete-modal");
  const btnCancelDelete = document.getElementById("btn-cancel-delete");
  const btnConfirmDelete = document.getElementById("btn-confirm-delete");

  let batchToDeleteId = null;
  let allBatches = [];

  // 1. Toast Notification Utility
  window.showToast = function(title, message, type = "success") {
    if (!toastContainer) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    let iconSvg = "";
    if (type === "success") {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === "error") {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
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
  };

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

  // 2. Fetch and render batches
  async function loadBatches() {
    try {
      const res = await fetch("/api/batches");
      const data = await res.json();
      if (data.status === "success" && data.batches) {
        allBatches = data.batches;
        renderBatches(allBatches);
      } else {
        renderErrorState(data.message || "Failed to load batches");
      }
    } catch (err) {
      console.error("Error loading batches:", err);
      renderErrorState("Could not connect to backend server");
    }
  }

  function renderBatches(batches) {
    batchesTotalTag.textContent = `${batches.length} Batch${batches.length === 1 ? "" : "es"}`;

    if (!batches || batches.length === 0) {
      batchesTbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="6">
            <div class="empty-state">
              <p>No batches configured yet.</p>
              <span>Click "+ Add New Batch" above to configure your first batch mapping.</span>
            </div>
          </td>
        </tr>`;
      return;
    }

    batchesTbody.innerHTML = batches.map(b => {
      const keywords = (b.keywords || "")
        .split(",")
        .map(k => k.trim())
        .filter(Boolean);

      const keywordBadges = keywords.length > 0
        ? keywords.map(k => `<span class="keyword-tag">${escapeHtml(k)}</span>`).join(" ")
        : `<span class="text-muted text-sm">No keywords</span>`;

      const destFolder = b.destination_folder || `exports/${b.batch_name}`;
      const isEnabled = b.is_enabled !== false;

      return `
        <tr>
          <td class="mono font-semibold text-muted">#${b.id}</td>
          <td>
            <span class="batch-badge font-bold">${escapeHtml(b.batch_name)}</span>
          </td>
          <td>
            <div class="keyword-tags">${keywordBadges}</div>
          </td>
          <td class="mono text-sm" style="color: #38bdf8;">${escapeHtml(destFolder)}</td>
          <td>
            <label class="switch" title="Toggle active status">
              <input type="checkbox" class="toggle-batch-active" data-id="${b.id}" ${isEnabled ? "checked" : ""}>
              <span class="slider"></span>
            </label>
          </td>
          <td style="text-align: right;">
            <div class="action-btn-group">
              <button class="btn-action btn-action-edit btn-edit-batch" data-id="${b.id}">Edit</button>
              <button class="btn-action btn-action-delete btn-delete-batch" data-id="${b.id}" data-name="${escapeHtml(b.batch_name)}">Delete</button>
            </div>
          </td>
        </tr>`;
    }).join("");

    // Attach listeners
    document.querySelectorAll(".toggle-batch-active").forEach(checkbox => {
      checkbox.addEventListener("change", async (e) => {
        const id = checkbox.getAttribute("data-id");
        await toggleBatchStatus(id, checkbox);
      });
    });

    document.querySelectorAll(".btn-edit-batch").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        openEditModal(id);
      });
    });

    document.querySelectorAll(".btn-delete-batch").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const name = btn.getAttribute("data-name");
        openDeleteModal(id, name);
      });
    });
  }

  function renderErrorState(msg) {
    batchesTbody.innerHTML = `
      <tr class="empty-row">
        <td colspan="6">
          <div class="empty-state">
            <p class="text-danger">${escapeHtml(msg)}</p>
          </div>
        </td>
      </tr>`;
  }

  // 3. Toggle Batch Status
  async function toggleBatchStatus(id, checkbox) {
    try {
      const res = await fetch(`/api/batches/${id}/toggle`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        showToast("Batch Updated", data.message, "success");
      } else {
        checkbox.checked = !checkbox.checked;
        showToast("Error", data.message || "Failed to toggle batch", "error");
      }
    } catch (err) {
      checkbox.checked = !checkbox.checked;
      showToast("Error", "Server error while toggling batch", "error");
    }
  }

  // 4. Modal Open/Close handlers
  function openAddModal() {
    batchIdInput.value = "";
    modalBatchTitle.textContent = "Add New Batch";
    batchNameInput.value = "";
    batchKeywordsInput.value = "";
    batchFolderInput.value = "";
    batchEnabledInput.checked = true;
    batchModal.style.display = "flex";
    batchNameInput.focus();
  }

  function openEditModal(id) {
    const batch = allBatches.find(b => b.id == id);
    if (!batch) return;

    batchIdInput.value = batch.id;
    modalBatchTitle.textContent = `Edit Batch: ${batch.batch_name}`;
    batchNameInput.value = batch.batch_name || "";
    batchKeywordsInput.value = batch.keywords || "";
    batchFolderInput.value = batch.destination_folder || "";
    batchEnabledInput.checked = batch.is_enabled !== false;
    batchModal.style.display = "flex";
    batchNameInput.focus();
  }

  function closeBatchModal() {
    batchModal.style.display = "none";
  }

  if (btnOpenAddModal) btnOpenAddModal.addEventListener("click", openAddModal);
  if (btnCloseBatchModal) btnCloseBatchModal.addEventListener("click", closeBatchModal);
  if (btnCancelBatch) btnCancelBatch.addEventListener("click", closeBatchModal);
  batchModal.addEventListener("click", (e) => {
    if (e.target === batchModal) closeBatchModal();
  });

  // 5. Submit Batch Form (Add or Edit)
  batchForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const id = batchIdInput.value;
    const isEdit = Boolean(id);
    const payload = {
      batch_name: batchNameInput.value.trim(),
      keywords: batchKeywordsInput.value.trim(),
      destination_folder: batchFolderInput.value.trim() || undefined,
      is_enabled: batchEnabledInput.checked,
    };

    if (!payload.batch_name || !payload.keywords) {
      showToast("Validation Error", "Batch name and keywords are required.", "error");
      return;
    }

    try {
      const url = isEdit ? `/api/batches/${id}` : "/api/batches";
      const method = isEdit ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (data.status === "success") {
        showToast(isEdit ? "Batch Updated" : "Batch Created", data.message, "success");
        closeBatchModal();
        await loadBatches();
      } else {
        showToast("Error", data.message || "Failed to save batch", "error");
      }
    } catch (err) {
      showToast("Error", "Network error while saving batch", "error");
    }
  });

  // 6. Delete Batch Modal & Logic
  function openDeleteModal(id, name) {
    batchToDeleteId = id;
    deleteBatchNameEl.textContent = name;
    deleteModal.style.display = "flex";
  }

  function closeDeleteModal() {
    batchToDeleteId = null;
    deleteModal.style.display = "none";
  }

  if (btnCloseDeleteModal) btnCloseDeleteModal.addEventListener("click", closeDeleteModal);
  if (btnCancelDelete) btnCancelDelete.addEventListener("click", closeDeleteModal);
  deleteModal.addEventListener("click", (e) => {
    if (e.target === deleteModal) closeDeleteModal();
  });

  btnConfirmDelete.addEventListener("click", async () => {
    if (!batchToDeleteId) return;

    try {
      const res = await fetch(`/api/batches/${batchToDeleteId}`, { method: "DELETE" });
      const data = await res.json();

      if (data.status === "success") {
        showToast("Batch Deleted", data.message, "success");
        closeDeleteModal();
        await loadBatches();
      } else {
        showToast("Error", data.message || "Failed to delete batch", "error");
      }
    } catch (err) {
      showToast("Error", "Network error while deleting batch", "error");
    }
  });

  // Initial Load
  loadBatches();
});
