#!/usr/bin/env bash
# ==============================================================================
# Telegram Backup Bot — Production Preflight Verification Script
# ==============================================================================
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
STORAGE_DIR="${STORAGE_DIR:-./storage}"
MONGO_BACKUP_DIR="${MONGO_BACKUP_DIR:-./backups/mongodb}"
STORAGE_BACKUP_DIR="${STORAGE_BACKUP_DIR:-./backups/storage}"

FAILURES=0
WARNINGS=0

pass() {
    echo -e "  \033[0;32m[PASS]\033[0m $1"
}

warn() {
    echo -e "  \033[0;33m[WARN]\033[0m $1"
    WARNINGS=$((WARNINGS + 1))
}

fail() {
    echo -e "  \033[0;31m[FAIL]\033[0m $1"
    FAILURES=$((FAILURES + 1))
}

echo "============================================================"
echo "🔍 TELEGRAM BACKUP BOT — PRODUCTION PREFLIGHT CHECK"
echo "============================================================"

# ------------------------------------------------------------------------------
# 1. System & Command Dependencies
# ------------------------------------------------------------------------------
echo -e "\n1. System Dependencies:"

if command -v docker &> /dev/null; then
    pass "Docker CLI is installed ($(docker --version))"
else
    fail "Docker CLI is not installed"
fi

if docker compose version &> /dev/null; then
    pass "Docker Compose is available ($(docker compose version --short))"
elif command -v docker-compose &> /dev/null; then
    pass "docker-compose standalone is available"
else
    fail "Docker Compose is not installed"
fi

if command -v docker &> /dev/null && docker info &> /dev/null; then
    pass "Docker daemon is running and accessible"
else
    warn "Docker daemon is not running or current user lacks docker group permissions"
fi

for cmd in curl tar gzip du find awk grep; do
    if command -v "$cmd" &> /dev/null; then
        pass "Command '$cmd' is available"
    else
        fail "Required command '$cmd' is missing"
    fi
done

# ------------------------------------------------------------------------------
# 2. Repository Structure & Files
# ------------------------------------------------------------------------------
echo -e "\n2. Repository Structure:"

for req_path in "app" "frontend" "Dockerfile" "${PROD_COMPOSE_FILE}" "deploy/nginx/nginx.conf"; do
    if [ -e "$req_path" ]; then
        pass "Required repository path '$req_path' exists"
    else
        fail "Required repository path '$req_path' is missing"
    fi
done

# ------------------------------------------------------------------------------
# 3. Environment & Secrets Configuration
# ------------------------------------------------------------------------------
echo -e "\n3. Environment & Configuration Check:"

if [ -f "$ENV_FILE" ]; then
    pass "Environment file '$ENV_FILE' found"
    
    # Load variables safely from env file for inspection
    set +e
    ENV_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^ENVIRONMENT=' | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    BOT_TOKEN_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^(BOT_TOKEN|TELEGRAM_BOT_TOKEN)=' | head -n1 | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    MONGO_URI_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^MONGODB_URI=' | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    SESSION_SEC_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^WEB_SESSION_SECRET=' | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    SEC_KEY_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^SECRET_KEY=' | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    JWT_SEC_VAL=$(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | grep -E '^JWT_SECRET=' | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
    set -e

    if [ "$ENV_VAL" = "production" ]; then
        pass "ENVIRONMENT is set to 'production'"
        
        # Validate Telegram BOT_TOKEN format (regex: digits:token_secret)
        if [[ -n "$BOT_TOKEN_VAL" && "$BOT_TOKEN_VAL" =~ ^[0-9]{6,14}:[A-Za-z0-9_-]{20,50}$ ]]; then
            pass "BOT_TOKEN is set with valid Telegram token format"
        else
            fail "BOT_TOKEN is missing or has invalid format for production (<bot_id>:<secret>)"
        fi

        # Validate MONGODB_URI
        if [[ -n "$MONGO_URI_VAL" && ( "$MONGO_URI_VAL" =~ ^mongodb:// || "$MONGO_URI_VAL" =~ ^mongodb\+srv:// ) ]]; then
            pass "MONGODB_URI is configured with valid protocol"
        else
            fail "MONGODB_URI is missing or invalid in production"
        fi

        # Validate WEB_SESSION_SECRET length >= 32
        if [ -n "$SESSION_SEC_VAL" ]; then
            SEC_LEN=${#SESSION_SEC_VAL}
            if [ "$SEC_LEN" -ge 32 ]; then
                # Check for weak patterns
                SEC_LOWER=$(echo "$SESSION_SEC_VAL" | tr '[:upper:]' '[:lower:]')
                if [[ "$SEC_LOWER" =~ (change|default|insecure|password|123456|secret) ]]; then
                    warn "WEB_SESSION_SECRET contains common keywords; ensure sufficient entropy"
                else
                    pass "WEB_SESSION_SECRET meets production strength requirements (>= 32 chars)"
                fi
            else
                fail "WEB_SESSION_SECRET is too short ($SEC_LEN chars, minimum 32 required)"
            fi
        else
            fail "WEB_SESSION_SECRET is missing in production"
        fi

        # Validate SECRET_KEY & JWT_SECRET
        if [[ -n "$SEC_KEY_VAL" && ! "$SEC_KEY_VAL" =~ (default-insecure|change-in-production) ]]; then
            pass "SECRET_KEY is configured with non-default value"
        else
            warn "SECRET_KEY uses default or insecure placeholder"
        fi

        if [[ -n "$JWT_SEC_VAL" && ! "$JWT_SEC_VAL" =~ (default-insecure|change-in-production) ]]; then
            pass "JWT_SECRET is configured with non-default value"
        else
            warn "JWT_SECRET uses default or insecure placeholder"
        fi
    else
        warn "ENVIRONMENT is not set to 'production' (current: '${ENV_VAL:-unset}')"
    fi
else
    warn "Environment file '$ENV_FILE' not found. Using system environment variables."
fi

# ------------------------------------------------------------------------------
# 4. Storage & Backup Directories & Permissions
# ------------------------------------------------------------------------------
echo -e "\n4. Storage & Filesystem Health:"

for dir in "$STORAGE_DIR" "$STORAGE_DIR/.tmp-downloads" "./secrets" "$MONGO_BACKUP_DIR" "$STORAGE_BACKUP_DIR"; do
    if mkdir -p "$dir" 2>/dev/null; then
        # Test write and delete
        TEST_FILE="${dir}/.preflight_write_test_$$"
        if touch "$TEST_FILE" 2>/dev/null && rm -f "$TEST_FILE" 2>/dev/null; then
            pass "Directory '$dir' is writable"
        else
            fail "Directory '$dir' is not writable by current user"
        fi
    else
        fail "Cannot create or access directory '$dir'"
    fi
done

# Disk space check
if command -v df &> /dev/null; then
    DISK_USAGE_PCT=$(df -k "$STORAGE_DIR" | awk 'NR==2 {gsub("%",""); print $5}')
    if [ -n "$DISK_USAGE_PCT" ]; then
        if [ "$DISK_USAGE_PCT" -ge 90 ]; then
            fail "Disk usage on storage volume is critically high (${DISK_USAGE_PCT}% >= 90%)"
        elif [ "$DISK_USAGE_PCT" -ge 80 ]; then
            warn "Disk usage on storage volume is high (${DISK_USAGE_PCT}% >= 80%)"
        else
            pass "Storage volume disk capacity is healthy (${DISK_USAGE_PCT}% used)"
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 5. Production Docker Compose Validation
# ------------------------------------------------------------------------------
echo -e "\n5. Production Compose Specification:"

if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    if [ -f "$PROD_COMPOSE_FILE" ]; then
        if docker compose -f "$PROD_COMPOSE_FILE" config -q 2>/dev/null; then
            pass "Compose configuration '$PROD_COMPOSE_FILE' is valid"
        else
            warn "Compose config check failed (check required environment variables in '$ENV_FILE')"
        fi
    else
        fail "Production compose file '$PROD_COMPOSE_FILE' not found"
    fi
fi

# ------------------------------------------------------------------------------
# 6. Port Availability Checks
# ------------------------------------------------------------------------------
echo -e "\n6. Port Availability:"

check_port() {
    local port="$1"
    local desc="$2"
    if command -v ss &> /dev/null; then
        if ss -tuln | grep -q ":${port} "; then
            warn "Port ${port} (${desc}) is currently in use"
        else
            pass "Port ${port} (${desc}) is available"
        fi
    elif command -v netstat &> /dev/null; then
        if netstat -tuln | grep -q ":${port} "; then
            warn "Port ${port} (${desc}) is currently in use"
        else
            pass "Port ${port} (${desc}) is available"
        fi
    else
        pass "Port ${port} check skipped (ss/netstat not available)"
    fi
}

check_port 80 "HTTP / Nginx"
check_port 443 "HTTPS / TLS"
check_port 8000 "FastAPI internal"

# ------------------------------------------------------------------------------
# Summary & Result
# ------------------------------------------------------------------------------
echo -e "\n============================================================"
echo "Preflight Results: ${FAILURES} Failures, ${WARNINGS} Warnings"
echo "============================================================"

if [ "$FAILURES" -gt 0 ]; then
    echo -e "\033[0;31m❌ Preflight FAILED. Fix the issues above before deploying to production.\033[0m\n"
    exit 1
else
    echo -e "\033[0;32m✅ Preflight PASSED. Server environment is ready for production deployment.\033[0m\n"
    exit 0
fi
