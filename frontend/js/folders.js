/**
 * Folders Management JavaScript Module
 */

const FoldersModule = {
  async loadFolders() {
    const grid = document.getElementById("folders-grid");
    const emptyState = document.getElementById("folders-empty-state");

    if (grid) {
      grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 32px; color: var(--text-secondary);">Loading folders...</div>`;
    }

    try {
      const res = await window.api.get("/folders");
      const folders = res.folders || [];

      if (folders.length === 0) {
        if (grid) grid.innerHTML = "";
        if (emptyState) emptyState.style.display = "block";
        return;
      }

      if (emptyState) emptyState.style.display = "none";

      if (grid) {
        grid.innerHTML = folders.map(f => `
          <div class="stat-card" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 14px; cursor: pointer;" onclick="FoldersModule.openFolderFiles('${f.id}', '${this.escapeHtml(f.name)}')">
              <div class="stat-icon-wrapper stat-icon-yellow" style="font-size: 26px;">📁</div>
              <div>
                <div style="font-weight: 600; font-size: 16px;">${this.escapeHtml(f.name)}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Folder</div>
              </div>
            </div>
            <div>
              <button class="btn btn-secondary btn-sm" onclick="FoldersModule.deleteFolder('${f.id}', '${this.escapeHtml(f.name)}')">🗑</button>
            </div>
          </div>
        `).join("");
      }
    } catch (err) {
      console.error("Failed to load folders:", err);
      if (grid) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--accent-danger);">Error: ${err.message}</div>`;
      }
    }
  },

  openFolderFiles(folderId, folderName) {
    window.FilesModule.currentFolderId = folderId;
    window.navigateToTab("files");
    const titleEl = document.getElementById("files-page-header-title");
    if (titleEl) titleEl.textContent = `📁 ${folderName}`;
  },

  promptCreateFolder() {
    const input = document.getElementById("new-folder-name-input");
    if (input) input.value = "";
    window.openModal("modal-new-folder");
  },

  async confirmCreateFolder() {
    const input = document.getElementById("new-folder-name-input");
    const name = input ? input.value.trim() : "";
    if (!name) {
      window.showToast("Folder name cannot be empty", "error");
      return;
    }

    try {
      await window.api.post("/folders", { name });
      window.closeModal("modal-new-folder");
      window.showToast(`Folder '${name}' created!`, "success");
      this.loadFolders();
    } catch (err) {
      window.showToast(`Failed to create folder: ${err.message}`, "error");
    }
  },

  async deleteFolder(folderId, folderName) {
    if (!confirm(`Are you sure you want to delete folder '${folderName}'? Contained files will be safely moved to root.`)) {
      return;
    }

    try {
      await window.api.delete(`/folders/${folderId}`);
      window.showToast(`Folder '${folderName}' deleted`, "success");
      this.loadFolders();
    } catch (err) {
      window.showToast(`Failed to delete folder: ${err.message}`, "error");
    }
  },

  escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  },
};

window.FoldersModule = FoldersModule;
