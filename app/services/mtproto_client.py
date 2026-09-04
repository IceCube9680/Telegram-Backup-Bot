"""Telegram MTProto Client Manager for large-file transfers (Telethon)."""

import asyncio
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Tuple, Union
from telethon import TelegramClient
from telethon.errors import (
    FileMigrateError,
    FileReferenceExpiredError,
    FloodWaitError,
    RPCError,
    SessionPasswordNeededError,
)
from telethon.tl.types import (
    Document,
    Message,
    MessageMediaDocument,
    MessageMediaPhoto,
    Photo,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConfigurationError,
    TelegramDownloadError,
    TelegramFileRefExpiredError,
    TelegramFloodWaitError,
    TelegramPermanentError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class TelethonClientManager:
    """Manages dedicated server-side Telethon MTProto client lifecycle and session security."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self._connected = False

    def _ensure_session_dir_permissions(self, session_path: Path) -> None:
        """Ensure session directory exists and has appropriate filesystem permissions."""
        try:
            session_dir = session_path.parent
            session_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(session_dir, 0o777)
            except Exception:
                pass

            if session_path.exists():
                try:
                    os.chmod(session_path, 0o666)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to enforce permissions on session path {session_path}: {e}")

    async def initialize(self) -> Optional[TelegramClient]:
        """Initialize and connect Telethon MTProto client if enabled."""
        if not self.settings.MT_PROTO_ENABLED:
            logger.debug("MTProto is disabled in settings.")
            return None

        async with self._lock:
            if self.client and self._connected:
                return self.client

            api_id = self.settings.MT_PROTO_API_ID
            api_hash = self.settings.MT_PROTO_API_HASH
            session_str_or_path = self.settings.MT_PROTO_SESSION_PATH

            if not api_id or not api_hash:
                raise ConfigurationError(
                    message="MT_PROTO_API_ID and MT_PROTO_API_HASH are required when MT_PROTO_ENABLED=true.",
                    details={"env_key": "MT_PROTO_API_ID"},
                )

            session_file = Path(session_str_or_path)
            self._ensure_session_dir_permissions(session_file)

            session_target = str(session_file)
            if session_target.endswith(".session"):
                session_target = session_target[:-8]

            logger.info("Initializing dedicated MTProto TelegramClient...")
            self.client = TelegramClient(
                session=session_target,
                api_id=api_id,
                api_hash=api_hash,
                flood_sleep_threshold=0,  # Do not sleep automatically in library; let worker handle FLOOD_WAIT
            )

            try:
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    logger.warning(
                        "MTProto client is connected but not authorized. Please run session authorization setup."
                    )
                else:
                    self._connected = True
                    me = await self.client.get_me()
                    first_name = getattr(me, "first_name", "Unknown") if me else "Unknown"
                    logger.info(f"MTProto client connected and authorized as '{first_name}' (ID: {getattr(me, 'id', None)})")
            except Exception as e:
                logger.error(f"Failed to connect MTProto client: {e}")
                self._connected = False
                raise TelegramDownloadError(
                    message=f"Failed to connect MTProto client: {str(e)}",
                    details={"error": str(e)},
                ) from e

            return self.client

    async def get_client(self) -> TelegramClient:
        """Return connected TelegramClient or initialize."""
        if not self.client or not self._connected:
            client = await self.initialize()
            if not client:
                raise ConfigurationError(
                    message="MTProto is not enabled or failed to initialize.",
                    details={"MT_PROTO_ENABLED": self.settings.MT_PROTO_ENABLED},
                )
            return client
        return self.client

    async def close(self) -> None:
        """Gracefully disconnect MTProto client."""
        async with self._lock:
            if self.client:
                try:
                    await self.client.disconnect()
                    logger.info("MTProto TelegramClient disconnected.")
                except Exception as e:
                    logger.warning(f"Error disconnecting MTProto client: {e}")
                finally:
                    self.client = None
                    self._connected = False

    async def resolve_message_media(
        self,
        chat_id: int,
        message_id: int,
    ) -> Tuple[Any, Optional[int]]:
        """Locate Telegram message by chat_id and message_id and return (media_object, file_size)."""
        client = await self.get_client()
        try:
            msg: Optional[Message] = await client.get_messages(chat_id, ids=message_id)
            if not msg:
                raise TelegramPermanentError(
                    message=f"Telegram message {message_id} not found in chat {chat_id}",
                    details={"chat_id": chat_id, "message_id": message_id},
                )

            media = msg.media
            if not media:
                raise TelegramPermanentError(
                    message=f"Message {message_id} in chat {chat_id} contains no media",
                    details={"chat_id": chat_id, "message_id": message_id},
                )

            # Determine file size
            file_size: Optional[int] = None
            if isinstance(media, MessageMediaDocument) and isinstance(media.document, Document):
                file_size = media.document.size
            elif isinstance(media, MessageMediaPhoto) and isinstance(media.photo, Photo):
                # Largest size in photo
                if media.photo.sizes:
                    file_size = getattr(media.photo.sizes[-1], "size", None)

            return media, file_size

        except FloodWaitError as fe:
            logger.warning(f"Telegram FloodWait encountered for chat {chat_id}: wait {fe.seconds}s")
            raise TelegramFloodWaitError(wait_seconds=fe.seconds) from fe
        except FileReferenceExpiredError as fre:
            logger.warning(f"Telegram file reference expired for chat {chat_id}, msg {message_id}")
            raise TelegramFileRefExpiredError() from fre
        except RPCError as rpc:
            logger.error(f"Telegram RPC error resolving message media: {rpc}")
            raise TelegramDownloadError(
                message=f"Telegram RPC error: {str(rpc)}",
                details={"error": str(rpc)},
            ) from rpc
        except Exception as e:
            if isinstance(e, (TelegramPermanentError, TelegramDownloadError)):
                raise
            logger.error(f"Error resolving Telegram message media: {e}")
            raise TelegramDownloadError(
                message=f"Failed to resolve Telegram media: {str(e)}",
                details={"chat_id": chat_id, "message_id": message_id, "error": str(e)},
            ) from e
