import asyncio
import os
import stat
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Tuple, Union
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FileMigrateError,
    FileReferenceExpiredError,
    FloodWaitError,
    RPCError,
    SessionPasswordNeededError,
    UserDeactivatedError,
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
    MTProtoAccessError,
    TelegramDownloadError,
    TelegramFileRefExpiredError,
    TelegramFloodWaitError,
    TelegramPermanentError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class TelethonClientManager:
    """Manages dedicated server-side Telethon MTProto bot client lifecycle and session security."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self._connected = False

    def _ensure_session_dir_permissions(self, session_path: Path) -> None:
        """Ensure session directory exists and has appropriate POSIX filesystem permissions."""
        try:
            session_dir = session_path.parent
            session_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(session_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            except Exception:
                pass

            if session_path.exists():
                try:
                    os.chmod(session_path, stat.S_IRUSR | stat.S_IWUSR)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to enforce permissions on session path {session_path}: {e}")

    async def initialize(self) -> Optional[TelegramClient]:
        """Initialize and connect Telethon MTProto client using Bot Token authorization."""
        if not self.settings.MT_PROTO_ENABLED:
            logger.debug("MTProto is disabled in settings.")
            return None

        async with self._lock:
            if self.client and self._connected:
                return self.client

            api_id = self.settings.MT_PROTO_API_ID
            api_hash = self.settings.MT_PROTO_API_HASH
            session_str_or_path = self.settings.MT_PROTO_SESSION_PATH
            bot_token = self.settings.telegram_token or self.settings.BOT_TOKEN or self.settings.TELEGRAM_BOT_TOKEN

            if not api_id or not api_hash:
                raise ConfigurationError(
                    message="MT_PROTO_API_ID and MT_PROTO_API_HASH are required when MT_PROTO_ENABLED=true.",
                    details={"env_key": "MT_PROTO_API_ID"},
                )

            if not bot_token:
                raise ConfigurationError(
                    message="BOT_TOKEN is required for MTProto bot authorization.",
                    details={"env_key": "BOT_TOKEN"},
                )

            session_file = Path(session_str_or_path)
            self._ensure_session_dir_permissions(session_file)

            session_target = str(session_file)
            if session_target.endswith(".session"):
                session_target = session_target[:-8]

            logger.info("Initializing dedicated Bot MTProto TelegramClient...")
            self.client = TelegramClient(
                session=session_target,
                api_id=api_id,
                api_hash=api_hash,
                flood_sleep_threshold=0,  # Do not sleep automatically in library; let worker handle FLOOD_WAIT
            )

            try:
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    logger.info("Authorizing MTProto client with Bot Token (auth.importBotAuthorization)...")
                    await self.client.start(bot_token=bot_token)

                self._connected = True
                me = await self.client.get_me()
                bot_username = f"@{me.username}" if getattr(me, "username", None) else "Unknown"
                is_bot = bool(getattr(me, "bot", False))
                logger.info(
                    f"MTProto client connected and authorized as '{bot_username}' (ID: {getattr(me, 'id', None)}, Bot: {is_bot})"
                )

                # Enforce 0600 permissions on session file after authorization
                actual_session = Path(f"{session_target}.session")
                if actual_session.exists():
                    self._ensure_session_dir_permissions(actual_session)

            except Exception as e:
                logger.error(f"Failed to connect and authorize MTProto bot client: {e}")
                self._connected = False
                raise TelegramDownloadError(
                    message=f"Failed to connect MTProto bot client: {str(e)}",
                    details={"error": str(e)},
                ) from e

            return self.client

    async def get_client(self) -> TelegramClient:
        """Return connected and authorized TelegramClient or raise TelegramPermanentError."""
        if not self.client or not self._connected:
            await self.initialize()
            if not self.client or not self._connected:
                raise TelegramPermanentError(
                    message="MTProto bot client is not authorized.",
                    details={"MT_PROTO_ENABLED": self.settings.MT_PROTO_ENABLED, "session_path": self.settings.MT_PROTO_SESSION_PATH},
                )
            return self.client
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
        chat_id: Union[int, str],
        message_id: int,
        expected_size: Optional[int] = None,
        media_type: Optional[str] = None,
        file_unique_id: Optional[str] = None,
    ) -> Tuple[Any, Optional[int]]:
        """Resolve Telegram media object and file size from target chat and message ID via MTProto."""
        client = await self.get_client()

        # Resolve chat entity directly without fallbacks
        entity = None
        try:
            entity = await client.get_input_entity(chat_id)
        except Exception:
            try:
                entity = await client.get_entity(chat_id)
            except Exception as e:
                logger.error(f"Failed to resolve MTProto entity for chat {chat_id}: {e}")
                raise MTProtoAccessError(
                    message=f"MTProto cannot resolve chat entity {chat_id}: {str(e)}",
                    details={"chat_id": chat_id, "message_id": message_id, "error": str(e)},
                ) from e

        try:
            msg = await client.get_messages(entity, ids=message_id)
        except AuthKeyUnregisteredError as auth_err:
            logger.error(f"MTProto session key is unregistered/invalid: {auth_err}")
            self._connected = False
            raise TelegramPermanentError(
                message="MTProto session key is unregistered or revoked.",
                details={"error": str(auth_err)},
            ) from auth_err
        except FloodWaitError as fe:
            logger.warning(f"Telegram FloodWait encountered for chat {chat_id}: wait {fe.seconds}s")
            raise TelegramFloodWaitError(wait_seconds=fe.seconds) from fe
        except FileReferenceExpiredError as fre:
            logger.warning(f"Telegram file reference expired for chat {chat_id}, msg {message_id}")
            raise TelegramFileRefExpiredError() from fre
        except RPCError as rpc:
            logger.error(f"Telegram RPC error resolving message {message_id} in chat {chat_id}: {rpc}")
            raise MTProtoAccessError(
                message=f"Telegram RPC error accessing message {message_id} in chat {chat_id}: {str(rpc)}",
                details={"chat_id": chat_id, "message_id": message_id, "error": str(rpc)},
            ) from rpc
        except Exception as ex:
            logger.error(f"Unexpected error retrieving message {message_id} in chat {chat_id}: {ex}")
            raise MTProtoAccessError(
                message=f"Failed to retrieve message {message_id} in chat {chat_id}: {str(ex)}",
                details={"chat_id": chat_id, "message_id": message_id, "error": str(ex)},
            ) from ex

        if not msg:
            raise MTProtoAccessError(
                message=f"Telegram message {message_id} not found in chat {chat_id}",
                details={"chat_id": chat_id, "message_id": message_id},
            )

        media = getattr(msg, "media", None)
        if not media:
            raise MTProtoAccessError(
                message=f"Telegram message {message_id} in chat {chat_id} contains no media",
                details={"chat_id": chat_id, "message_id": message_id},
            )

        # Determine file size
        file_size: Optional[int] = None
        if isinstance(media, MessageMediaDocument) and isinstance(media.document, Document):
            file_size = media.document.size
        elif isinstance(media, MessageMediaPhoto) and isinstance(media.photo, Photo):
            if media.photo.sizes:
                file_size = getattr(media.photo.sizes[-1], "size", None)
        else:
            logger.warning(f"Message {message_id} in chat {chat_id} has media type: {type(media)}")

        logger.info(
            f"[mtproto_media_resolved] Successfully resolved message {message_id} in chat {chat_id} (media: {type(media).__name__}, size: {file_size} bytes)"
        )
        return media, file_size
