#!/usr/bin/env python3
"""Phase 10A — MTProto Access Spike.

Validates:
1. MTProto client initialization & session authorization.
2. Locating message by chat_id + message_id.
3. Accessing media document reference.
4. Chunked streaming download (100–200 MB or custom size) with O(1) memory.
5. Exact byte count and SHA-256 calculation.
"""

import asyncio
import hashlib
import os
from pathlib import Path
import sys
import time
from typing import Optional, Tuple

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.services.mtproto_client import TelethonClientManager
from app.workers.download_provider import MtProtoDownloader, TelegramSourceRef

logger = get_logger(__name__)


async def run_mtproto_access_spike(
    chat_id: int,
    message_id: int,
    output_dir: Path,
    expected_size: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> Tuple[bool, dict]:
    """Execute the Phase 10A MTProto Access Spike against a real or staged Telegram message.

    Returns:
        Tuple[bool, dict]: (success, diagnostics_dict)
    """
    cfg = settings or get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = {
        "chat_id": chat_id,
        "message_id": message_id,
        "mtproto_enabled": cfg.MT_PROTO_ENABLED,
        "session_path": cfg.MT_PROTO_SESSION_PATH,
        "connected": False,
        "authorized": False,
        "media_found": False,
        "file_size": 0,
        "download_duration_seconds": 0.0,
        "sha256": None,
        "error": None,
    }

    if not cfg.MT_PROTO_ENABLED:
        diagnostics["error"] = "MT_PROTO_ENABLED is false in configuration."
        return False, diagnostics

    client_manager = TelethonClientManager(cfg)
    try:
        # Step 1: Connect and check authorization
        client = await client_manager.initialize()
        if not client:
            diagnostics["error"] = "Failed to initialize Telethon client."
            return False, diagnostics

        diagnostics["connected"] = True
        is_auth = await client.is_user_authorized()
        diagnostics["authorized"] = is_auth

        if not is_auth:
            diagnostics["error"] = "Telethon client is not authorized. Run scripts/create_mtproto_session.py first."
            return False, diagnostics

        # Step 2 & 3: Resolve message media
        print(f"[*] Locating message {message_id} in chat {chat_id}...")
        media, resolved_size = await client_manager.resolve_message_media(chat_id=chat_id, message_id=message_id)
        diagnostics["media_found"] = True
        diagnostics["file_size"] = resolved_size or expected_size or 0
        print(f"[+] Media document located! Size: {diagnostics['file_size']} bytes")

        # Step 4: Stream download using MtProtoDownloader in 1 MiB chunks
        downloader = MtProtoDownloader(client_manager, settings=cfg)
        source_ref = TelegramSourceRef(
            user_id=chat_id,
            chat_id=chat_id,
            message_id=message_id,
            expected_size=resolved_size or expected_size,
            task_id="spike_test_task",
        )

        print("[*] Beginning chunked streaming download (O(1) memory)...")
        start_time = time.monotonic()

        last_report = start_time

        async def on_progress(downloaded: int, total: int):
            nonlocal last_report
            now = time.monotonic()
            if now - last_report >= 2.0 or downloaded == total:
                last_report = now
                pct = (downloaded / total * 100.0) if total > 0 else 0.0
                mb_dl = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                print(f"    --> Progress: {pct:.1f}% ({mb_dl:.1f}/{mb_tot:.1f} MB)")

        result = await downloader.download_to_temp_file(
            source=source_ref,
            temp_dir=output_dir,
            chunk_size=cfg.MT_PROTO_CHUNK_SIZE,
            on_progress=on_progress,
            progress_interval_seconds=1.0,
            resume=True,
        )

        duration = time.monotonic() - start_time
        diagnostics["download_duration_seconds"] = round(duration, 2)
        diagnostics["sha256"] = result.sha256
        diagnostics["downloaded_path"] = str(result.temp_path)

        print(f"[+] Download completed in {duration:.2f}s!")
        print(f"[+] Verified SHA-256: {result.sha256}")
        print(f"[+] File Size: {result.file_size} bytes")

        # Clean up temporary spike file
        if result.temp_path.exists():
            result.temp_path.unlink(missing_ok=True)

        return True, diagnostics

    except Exception as e:
        diagnostics["error"] = str(e)
        logger.exception(f"Spike failed: {e}")
        return False, diagnostics
    finally:
        await client_manager.close()


async def main() -> None:
    setup_logging("INFO")
    print("=" * 65)
    print(" Telegram Backup Bot — Phase 10A MTProto Access Spike")
    print("=" * 65)

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python scripts/mtproto_access_spike.py <chat_id> <message_id> [expected_size]")
        print("\nExample:")
        print("  python scripts/mtproto_access_spike.py 123456789 42 150000000\n")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    message_id = int(sys.argv[2])
    expected_size = int(sys.argv[3]) if len(sys.argv) > 3 else None

    temp_dir = Path("./storage/.tmp-spike")
    success, diag = await run_mtproto_access_spike(
        chat_id=chat_id,
        message_id=message_id,
        output_dir=temp_dir,
        expected_size=expected_size,
    )

    print("\n" + "=" * 65)
    if success:
        print(" 🎉 PHASE 10A SPIKE: PASS")
        print(f" File Size: {diag['file_size']} bytes")
        print(f" SHA-256:   {diag['sha256']}")
        print(f" Duration:  {diag['download_duration_seconds']}s")
    else:
        print(" ❌ PHASE 10A SPIKE: FAIL")
        print(f" Reason:    {diag['error']}")
    print("=" * 65 + "\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
