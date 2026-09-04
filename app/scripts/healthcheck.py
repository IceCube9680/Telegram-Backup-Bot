"""Production smoke-test and healthcheck CLI utility."""

import asyncio
from pathlib import Path
import sys
import urllib.request
from typing import Dict, Any

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.mongo import mongo_manager
from app.services.disk_service import get_disk_health


async def run_healthcheck() -> int:
    setup_logging("WARNING")
    settings = get_settings()

    print("\n" + "=" * 60)
    print("🩺 TELEGRAM BACKUP BOT — HEALTH CHECK")
    print("=" * 60)

    is_healthy = True

    # 1. MongoDB Health
    try:
        db_connected = await mongo_manager.ping()
        if db_connected:
            print(f"[{'PASS':^6}] MongoDB Connection:   Connected ({settings.MONGODB_DATABASE})")
        else:
            print(f"[{'FAIL':^6}] MongoDB Connection:   Failed to ping database")
            is_healthy = False
    except Exception as e:
        print(f"[{'FAIL':^6}] MongoDB Connection:   Error ({e})")
        is_healthy = False

    # 2. Storage Directory Health & Disk Space
    try:
        disk_health = await get_disk_health(settings)
        free_mb = round(disk_health.free_bytes / (1024 * 1024), 1)
        total_mb = round(disk_health.total_bytes / (1024 * 1024), 1)

        if disk_health.status == "healthy":
            status_tag = "PASS"
        elif disk_health.status == "warning":
            status_tag = "WARN"
        else:
            status_tag = "FAIL"
            is_healthy = False

        print(
            f"[{status_tag:^6}] Storage Disk Space:   {disk_health.usage_percent}% used ({free_mb} MB free / {total_mb} MB total)"
        )
    except Exception as e:
        print(f"[{'FAIL':^6}] Storage Directory:    Error ({e})")
        is_healthy = False

    # 3. HTTP API Endpoint (Optional if running)
    api_url = f"http://localhost:{settings.API_PORT}/health/live"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "healthcheck-cli"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print(f"[{'PASS':^6}] API HTTP Service:     Running (HTTP 200 at {api_url})")
            else:
                print(f"[{'WARN':^6}] API HTTP Service:     Returned HTTP {resp.status}")
    except Exception:
        print(f"[{'INFO':^6}] API HTTP Service:     Not running or not reachable on {api_url}")

    # 4. Telegram Bot Token configured
    token = settings.telegram_token
    if token:
        masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
        print(f"[{'PASS':^6}] Telegram Bot Token:   Configured ({masked})")
    else:
        print(f"[{'WARN':^6}] Telegram Bot Token:   Not configured")

    print("-" * 60)
    if is_healthy:
        print("Overall Status: ✅ HEALTHY\n")
        return 0
    else:
        print("Overall Status: ❌ UNHEALTHY / DEGRADED\n")
        return 1


def main() -> None:
    code = asyncio.run(run_healthcheck())
    sys.exit(code)


if __name__ == "__main__":
    main()
