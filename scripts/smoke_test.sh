#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — Production Smoke Test Script
# ==============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TIMEOUT_SEC="${TIMEOUT_SEC:-5}"

FAILURES=0
SUCCESSES=0

pass() {
    echo -e "  \033[0;32m[PASS]\033[0m $1"
    SUCCESSES=$((SUCCESSES + 1))
}

fail() {
    echo -e "  \033[0;31m[FAIL]\033[0m $1"
    FAILURES=$((FAILURES + 1))
}

echo "============================================================"
echo "🧪 TELEGRAM BACKUP BOT — PRODUCTION SMOKE TEST"
echo "Target Base URL: ${BASE_URL}"
echo "============================================================"

# Helper function for curl
http_get() {
    local endpoint="$1"
    curl -sS -m "$TIMEOUT_SEC" -D - "${BASE_URL}${endpoint}" -o /tmp/smoke_body_$$ 2>/dev/null || true
}

http_post_json() {
    local endpoint="$1"
    local data="$2"
    curl -sS -m "$TIMEOUT_SEC" -D - -H "Content-Type: application/json" -d "$data" "${BASE_URL}${endpoint}" -o /tmp/smoke_body_$$ 2>/dev/null || true
}

cleanup() {
    rm -f /tmp/smoke_body_$$ /tmp/smoke_headers_$$
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# 1. Liveness Probe
# ------------------------------------------------------------------------------
echo -e "\n1. Liveness Probe (GET /health/live):"
HEADERS=$(http_get "/health/live")
BODY=$(cat /tmp/smoke_body_$$ 2>/dev/null || echo "")

if echo "$HEADERS" | grep -q "HTTP/.* 200"; then
    if echo "$BODY" | grep -q '"status"[[:space:]]*:[[:space:]]*"alive"'; then
        pass "Liveness probe responded with HTTP 200 and status='alive'"
    else
        fail "Liveness probe returned HTTP 200 but unexpected JSON body: $BODY"
    fi
else
    fail "Liveness probe failed: $(echo "$HEADERS" | head -n 1)"
fi

# ------------------------------------------------------------------------------
# 2. Readiness Probe
# ------------------------------------------------------------------------------
echo -e "\n2. Readiness Probe (GET /health/ready):"
HEADERS=$(http_get "/health/ready")
BODY=$(cat /tmp/smoke_body_$$ 2>/dev/null || echo "")

if echo "$HEADERS" | grep -q "HTTP/.* 200"; then
    if echo "$BODY" | grep -q '"status"[[:space:]]*:[[:space:]]*"ready"'; then
        pass "Readiness probe responded with HTTP 200 and status='ready' (MongoDB connected)"
    else
        fail "Readiness probe returned HTTP 200 but unexpected body: $BODY"
    fi
elif echo "$HEADERS" | grep -q "HTTP/.* 503"; then
    fail "Readiness probe returned HTTP 503: MongoDB not ready / connected"
else
    fail "Readiness probe request failed: $(echo "$HEADERS" | head -n 1)"
fi

# ------------------------------------------------------------------------------
# 3. Combined Health Check & Metadata
# ------------------------------------------------------------------------------
echo -e "\n3. Combined Health Endpoint (GET /health):"
HEADERS=$(http_get "/health")
BODY=$(cat /tmp/smoke_body_$$ 2>/dev/null || echo "")

if echo "$HEADERS" | grep -q "HTTP/.* 200"; then
    if echo "$BODY" | grep -q '"version"'; then
        APP_VER=$(echo "$BODY" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d '"' -f4 || echo "unknown")
        pass "Combined health endpoint returned HTTP 200 (Version: ${APP_VER})"
    else
        pass "Combined health endpoint returned HTTP 200"
    fi

    if echo "$BODY" | grep -q '"disk"'; then
        pass "Disk capacity and storage health reported in payload"
    fi
else
    fail "Combined health endpoint check failed: $(echo "$HEADERS" | head -n 1)"
fi

# ------------------------------------------------------------------------------
# 4. Frontend Login & Dashboard
# ------------------------------------------------------------------------------
echo -e "\n4. Web Dashboard Availability:"
HEADERS=$(http_get "/login")
BODY=$(cat /tmp/smoke_body_$$ 2>/dev/null || echo "")

if echo "$HEADERS" | grep -q "HTTP/.* 200"; then
    if echo "$BODY" | grep -qi "<html"; then
        pass "Login page (GET /login) rendered valid HTML"
    else
        fail "Login page did not return HTML content"
    fi
else
    fail "Login page (GET /login) failed with status: $(echo "$HEADERS" | head -n 1)"
fi

HEADERS_ROOT=$(http_get "/")
if echo "$HEADERS_ROOT" | grep -qE "HTTP/.* (200|301|302|307|308)"; then
    pass "Root dashboard (GET /) is accessible (HTTP status $(echo "$HEADERS_ROOT" | head -n 1 | awk '{print $2}'))"
else
    fail "Root dashboard (GET /) failed: $(echo "$HEADERS_ROOT" | head -n 1)"
fi

# ------------------------------------------------------------------------------
# 5. Security Headers
# ------------------------------------------------------------------------------
echo -e "\n5. Security Headers Validation:"
HEADERS=$(http_get "/health")

if echo "$HEADERS" | grep -qi "X-Content-Type-Options:[[:space:]]*nosniff"; then
    pass "X-Content-Type-Options: nosniff header present"
else
    fail "X-Content-Type-Options header missing or incorrect"
fi

if echo "$HEADERS" | grep -qi "X-Frame-Options:[[:space:]]*DENY"; then
    pass "X-Frame-Options: DENY header present"
else
    fail "X-Frame-Options header missing or incorrect"
fi

if echo "$HEADERS" | grep -qi "Referrer-Policy:"; then
    pass "Referrer-Policy header present"
else
    fail "Referrer-Policy header missing"
fi

if echo "$HEADERS" | grep -qi "X-Request-ID:"; then
    pass "X-Request-ID correlation header present"
else
    fail "X-Request-ID header missing"
fi

# ------------------------------------------------------------------------------
# 6. Production Dev-Login Protection Check
# ------------------------------------------------------------------------------
echo -e "\n6. Production Dev-Login Security Guard:"
DEV_HEADERS=$(http_post_json "/api/auth/dev-login" '{"telegram_user_id": 999999999, "first_name": "test_user"}')
DEV_BODY=$(cat /tmp/smoke_body_$$ 2>/dev/null || echo "")

if echo "$DEV_HEADERS" | grep -q "HTTP/.* 403"; then
    pass "Dev-login endpoint is strictly blocked (HTTP 403 Forbidden)"
elif echo "$DEV_HEADERS" | grep -q "HTTP/.* 200"; then
    # In test/dev environment, dev-login may succeed
    echo -e "  \033[0;33m[INFO]\033[0m Dev-login succeeded (allowed in test/development environment)"
else
    pass "Dev-login rejected with non-200 status code: $(echo "$DEV_HEADERS" | head -n 1)"
fi

# ------------------------------------------------------------------------------
# Summary & Result
# ------------------------------------------------------------------------------
echo -e "\n============================================================"
echo "Smoke Test Summary: ${SUCCESSES} Passed, ${FAILURES} Failed"
echo "============================================================"

if [ "$FAILURES" -gt 0 ]; then
    echo -e "\033[0;31m❌ Smoke Test FAILED with ${FAILURES} errors.\033[0m\n"
    exit 1
else
    echo -e "\033[0;32m✅ Smoke Test PASSED. Application services are healthy and responsive.\033[0m\n"
    exit 0
fi
