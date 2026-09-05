/**
 * Statistics Rendering and Formatting
 */

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || isNaN(bytes) || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

const StatsModule = {
  async loadStats() {
    try {
      const stats = await window.api.get("/stats");
      this.render(stats);
      return stats;
    } catch (err) {
      console.error("Failed to load statistics:", err);
      window.showToast("Failed to load statistics", "error");
    }
  },

  render(stats) {
    if (!stats) return;

    const formattedSize = formatBytes(stats.total_size_bytes);

    // Update Storage Widget in Welcome Card
    const storageWidgetText = document.getElementById("storage-widget-text");
    const storageProgressFill = document.getElementById("storage-progress-bar-fill");
    if (storageWidgetText) {
      storageWidgetText.textContent = `${formattedSize} stored • ${stats.completed_count} files`;
    }
    if (storageProgressFill) {
      // Calculate a healthy representation of usage
      const percentage = Math.min(100, Math.max(8, Math.round((stats.total_size_bytes / (10 * 1024 * 1024 * 1024)) * 100)));
      storageProgressFill.style.width = `${percentage}%`;
    }

    // Update Quick Overview Cards
    const totalFilesEl = document.getElementById("stat-total-files");
    const totalSizeEl = document.getElementById("stat-total-size");
    const completedEl = document.getElementById("stat-completed");
    const processingEl = document.getElementById("stat-processing");
    const pendingEl = document.getElementById("stat-pending");
    const failedEl = document.getElementById("stat-failed");

    if (totalFilesEl) totalFilesEl.textContent = stats.total_files.toLocaleString();
    if (totalSizeEl) totalSizeEl.textContent = formattedSize;
    if (completedEl) completedEl.textContent = stats.completed_count.toLocaleString();
    if (processingEl) processingEl.textContent = stats.processing_count.toLocaleString();
    if (pendingEl) pendingEl.textContent = stats.pending_count.toLocaleString();
    if (failedEl) failedEl.textContent = stats.failed_count.toLocaleString();

    // Stats View Breakdown
    const statsViewTotalFiles = document.getElementById("sv-total-files");
    const statsViewTotalSize = document.getElementById("sv-total-size");
    const statsViewCompleted = document.getElementById("sv-completed");
    const statsViewProcessing = document.getElementById("sv-processing");
    const statsViewPending = document.getElementById("sv-pending");
    const statsViewFailed = document.getElementById("sv-failed");

    if (statsViewTotalFiles) statsViewTotalFiles.textContent = stats.total_files.toLocaleString();
    if (statsViewTotalSize) statsViewTotalSize.textContent = formattedSize;
    if (statsViewCompleted) statsViewCompleted.textContent = stats.completed_count.toLocaleString();
    if (statsViewProcessing) statsViewProcessing.textContent = stats.processing_count.toLocaleString();
    if (statsViewPending) statsViewPending.textContent = stats.pending_count.toLocaleString();
    if (statsViewFailed) statsViewFailed.textContent = stats.failed_count.toLocaleString();
  },
};

window.StatsModule = StatsModule;
window.formatBytes = formatBytes;
