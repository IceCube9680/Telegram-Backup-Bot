/**
 * Tags Management JavaScript Module
 */

const TagsModule = {
  async loadTags() {
    const listEl = document.getElementById("tags-list-container");
    const emptyState = document.getElementById("tags-empty-state");

    if (listEl) {
      listEl.innerHTML = `<div style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading tags...</div>`;
    }

    try {
      const res = await window.api.get("/tags");
      const tags = res.tags || [];

      if (tags.length === 0) {
        if (listEl) listEl.innerHTML = "";
        if (emptyState) emptyState.style.display = "block";
        return;
      }

      if (emptyState) emptyState.style.display = "none";

      if (listEl) {
        listEl.innerHTML = tags.map(t => `
          <div class="stat-card" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 10px; cursor: pointer;" onclick="TagsModule.openTagFiles('${t.id}', '${this.escapeHtml(t.name)}')">
              <span style="font-size: 20px;">🏷</span>
              <span style="font-weight: 600; font-size: 15px;">${this.escapeHtml(t.name)}</span>
            </div>
            <div>
              <button class="btn btn-secondary btn-sm" onclick="TagsModule.deleteTag('${t.id}', '${this.escapeHtml(t.name)}')">🗑</button>
            </div>
          </div>
        `).join("");
      }
    } catch (err) {
      console.error("Failed to load tags:", err);
      if (listEl) {
        listEl.innerHTML = `<div style="text-align: center; color: var(--accent-danger);">Error: ${err.message}</div>`;
      }
    }
  },

  async openTagFiles(tagId, tagName) {
    const panel = document.getElementById("tagged-files-panel");
    const titleEl = document.getElementById("tagged-files-title");
    const tbody = document.getElementById("tagged-files-tbody");

    if (panel) panel.style.display = "block";
    if (titleEl) titleEl.textContent = `🏷 Files tagged with "${tagName}"`;
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 16px;">Loading tagged files...</td></tr>`;

    try {
      const res = await window.api.get(`/tags/${tagId}/files`);
      const items = res.items || [];

      if (items.length === 0) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 16px; color: var(--text-secondary);">No files attached to this tag.</td></tr>`;
        return;
      }

      if (tbody) {
        tbody.innerHTML = items.map(item => `
          <tr>
            <td>📄 ${this.escapeHtml(item.original_filename || "Unnamed")}</td>
            <td>${item.media_type || "file"}</td>
            <td>${item.file_size ? window.formatBytes(item.file_size) : "—"}</td>
            <td><span class="badge badge-${item.status}">${item.status}</span></td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="FilesModule.viewDetails('${item.id}')">👁 View</button>
              ${item.status === 'completed' ? `<a href="/api/files/${item.id}/download" class="btn btn-blue btn-sm">⬇</a>` : ''}
            </td>
          </tr>
        `).join("");
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="color: var(--accent-danger); text-align: center;">${err.message}</td></tr>`;
    }
  },

  promptCreateTag() {
    const input = document.getElementById("new-tag-name-input");
    if (input) input.value = "";
    window.openModal("modal-new-tag");
  },

  async confirmCreateTag() {
    const input = document.getElementById("new-tag-name-input");
    const name = input ? input.value.trim() : "";
    if (!name) {
      window.showToast("Tag name cannot be empty", "error");
      return;
    }

    try {
      await window.api.post("/tags", { name });
      window.closeModal("modal-new-tag");
      window.showToast(`Tag '${name}' created!`, "success");
      this.loadTags();
    } catch (err) {
      window.showToast(`Failed to create tag: ${err.message}`, "error");
    }
  },

  async deleteTag(tagId, tagName) {
    if (!confirm(`Are you sure you want to delete tag '${tagName}'?`)) {
      return;
    }

    try {
      await window.api.delete(`/tags/${tagId}`);
      window.showToast(`Tag '${tagName}' deleted`, "success");
      this.loadTags();
      const panel = document.getElementById("tagged-files-panel");
      if (panel) panel.style.display = "none";
    } catch (err) {
      window.showToast(`Failed to delete tag: ${err.message}`, "error");
    }
  },

  escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  },
};

window.TagsModule = TagsModule;
