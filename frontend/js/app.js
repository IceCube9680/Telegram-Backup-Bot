/**
 * Telegram Backup Bot - Main Application Controller
 */

// Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  
  const icon = type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️";
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Modal Helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("open");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("open");
}

// Tab Navigation
function navigateToTab(tabName) {
  const navItems = document.querySelectorAll(".nav-item");
  const viewSections = document.querySelectorAll(".view-section");

  navItems.forEach(item => {
    if (item.dataset.tab === tabName) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  viewSections.forEach(section => {
    if (section.id === `view-${tabName}`) {
      section.classList.add("active");
    } else {
      section.classList.remove("active");
    }
  });

  // Trigger relevant module loaders
  if (tabName === "dashboard") {
    window.StatsModule.loadStats();
  } else if (tabName === "files") {
    window.FilesModule.loadFiles(1);
  } else if (tabName === "folders") {
    window.FoldersModule.loadFolders();
  } else if (tabName === "tags") {
    window.TagsModule.loadTags();
  } else if (tabName === "stats") {
    window.StatsModule.loadStats();
  }
}

// App Initialization
document.addEventListener("DOMContentLoaded", async () => {
  // 1. Check Authentication
  const user = await window.Auth.checkAuth();
  if (!user) {
    window.location.href = "/login";
    return;
  }

  // 2. Render User Profile
  const avatarEl = document.getElementById("user-avatar-initial");
  const nameEl = document.getElementById("user-display-name");
  const handleEl = document.getElementById("user-display-handle");

  const displayName = `${user.first_name || ""} ${user.last_name || ""}`.trim() || "Telegram User";
  if (avatarEl) avatarEl.textContent = displayName.charAt(0).toUpperCase();
  if (nameEl) nameEl.textContent = displayName;
  if (handleEl) handleEl.textContent = user.username ? `@${user.username}` : `ID: ${user.telegram_user_id}`;

  // 3. Bind Navigation Click Handlers
  document.querySelectorAll(".nav-item[data-tab]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      navigateToTab(btn.dataset.tab);
    });
  });

  // 4. Bind Logout Button
  const logoutBtn = document.getElementById("btn-logout");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => window.Auth.logout());
  }

  // 5. Close Modal on Backdrop Click
  document.querySelectorAll(".modal-backdrop").forEach(backdrop => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        backdrop.classList.remove("open");
      }
    });
  });

  // 6. Bind Pagination Buttons
  const filesPrev = document.getElementById("btn-files-prev");
  const filesNext = document.getElementById("btn-files-next");
  if (filesPrev) filesPrev.addEventListener("click", () => window.FilesModule.loadFiles(window.FilesModule.currentPage - 1));
  if (filesNext) filesNext.addEventListener("click", () => window.FilesModule.loadFiles(window.FilesModule.currentPage + 1));

  const searchPrev = document.getElementById("btn-search-prev");
  const searchNext = document.getElementById("btn-search-next");
  if (searchPrev) searchPrev.addEventListener("click", () => window.SearchModule.performSearch(window.SearchModule.currentPage - 1));
  if (searchNext) searchNext.addEventListener("click", () => window.SearchModule.performSearch(window.SearchModule.currentPage + 1));

  // 7. Initial Data Load
  window.StatsModule.loadStats();
  window.FilesModule.loadFiles(1);
});

// Expose globals
window.showToast = showToast;
window.openModal = openModal;
window.closeModal = closeModal;
window.navigateToTab = navigateToTab;
