/**
 * Files Management JavaScript Module
 */

const FilesModule = {
  currentPage: 1,
  pageSize: 15,
  totalPages: 1,
  currentFolderId: null,
  currentStatus: null,
  currentMediaType: null,

  async loadFiles(page = 1) {
    this.currentPage = page;
    const tableBody = document.getElementById("files-table-body");
    const emptyState = document.getElementById("files-empty-state");
    const paginationContainer = document.getElementById("files-pagination");

    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: var(--text-secondary);">Loading backups...</td></tr>`;
    }

    try {
      const params = {
        page: this.currentPage,
        page_size: this.pageSize,
      };
      if (this.currentFolderId) params.folder_id = this.currentFolderId;
      if (this.currentStatus) params.status = this.currentStatus;
      if (this.currentMediaType) params.media_type = this.currentMediaType;

      const result = await window.api.get("/files", params);
      this.totalPages = result.total_pages || 1;

      if (!result.items || result.items.length === 0) {
        if (tableBody) tableBody.innerHTML = "";
        if (emptyState) emptyState.style.display = "block";
        if (paginationContainer) paginationContainer.style.display = "none";
        return;
      }

      if (emptyState) emptyState.style.display = "none";
      if (paginationContainer) paginationContainer.style.display = "flex";

      this.renderTable(result.items);
      this.renderPagination(result);
    } catch (err) {
      console.error("Failed to load files:", err);
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: var(--accent-danger);">Error loading files: ${err.message}</td></tr>`;
      }
    }
  },

  renderTable(items) {
    const tableBody = document.getElementById("files-table-body");
    if (!tableBody) return;

    tableBody.innerHTML = items.map(item => {
      const sizeStr = item.file_size ? window.formatBytes(item.file_size) : "—";
      const dateStr = item.created_at ? new Date(item.created_at).toLocaleDateString() : "—";
      const statusBadge = `<span class="badge badge-${item.status}">${item.status}</span>`;

      return `
        <tr>
          <td>
            <div style="display: flex; align-items: center; gap: 8px; font-weight: 500;">
              <span>📄</span>
              <span title="${item.original_filename}">${this.escapeHtml(item.original_filename)}</span>
            </div>
          </td>
          <td><span style="color: var(--text-secondary); text-transform: capitalize;">${item.media_type}</span></td>
          <td>${sizeStr}</td>
          <td>${statusBadge}</td>
          <td>${dateStr}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 6px;">
              <button class="btn btn-secondary btn-sm" onclick="FilesModule.viewDetails('${item.id}')" title="View Details">👁</button>
              ${item.status === 'completed' ? `<a href="/api/files/${item.id}/download" class="btn btn-blue btn-sm" title="Download">⬇</a>` : ''}
              ${item.status === 'failed' ? `<button class="btn btn-secondary btn-sm" onclick="FilesModule.retryFile('${item.id}')" title="Retry">🔄</button>` : ''}
              <button class="btn btn-secondary btn-sm" onclick="FilesModule.openMoveModal('${item.id}')" title="Move">📁</button>
              <button class="btn btn-danger btn-sm" onclick="FilesModule.promptDelete('${item.id}', '${this.escapeHtml(item.original_filename)}')">🗑</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  },

  renderPagination(result) {
    const pageInfo = document.getElementById("files-page-info");
    const prevBtn = document.getElementById("btn-files-prev");
    const nextBtn = document.getElementById("btn-files-next");

    if (pageInfo) {
      pageInfo.textContent = `Page ${result.page} of ${result.total_pages || 1} (${result.total} items)`;
    }

    if (prevBtn) prevBtn.disabled = result.page <= 1;
    if (nextBtn) nextBtn.disabled = result.page >= result.total_pages;
  },

  async viewDetails(fileId) {
    try {
      const details = await window.api.get(`/files/${fileId}`);
      
      const modal = document.getElementById("modal-file-details");
      const titleEl = document.getElementById("fd-filename");
      const sizeEl = document.getElementById("fd-size");
      const mimeEl = document.getElementById("fd-mime");
      const typeEl = document.getElementById("fd-type");
      const statusEl = document.getElementById("fd-status");
      const folderEl = document.getElementById("fd-folder");
      const tagsEl = document.getElementById("fd-tags");
      const dateEl = document.getElementById("fd-date");
      const shaEl = document.getElementById("fd-sha256");
      const dlBtn = document.getElementById("fd-btn-download");

      if (titleEl) titleEl.textContent = details.original_filename;
      if (sizeEl) sizeEl.textContent = details.file_size ? window.formatBytes(details.file_size) : "—";
      if (mimeEl) mimeEl.textContent = details.mime_type || "—";
      if (typeEl) typeEl.textContent = details.media_type;
      if (statusEl) statusEl.innerHTML = `<span class="badge badge-${details.status}">${details.status}</span>`;
      if (folderEl) folderEl.textContent = details.folder_name || "Root (No folder)";
      if (dateEl) dateEl.textContent = new Date(details.created_at).toLocaleString();
      if (shaEl) shaEl.textContent = details.sha256_short || "—";

      if (tagsEl) {
        if (details.tags && details.tags.length > 0) {
          tagsEl.innerHTML = details.tags.map(t => `<span class="tag-chip">🏷 ${t}</span>`).join(" ");
        } else {
          tagsEl.textContent = "None";
        }
      }

      if (dlBtn) {
        if (details.status === "completed") {
          dlBtn.style.display = "inline-flex";
          dlBtn.href = `/api/files/${details.item_id}/download`;
        } else {
          dlBtn.style.display = "none";
        }
      }

      window.openModal("modal-file-details");
    } catch (err) {
      window.showToast(`Failed to load file details: ${err.message}`, "error");
    }
  },

  promptDelete(fileId, filename) {
    const nameEl = document.getElementById("delete-modal-filename");
    if (nameEl) nameEl.textContent = filename;

    const confirmBtn = document.getElementById("btn-confirm-delete");
    if (confirmBtn) {
      confirmBtn.onclick = () => this.confirmDelete(fileId);
    }

    window.openModal("modal-delete-confirm");
  },

  async confirmDelete(fileId) {
    try {
      await window.api.delete(`/files/${fileId}`);
      window.closeModal("modal-delete-confirm");
      window.showToast("File deleted successfully", "success");
      this.loadFiles(this.currentPage);
      window.StatsModule.loadStats();
    } catch (err) {
      window.showToast(`Failed to delete file: ${err.message}`, "error");
    }
  },

  async retryFile(fileId) {
    try {
      const res = await window.api.post(`/files/${fileId}/retry`);
      window.showToast(res.message || "Task re-queued", "success");
      this.loadFiles(this.currentPage);
      window.StatsModule.loadStats();
    } catch (err) {
      window.showToast(`Retry failed: ${err.message}`, "error");
    }
  },

  async openMoveModal(fileId) {
    const targetSelect = document.getElementById("move-folder-select");
    const moveConfirmBtn = document.getElementById("btn-confirm-move");

    if (targetSelect) {
      targetSelect.innerHTML = `<option value="">📁 Root (No folder)</option>`;
      try {
        const res = await window.api.get("/folders");
        if (res.folders) {
          res.folders.forEach(f => {
            targetSelect.innerHTML += `<option value="${f.id}">📁 ${this.escapeHtml(f.name)}</option>`;
          });
        }
      } catch (e) {}
    }

    if (moveConfirmBtn) {
      moveConfirmBtn.onclick = async () => {
        const folderId = targetSelect.value || null;
        try {
          await window.api.post(`/files/${fileId}/move`, { folder_id: folderId });
          window.closeModal("modal-move-file");
          window.showToast("File moved successfully", "success");
          this.loadFiles(this.currentPage);
        } catch (err) {
          window.showToast(`Move failed: ${err.message}`, "error");
        }
      };
    }

    window.openModal("modal-move-file");
  },

  escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  },
};

window.FilesModule = FilesModule;
