#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — Production Deployment Script
# ==============================================================================
set -euo pipefail

PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:8000/health/ready}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-60}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-0}"
SKIP_SMOKE_TEST="${SKIP_SMOKE_TEST:-0}"

echo "============================================================"
echo "🚀 TELEGRAM BACKUP BOT — PRODUCTION DEPLOYMENT"
echo "Compose File: ${PROD_COMPOSE_FILE}"
echo "Env File:     ${ENV_FILE}"
echo "============================================================"

# ------------------------------------------------------------------------------
# 1. Preflight Validation
# ------------------------------------------------------------------------------
if [ "$SKIP_PREFLIGHT" -eq 0 ]; then
    echo -e "\n[Step 1/6] Running production preflight checks..."
    if [ -f "scripts/preflight.sh" ]; then
        bash scripts/preflight.sh
    else
        echo "❌ Error: scripts/preflight.sh not found."
        exit 1
    fi
else
    echo -e "\n[Step 1/6] Preflight checks skipped by flag (SKIP_PREFLIGHT=1)."
fi

# ------------------------------------------------------------------------------
# 2. Compose Configuration Validation
# ------------------------------------------------------------------------------
echo -e "\n[Step 2/6] Validating Docker Compose configuration..."
if ! docker compose -f "$PROD_COMPOSE_FILE" config -q; then
    echo "❌ Error: Compose configuration validation failed."
    exit 1
fi
echo "✅ Compose configuration validated."

# ------------------------------------------------------------------------------
# 3. Build Production Container Images
# ------------------------------------------------------------------------------
echo -e "\n[Step 3/6] Building production application images..."
docker compose -f "$PROD_COMPOSE_FILE" build --pull
echo "✅ Image build complete."

# ------------------------------------------------------------------------------
# 4. Start Containers (Preserving Volumes)
# ------------------------------------------------------------------------------
echo -e "\n[Step 4/6] Starting container services..."
docker compose -f "$PROD_COMPOSE_FILE" up -d --remove-orphans
echo "✅ Services launched in background."

# ------------------------------------------------------------------------------
# 5. Wait for Database & API Service Readiness
# ------------------------------------------------------------------------------
echo -e "\n[Step 5/6] Waiting for service health & readiness (max ${MAX_WAIT_SECONDS}s)..."

wait_for_service() {
    local service_name="$1"
    local elapsed=0
    echo -n "  Waiting for '${service_name}' container to be ready... "
    while [ $elapsed -lt "$MAX_WAIT_SECONDS" ]; do
        local container_status
        container_status=$(docker compose -f "$PROD_COMPOSE_FILE" ps "$service_name" --format "{{.Status}}" 2>/dev/null || echo "")
        
        if [[ "$container_status" =~ (healthy|running) ]]; then
            echo "✅ (${container_status})"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
    done
    echo "❌ TIMEOUT"
    echo "❌ Error: Service '${service_name}' failed to reach ready state within ${MAX_WAIT_SECONDS}s."
    return 1
}

wait_for_service "mongodb"
wait_for_service "api"
wait_for_service "bot"
wait_for_service "worker"

# Poll FastAPI readiness endpoint
echo -n "  Checking FastAPI database readiness probe (${API_HEALTH_URL})... "
api_elapsed=0
api_ready=0
while [ $api_elapsed -lt "$MAX_WAIT_SECONDS" ]; do
    if curl -sS -f "$API_HEALTH_URL" &>/dev/null; then
        echo "✅ Connected"
        api_ready=1
        break
    fi
    sleep 2
    api_elapsed=$((api_elapsed + 2))
    echo -n "."
done

if [ "$api_ready" -ne 1 ]; then
    echo "⚠️  FastAPI readiness probe check timed out or host port not directly reachable (check Nginx or internal port binding)."
fi

# ------------------------------------------------------------------------------
# 6. Post-Deployment Smoke Test
# ------------------------------------------------------------------------------
if [ "$SKIP_SMOKE_TEST" -eq 0 ]; then
    echo -e "\n[Step 6/6] Executing post-deployment smoke test..."
    if [ -f "scripts/smoke_test.sh" ]; then
        if bash scripts/smoke_test.sh; then
            echo "✅ Smoke test completed successfully."
        else
            echo "❌ Smoke test detected issues. Check container logs."
            exit 1
        fi
    fi
else
    echo -e "\n[Step 6/6] Smoke tests skipped by flag (SKIP_SMOKE_TEST=1)."
fi

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
echo -e "\n============================================================"
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "============================================================"
echo "Running Services:"
docker compose -f "$PROD_COMPOSE_FILE" ps
echo "============================================================"
echo "Helpful commands:"
echo "  View API Logs:     docker compose -f $PROD_COMPOSE_FILE logs -f api"
echo "  View Bot Logs:     docker compose -f $PROD_COMPOSE_FILE logs -f bot"
echo "  View Worker Logs:  docker compose -f $PROD_COMPOSE_FILE logs -f worker"
echo "  Check Status:      docker compose -f $PROD_COMPOSE_FILE ps"
echo "============================================================"
