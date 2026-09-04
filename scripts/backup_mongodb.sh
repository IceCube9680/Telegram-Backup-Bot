#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — MongoDB Backup Script
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/mongodb}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET_FILE="${BACKUP_DIR}/mongo_backup_${TIMESTAMP}.archive.gz"
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
MONGODB_DATABASE="${MONGODB_DATABASE:-telegram_backup}"

mkdir -p "${BACKUP_DIR}"

echo "============================================================"
echo "📦 Starting MongoDB Database Backup..."
echo "Database:  ${MONGODB_DATABASE}"
echo "Target:    ${TARGET_FILE}"
echo "============================================================"

# Perform mongodump with gzip compression and single archive
if command -v mongodump &> /dev/null; then
    mongodump --uri="${MONGODB_URI}" --db="${MONGODB_DATABASE}" --archive="${TARGET_FILE}" --gzip
elif command -v docker &> /dev/null && docker ps | grep -q "telegram_backup_mongodb"; then
    echo "Using Docker container 'telegram_backup_mongodb' for mongodump..."
    docker exec telegram_backup_mongodb mongodump --db="${MONGODB_DATABASE}" --archive --gzip > "${TARGET_FILE}"
else
    echo "❌ Error: Neither local 'mongodump' nor running Docker container 'telegram_backup_mongodb' found."
    exit 1
fi

if [[ -f "${TARGET_FILE}" && -s "${TARGET_FILE}" ]]; then
    SIZE_KB=$(du -k "${TARGET_FILE}" | cut -f1)
    echo "✅ MongoDB Backup successfully created: ${TARGET_FILE} (${SIZE_KB} KB)"
else
    echo "❌ Error: Backup file was not created or is empty."
    exit 1
fi

# Verify newly created archive if python verifier is available
if [ -f "app/scripts/verify_backup.py" ]; then
    if command -v python3 &>/dev/null; then
        python3 -m app.scripts.verify_backup "${TARGET_FILE}" || true
    elif command -v python &>/dev/null; then
        python -m app.scripts.verify_backup "${TARGET_FILE}" || true
    fi
fi

# Cleanup old backups older than RETENTION_DAYS
echo "🧹 Cleaning backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -type f -name "mongo_backup_*.archive.gz" -mtime +"${RETENTION_DAYS}" -delete || true

echo "✅ MongoDB backup process complete."
