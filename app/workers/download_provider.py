"""Telegram Download Provider Abstraction (Bot API and MTProto)."""

from abc import ABC, abstractmethod
import asyncio
import hashlib
import os
from pathlib import Path
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Tuple
import uuid
from aiogram import Bot
from pydantic import BaseModel, Field
from telethon import TelegramClient
from telethon.errors import (
    FileMigrateError,
    FileReferenceExpiredError,
    FloodWaitError,
    RPCError,
)

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.mtproto_client import (
    TelegramFileRefExpiredError,
    TelegramFloodWaitError,
    TelethonClientManager,
)
from app.workers.retry import (
    TelegramDownloadError,
    TelegramPermanentError,
)
from app.workers.telegram_downloader import DownloadResult, TelegramFileInfo, TelegramDownloader

logger = get_logger(__name__)


class TelegramSourceRef(BaseModel):
    """Normalized reference to a downloadable Telegram media source."""

    user_id: int = Field(..., description="Telegram user ID owning the source")
    chat_id: Optional[int] = Field(default=None, description="Telegram chat ID where media is located")
    message_id: int = Field(..., description="Original Telegram message ID")
    file_id: Optional[str] = Field(default=None, description="Bot API file identifier")
    file_unique_id: Optional[str] = Field(default=None, description="Telegram unique file identifier")
    media_type: str = Field(default="document", description="Media classification type")
    expected_size: Optional[int] = Field(default=None, ge=0, description="Expected file size in bytes")
    task_id: Optional[str] = Field(default=None, description="Associated background task ID")


class TelegramDownloadProvider(ABC):
    """Abstract interface for Telegram media download providers."""

    @abstractmethod
    async def download_to_temp_file(
        self,
        source: TelegramSourceRef,
        temp_dir: Path,
        chunk_size: int = 1048576,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
        progress_interval_seconds: float = 2.0,
        resume: bool = True,
    ) -> DownloadResult:
        """Stream media directly into temporary file with incremental SHA-256 calculation."""
        pass


class BotApiDownloader(TelegramDownloadProvider):
    """Standard Telegram Bot API downloader for normal files (<= 20 MiB)."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._downloader = TelegramDownloader(bot)

    async def download_to_temp_file(
        self,
        source: TelegramSourceRef,
        temp_dir: Path,
        chunk_size: int = 65536,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
        progress_interval_seconds: float = 2.0,
        resume: bool = True,
    ) -> DownloadResult:
        """Download file via standard Telegram Bot API getFile streaming."""
        if not source.file_id:
            raise TelegramPermanentError(
                message="Missing file_id for Bot API download",
                details={"source": source.model_dump()},
            )

        return await self._downloader.download_to_temp_file(
            file_id=source.file_id,
            temp_dir=temp_dir,
            chunk_size=chunk_size,
            expected_size=source.expected_size,
            on_progress=on_progress,
            progress_interval_seconds=progress_interval_seconds,
        )


class MtProtoDownloader(TelegramDownloadProvider):
    """High-performance MTProto downloader for large files up to 4 GiB using chunked streaming and resume."""

    def __init__(
        self,
        client_manager: TelethonClientManager,
        settings: Optional[Settings] = None,
    ) -> None:
        self.client_manager = client_manager
        self.settings = settings or get_settings()

    async def _compute_partial_hash_and_offset(
        self, part_path: Path, expected_size: Optional[int]
    ) -> Tuple[Any, int]:
        """Re-read existing .part file sequentially to build SHA-256 state and return (hasher, valid_offset)."""
        hasher = hashlib.sha256()
        existing_size = await asyncio.to_thread(lambda: part_path.stat().st_size if part_path.exists() else 0)

        if existing_size <= 0:
            return hasher, 0

        # If partial file is unexpectedly larger than expected size, invalidate
        if expected_size and existing_size > expected_size:
            logger.warning(
                f"Partial file {part_path} ({existing_size} bytes) exceeds expected size ({expected_size} bytes). Resetting."
            )
            await asyncio.to_thread(part_path.unlink, missing_ok=True)
            return hashlib.sha256(), 0

        # Read partial file in 1 MiB chunks to rebuild hasher in O(1) memory
        def _read_and_hash() -> int:
            bytes_read = 0
            with open(part_path, "rb") as f:
                while chunk := f.read(1048576):
                    hasher.update(chunk)
                    bytes_read += len(chunk)
            return bytes_read

        valid_bytes = await asyncio.to_thread(_read_and_hash)
        logger.info(f"[resume_state_rebuilt] part_path={part_path.name} valid_offset={valid_bytes} bytes")
        return hasher, valid_bytes

    async def download_to_temp_file(
        self,
        source: TelegramSourceRef,
        temp_dir: Path,
        chunk_size: int = 1048576,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
        progress_interval_seconds: float = 2.0,
        resume: bool = True,
    ) -> DownloadResult:
        """Stream Telegram MTProto file in chunks with resumable offset, bounded memory, and incremental SHA-256."""
        temp_dir = temp_dir.resolve()
        await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)

        task_id = source.task_id or uuid.uuid4().hex
        part_filename = f".tmp_mtproto_{task_id}.part"
        part_path = temp_dir / part_filename

        chat_id = source.chat_id or source.user_id
        message_id = source.message_id

        # 1. Resolve MTProto media reference
        client: TelegramClient = await self.client_manager.get_client()
        media, resolved_size = await self.client_manager.resolve_message_media(
            chat_id=chat_id,
            message_id=message_id,
            expected_size=source.expected_size,
            media_type=source.media_type,
            file_unique_id=source.file_unique_id,
        )
        target_size = resolved_size or source.expected_size or 0

        # Enforce exact 4 GiB platform hard limit (4,294,967,296 bytes)
        HARD_LIMIT_4_GIB = 4294967296
        if target_size > HARD_LIMIT_4_GIB:
            raise TelegramPermanentError(
                message=f"File size ({target_size} bytes) exceeds maximum supported limit of 4 GiB (4,294,967,296 bytes).",
                details={"file_size": target_size, "max_allowed": HARD_LIMIT_4_GIB},
            )

        # 2. Check and initialize resume state
        hasher = hashlib.sha256()
        start_offset = 0

        if resume and self.settings.LARGE_FILE_RESUME_ENABLED and part_path.exists():
            try:
                hasher, start_offset = await self._compute_partial_hash_and_offset(part_path, target_size)
            except Exception as re:
                logger.warning(f"Failed to inspect partial file {part_path}: {re}. Starting from 0.")
                await asyncio.to_thread(part_path.unlink, missing_ok=True)
                hasher = hashlib.sha256()
                start_offset = 0

        downloaded_bytes = start_offset
        last_progress_time = time.monotonic()

        # Send initial progress if resumed
        if on_progress and start_offset > 0:
            try:
                await on_progress(downloaded_bytes, target_size)
            except Exception:
                pass

        logger.info(
            f"[mtproto_stream_start] task={task_id} offset={start_offset}/{target_size} bytes chunk_size={chunk_size}"
        )

        try:
            def _open_for_append():
                return open(part_path, "ab" if start_offset > 0 else "wb")

            f = await asyncio.to_thread(_open_for_append)
            try:
                # Use Telethon iter_download with offset and chunk request_size
                async for chunk in client.iter_download(
                    file=media,
                    offset=start_offset,
                    request_size=chunk_size,
                ):
                    if chunk:
                        await asyncio.to_thread(f.write, chunk)
                        hasher.update(chunk)
                        downloaded_bytes += len(chunk)

                        now = time.monotonic()
                        if on_progress and (now - last_progress_time >= progress_interval_seconds):
                            last_progress_time = now
                            try:
                                await on_progress(downloaded_bytes, target_size)
                            except Exception as pe:
                                logger.debug(f"MTProto progress callback error: {pe}")

                await asyncio.to_thread(f.flush)
                await asyncio.to_thread(os.fsync, f.fileno())
            finally:
                await asyncio.to_thread(f.close)

            # 3. Verify total downloaded byte size
            if target_size > 0 and downloaded_bytes != target_size:
                raise TelegramDownloadError(
                    message=f"MTProto download size mismatch: received {downloaded_bytes} bytes, expected {target_size} bytes",
                    details={
                        "downloaded_bytes": downloaded_bytes,
                        "expected_size": target_size,
                        "task_id": task_id,
                    },
                )

            # Final 100% progress callback
            if on_progress:
                try:
                    await on_progress(downloaded_bytes, downloaded_bytes or target_size)
                except Exception:
                    pass

            sha256_hex = hasher.hexdigest()
            logger.info(
                f"[mtproto_download_complete] task={task_id} size={downloaded_bytes} sha256={sha256_hex[:8]}..."
            )

            return DownloadResult(
                temp_path=part_path,
                sha256=sha256_hex,
                file_size=downloaded_bytes,
                file_unique_id=source.file_unique_id,
            )

        except FloodWaitError as fe:
            logger.warning(f"MTProto FloodWait encountered: wait {fe.seconds}s")
            raise TelegramFloodWaitError(wait_seconds=fe.seconds) from fe
        except FileReferenceExpiredError as fre:
            logger.warning(f"MTProto FileReferenceExpired: {fre}")
            raise TelegramFileRefExpiredError() from fre
        except FileMigrateError as fme:
            logger.warning(f"MTProto FileMigrateError to DC {fme.new_dc}")
            raise TelegramDownloadError(
                message=f"Telegram DC migration required to DC {fme.new_dc}",
                details={"new_dc": fme.new_dc},
            ) from fme
        except RPCError as rpc:
            logger.error(f"MTProto RPC error during download: {rpc}")
            raise TelegramDownloadError(
                message=f"Telegram RPC error: {str(rpc)}",
                details={"error": str(rpc)},
            ) from rpc
        except Exception as e:
            if isinstance(e, (TelegramPermanentError, TelegramDownloadError)):
                raise
            logger.error(f"Unexpected MTProto download error: {e}")
            raise TelegramDownloadError(
                message=f"MTProto download failed: {str(e)}",
                details={"error": str(e), "task_id": task_id},
            ) from e
