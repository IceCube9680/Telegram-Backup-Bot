#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — File Storage Backup Script
# ==============================================================================
set -euo pipefail

STORAGE_PATH="${STORAGE_PATH:-./storage}"
BACKUP_DIR="${BACKUP_DIR:-./backups/storage}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET_FILE="${BACKUP_DIR}/storage_backup_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "============================================================"
echo "📦 Starting Storage Filesystem Backup..."
echo "Source:  ${STORAGE_PATH}"
echo "Target:  ${TARGET_FILE}"
echo "============================================================"

if [ ! -d "${STORAGE_PATH}" ]; then
    echo "❌ Error: Storage directory '${STORAGE_PATH}' does not exist."
    exit 1
fi

# Exclude temporary download directory from permanent archive
tar --exclude='.tmp-downloads' -czf "${TARGET_FILE}" -C "${STORAGE_PATH}" .

if [[ -f "${TARGET_FILE}" && -s "${TARGET_FILE}" ]]; then
    SIZE_KB=$(du -k "${TARGET_FILE}" | cut -f1)
    echo "✅ Storage backup created: ${TARGET_FILE} (${SIZE_KB} KB)"
else
    echo "❌ Error: Storage backup archive was not created or is empty."
    exit 1
fi

# Verify newly created storage archive if python verifier is available
if [ -f "app/scripts/verify_backup.py" ]; then
    if command -v python3 &>/dev/null; then
        python3 -m app.scripts.verify_backup "${TARGET_FILE}" || true
    elif command -v python &>/dev/null; then
        python -m app.scripts.verify_backup "${TARGET_FILE}" || true
    fi
fi

# Retention cleanup
echo "🧹 Cleaning storage backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "storage_backup_*.tar.gz" -mtime +"${RETENTION_DAYS}" -delete || true

echo "✅ Storage backup process complete."
