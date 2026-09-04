#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — MongoDB Restore Script
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup_archive.gz> [--confirm]"
    exit 1
fi

ARCHIVE_PATH="$1"
CONFIRM="${2:-}"
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
MONGODB_DATABASE="${MONGODB_DATABASE:-telegram_backup}"

if [ ! -f "${ARCHIVE_PATH}" ]; then
    echo "❌ Error: Backup archive '${ARCHIVE_PATH}' not found."
    exit 1
fi

echo "============================================================"
echo "⚠️  WARNING: DATABASE RESTORE OPERATION"
echo "Target Database:  ${MONGODB_DATABASE}"
echo "Source Archive:   ${ARCHIVE_PATH}"
echo "============================================================"

if [ "${CONFIRM}" != "--confirm" ]; then
    read -p "Are you sure you want to RESTORE database '${MONGODB_DATABASE}' from this archive? (yes/no): " -r RESPONSE
    if [[ "${RESPONSE}" != "yes" ]]; then
        echo "Restore cancelled by user."
        exit 0
    fi
fi

echo "Restoring MongoDB database..."
if command -v mongorestore &> /dev/null; then
    mongorestore --uri="${MONGODB_URI}" --archive="${ARCHIVE_PATH}" --gzip --drop
elif command -v docker &> /dev/null && docker ps | grep -q "telegram_backup_mongodb"; then
    echo "Using Docker container 'telegram_backup_mongodb' for mongorestore..."
    docker exec -i telegram_backup_mongodb mongorestore --archive --gzip --drop < "${ARCHIVE_PATH}"
else
    echo "❌ Error: Neither local 'mongorestore' nor running Docker container 'telegram_backup_mongodb' found."
    exit 1
fi

echo "✅ Database restore completed successfully."
