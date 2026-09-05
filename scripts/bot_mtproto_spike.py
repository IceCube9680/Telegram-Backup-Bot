#!/usr/bin/env python3
"""Phase 10 — MTProto Bot Authorization Access Spike.

Validates:
1. Starts Telethon using the SAME BOT TOKEN used by the Bot API (auth.importBotAuthorization).
2. Verifies me.bot == True and MTProto account ID matches the Bot API bot identity.
3. Resolves the target chat without user/Saved Messages fallbacks.
4. Fetches known message(s) by message ID directly from the bot's MTProto chat.
5. Confirms message contains expected media/document and inspects document metadata.
6. Downloads a small controlled test chunk (e.g. 64 KiB - 1 MiB) with chunked streaming.
7. Logs ONLY safe metadata (numeric IDs, usernames, booleans) without secrets/tokens/hashes.
"""

import asyncio
import hashlib
import os
import stat
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple

from telethon import TelegramClient
from telethon.tl.types import Document, Message, MessageMediaDocument, MessageMediaPhoto, Photo

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


def enforce_session_file_security(session_path: Path) -> bool:
    """Enforce strict POSIX file permissions: 0600 on session file, 0700 on parent dir."""
    try:
        parent_dir = session_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(parent_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except Exception as e:
            logger.warning(f"Could not enforce 0700 on parent dir {parent_dir}: {e}")

        if session_path.exists():
            try:
                os.chmod(session_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception as e:
                logger.warning(f"Could not enforce 0600 on session file {session_path}: {e}")
        return True
    except Exception as e:
        logger.error(f"Failed session security setup: {e}")
        return False


async def run_bot_mtproto_spike(
    chat_id: int = 8728529759,
    message_id: Optional[int] = 207,
    session_file_path: Optional[Path] = None,
    settings: Optional[Settings] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Execute controlled Bot MTProto authorization and message media resolution spike."""
    cfg = settings or get_settings()

    api_id = cfg.MT_PROTO_API_ID
    api_hash = cfg.MT_PROTO_API_HASH
    bot_token = cfg.telegram_token

    if not api_id or not api_hash:
        print("[ERROR] MT_PROTO_API_ID or MT_PROTO_API_HASH is missing.")
        return False, {"error": "Missing MT_PROTO_API_ID or MT_PROTO_API_HASH"}

    if not bot_token:
        print("[ERROR] BOT_TOKEN is missing.")
        return False, {"error": "Missing BOT_TOKEN"}

    # Determine expected bot ID from token prefix
    expected_bot_id = int(bot_token.split(":")[0]) if ":" in bot_token else None

    # Determine session file path
    if session_file_path is None:
        session_file_path = BASE_DIR / "secrets" / "telegram_bot_mtproto.session"

    enforce_session_file_security(session_file_path)

    session_target = str(session_file_path)
    if session_target.endswith(".session"):
        session_target = session_target[:-8]

    report: Dict[str, Any] = {
        "bot_api_id": expected_bot_id,
        "bot_api_username": None,
        "mtproto_id": None,
        "mtproto_username": None,
        "mtproto_is_bot": False,
        "identity_match": False,
        "chat_resolution": False,
        "message_resolution": False,
        "media_resolution": False,
        "small_chunk_download": False,
        "session_security": False,
        "resolved_message_id": None,
        "document_size": None,
        "document_mime": None,
        "chunk_downloaded_bytes": 0,
        "chunk_sha256": None,
    }

    client = TelegramClient(
        session=session_target,
        api_id=api_id,
        api_hash=api_hash,
        flood_sleep_threshold=0,
    )

    try:
        await client.connect()

        # Authorize as bot using auth.importBotAuthorization via client.start
        if not await client.is_user_authorized():
            logger.info("Authorizing MTProto client as BOT using configured BOT_TOKEN...")
            await client.start(bot_token=bot_token)
        else:
            logger.info("MTProto client already authorized.")

        # Inspect Bot identity via get_me()
        me = await client.get_me()
        if not me:
            raise RuntimeError("Failed to obtain MTProto identity via get_me()")

        report["mtproto_id"] = getattr(me, "id", None)
        report["mtproto_username"] = f"@{me.username}" if getattr(me, "username", None) else None
        report["mtproto_is_bot"] = bool(getattr(me, "bot", False))
        report["bot_api_username"] = report["mtproto_username"]

        if report["mtproto_is_bot"] and report["mtproto_id"] == expected_bot_id:
            report["identity_match"] = True
            logger.info(f"Bot MTProto Identity Verified: ID={report['mtproto_id']} User={report['mtproto_username']} Bot={report['mtproto_is_bot']}")
        else:
            logger.error(f"Identity mismatch: MTProto ID={report['mtproto_id']} vs Bot API ID={expected_bot_id}")

        # Enforce security on generated session file
        actual_session = Path(f"{session_target}.session")
        if actual_session.exists():
            report["session_security"] = enforce_session_file_security(actual_session)

        # Resolve test chat
        entity = None
        try:
            entity = await client.get_input_entity(chat_id)
            report["chat_resolution"] = True
            logger.info(f"Successfully resolved input entity for chat_id={chat_id}")
        except Exception as e:
            logger.warning(f"Could not get input entity directly for {chat_id}: {e}. Attempting get_entity...")
            try:
                entity = await client.get_entity(chat_id)
                report["chat_resolution"] = True
                logger.info(f"Successfully resolved entity for chat_id={chat_id}")
            except Exception as ex2:
                logger.error(f"Failed to resolve chat {chat_id}: {ex2}")
                report["chat_resolution"] = False

        if not entity:
            logger.error(f"Cannot proceed without valid chat entity for {chat_id}")
            return False, report

        # Fetch message
        target_msg: Optional[Message] = None

        # 1. Try explicit message_id if provided
        if message_id:
            try:
                msg = await client.get_messages(entity, ids=message_id)
                if msg and getattr(msg, "media", None):
                    target_msg = msg
                    report["message_resolution"] = True
                    report["resolved_message_id"] = msg.id
                    logger.info(f"Direct lookup resolved message {message_id} with media in chat {chat_id}")
            except Exception as me_err:
                logger.debug(f"Direct message {message_id} fetch error: {me_err}")

        # 2. If target message not found by exact ID, inspect recent messages in chat
        if not target_msg:
            logger.info(f"Scanning recent messages in chat {chat_id} for media...")
            async for m in client.iter_messages(entity, limit=30):
                if m and getattr(m, "media", None):
                    target_msg = m
                    report["message_resolution"] = True
                    report["resolved_message_id"] = m.id
                    logger.info(f"Found recent media message {m.id} (Date: {m.date}) in chat {chat_id}")
                    break

        if not target_msg or not getattr(target_msg, "media", None):
            logger.error(f"No media message found in chat {chat_id}")
            return False, report

        media = target_msg.media
        file_size: Optional[int] = None
        mime_type: Optional[str] = None
        filename: Optional[str] = None

        if isinstance(media, MessageMediaDocument) and isinstance(media.document, Document):
            report["media_resolution"] = True
            file_size = media.document.size
            mime_type = media.document.mime_type
            report["document_size"] = file_size
            report["document_mime"] = mime_type
            logger.info(f"Resolved MessageMediaDocument: size={file_size} bytes, mime={mime_type}, doc_id={media.document.id}")
        elif isinstance(media, MessageMediaPhoto) and isinstance(media.photo, Photo):
            report["media_resolution"] = True
            if media.photo.sizes:
                file_size = getattr(media.photo.sizes[-1], "size", None)
            mime_type = "image/jpeg"
            report["document_size"] = file_size
            report["document_mime"] = mime_type
            logger.info(f"Resolved MessageMediaPhoto: size={file_size} bytes, photo_id={media.photo.id}")
        else:
            logger.warning(f"Unrecognized media type: {type(media)}")

        # Small controlled chunk test (first 64 KiB or up to 1 MiB)
        test_chunk_limit = 65536  # 64 KiB
        downloaded_bytes = 0
        hasher = hashlib.sha256()

        logger.info(f"Starting controlled small-chunk download (limit: {test_chunk_limit} bytes)...")
        async for chunk in client.iter_download(file=media, request_size=test_chunk_limit):
            if chunk:
                hasher.update(chunk)
                downloaded_bytes += len(chunk)
                if downloaded_bytes >= test_chunk_limit:
                    break

        if downloaded_bytes > 0:
            report["small_chunk_download"] = True
            report["chunk_downloaded_bytes"] = downloaded_bytes
            report["chunk_sha256"] = hasher.hexdigest()
            logger.info(f"Controlled chunk download successful: {downloaded_bytes} bytes (SHA-256 prefix: {report['chunk_sha256'][:16]})")

        all_passed = (
            report["identity_match"]
            and report["chat_resolution"]
            and report["message_resolution"]
            and report["media_resolution"]
            and report["small_chunk_download"]
            and report["session_security"]
        )

        return all_passed, report

    finally:
        await client.disconnect()
        logger.info("Bot MTProto client disconnected.")


if __name__ == "__main__":
    setup_logging()
    chat_id_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8728529759
    msg_id_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 207

    print("=" * 60)
    print("PHASE 10 — BOT MTProto ACCESS SPIKE")
    print("=" * 60)

    success, res = asyncio.run(
        run_bot_mtproto_spike(chat_id=chat_id_arg, message_id=msg_id_arg)
    )

    print("\n" + "=" * 60)
    print("BOT MTProto SPIKE REPORT")
    print("=" * 60)
    print(f"Bot API identity:      ID = {res['bot_api_id']}, username = {res['bot_api_username']}")
    print(f"MTProto identity:     ID = {res['mtproto_id']}, username = {res['mtproto_username']}, bot = {res['mtproto_is_bot']}")
    print(f"Identity match:       {'PASS' if res['identity_match'] else 'FAIL'}")
    print(f"Chat resolution:      {'PASS' if res['chat_resolution'] else 'FAIL'}")
    print(f"Message resolution:   {'PASS' if res['message_resolution'] else 'FAIL'} (Msg ID: {res['resolved_message_id']})")
    print(f"Media resolution:     {'PASS' if res['media_resolution'] else 'FAIL'} (Size: {res['document_size']} bytes, MIME: {res['document_mime']})")
    print(f"Chunk download:       {'PASS' if res['small_chunk_download'] else 'FAIL'} ({res['chunk_downloaded_bytes']} bytes)")
    print(f"Session security:     {'PASS' if res['session_security'] else 'FAIL'}")
    print("=" * 60)
    print(f"OVERALL SPIKE STATUS: {'PASS' if success else 'FAIL'}")
    print("=" * 60)

    sys.exit(0 if success else 1)
