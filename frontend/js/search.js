/**
 * Search JavaScript Module
 */

const SearchModule = {
  currentPage: 1,
  pageSize: 10,
  currentQuery: "",

  async performSearch(page = 1) {
    const input = document.getElementById("search-input-main");
    const query = input ? input.value.trim() : "";
    if (!query) {
      window.showToast("Please enter a search term", "info");
      return;
    }

    this.currentQuery = query;
    this.currentPage = page;

    const tableBody = document.getElementById("search-table-body");
    const mobileCards = document.getElementById("search-mobile-cards");
    const emptyState = document.getElementById("search-empty-state");
    const resultsContainer = document.getElementById("search-results-panel");
    const pageInfo = document.getElementById("search-page-info");
    const prevBtn = document.getElementById("btn-search-prev");
    const nextBtn = document.getElementById("btn-search-next");

    if (resultsContainer) resultsContainer.style.display = "block";
    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--text-secondary);">Searching for "${this.escapeHtml(query)}"...</td></tr>`;
    }
    if (mobileCards) {
      mobileCards.innerHTML = `<div style="text-align: center; padding: 24px; color: var(--text-secondary);">Searching for "${this.escapeHtml(query)}"...</div>`;
    }

    try {
      const result = await window.api.get("/search", {
        q: this.currentQuery,
        page: this.currentPage,
        page_size: this.pageSize,
      });

      const items = result.items || [];

      if (items.length === 0) {
        if (tableBody) tableBody.innerHTML = "";
        if (mobileCards) mobileCards.innerHTML = "";
        if (emptyState) emptyState.style.display = "block";
        if (pageInfo) pageInfo.textContent = `No results found for "${query}"`;
        return;
      }

      if (emptyState) emptyState.style.display = "none";

      if (tableBody) {
        tableBody.innerHTML = window.FilesModule.renderTableRowsHtml(items);
      }
      if (mobileCards) {
        mobileCards.innerHTML = window.FilesModule.renderFileCardsHtml(items);
      }

      if (pageInfo) {
        pageInfo.textContent = `Page ${result.page} of ${result.total_pages || 1} (${result.total} results)`;
      }

      if (prevBtn) prevBtn.disabled = result.page <= 1;
      if (nextBtn) nextBtn.disabled = result.page >= result.total_pages;
    } catch (err) {
      console.error("Search error:", err);
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--accent-danger);">${err.message}</td></tr>`;
      }
      if (mobileCards) {
        mobileCards.innerHTML = `<div style="text-align: center; padding: 24px; color: var(--accent-danger);">${err.message}</div>`;
      }
    }
  },

  escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  },
};

window.SearchModule = SearchModule;
