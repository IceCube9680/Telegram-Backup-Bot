#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — Production Rollback Script
# ==============================================================================
set -euo pipefail

PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
IMAGE_TAG="${1:-}"
FORCE="${2:-}"

echo "============================================================"
echo "🔄 TELEGRAM BACKUP BOT — PRODUCTION ROLLBACK"
echo "Compose File: ${PROD_COMPOSE_FILE}"
echo "============================================================"

echo "⚠️  CRITICAL ROLLBACK POLICY:"
echo "  1. This script rolls back running application containers to a previous"
echo "     known-good container state or specific image version tag."
echo "  2. Database (MongoDB) and Storage volumes are PRESERVED."
echo "  3. Database restoration from backup is a separate, deliberate disaster"
echo "     recovery operation (see scripts/restore_mongodb.sh)."
echo "============================================================"

if [ -z "$IMAGE_TAG" ]; then
    echo "Usage: $0 <IMAGE_TAG_OR_VERSION> [--confirm]"
    echo ""
    echo "Example: $0 v0.1.0 --confirm"
    echo "         $0 telegram-backup-bot:v0.1.0"
    exit 1
fi

if [ "$FORCE" != "--confirm" ]; then
    read -p "Are you sure you want to rollback to '${IMAGE_TAG}'? (yes/no): " -r CONFIRM_INPUT
    if [ "$CONFIRM_INPUT" != "yes" ]; then
        echo "Rollback cancelled by operator."
        exit 0
    fi
fi

echo -e "\n[Step 1/4] Stopping current deployment containers gracefully..."
docker compose -f "$PROD_COMPOSE_FILE" stop api bot worker

echo -e "\n[Step 2/4] Deploying target version (${IMAGE_TAG})..."
# If IMAGE_TAG is an environment variable override or tag
export APP_IMAGE_TAG="$IMAGE_TAG"
docker compose -f "$PROD_COMPOSE_FILE" up -d --no-build api bot worker

echo -e "\n[Step 3/4] Verifying rolled-back container status & readiness..."
sleep 5
docker compose -f "$PROD_COMPOSE_FILE" ps

echo -e "\n[Step 4/4] Running smoke test against rolled-back services..."
if [ -f "scripts/smoke_test.sh" ]; then
    if bash scripts/smoke_test.sh; then
        echo "✅ Rollback verified: Smoke tests passed."
    else
        echo "⚠️  Smoke test failed. Check logs via 'docker compose -f $PROD_COMPOSE_FILE logs'."
        exit 1
    fi
fi

echo -e "\n============================================================"
echo "✅ Rollback completed successfully to version: ${IMAGE_TAG}"
echo "============================================================"
