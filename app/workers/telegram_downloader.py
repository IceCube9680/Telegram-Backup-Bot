"""Telegram file retrieval and streaming download abstraction with incremental hashing."""

import asyncio
import hashlib
import os
from pathlib import Path
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Optional
import uuid
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.workers.retry import TelegramDownloadError, TelegramPermanentError

logger = get_logger(__name__)


class TelegramFileInfo(BaseModel):
    """Metadata about a downloadable Telegram file."""

    file_id: str = Field(..., description="Telegram file identifier")
    file_unique_id: Optional[str] = Field(default=None, description="Unique file identifier")
    file_path: str = Field(..., description="Relative file path on Telegram servers")
    file_size: Optional[int] = Field(default=None, ge=0, description="File size in bytes if reported")


class DownloadResult(BaseModel):
    """Result summary of a streaming download operation."""

    temp_path: Path = Field(..., description="Absolute path to downloaded temporary file")
    sha256: str = Field(..., description="Computed SHA-256 hexadecimal hash")
    file_size: int = Field(..., ge=0, description="Total downloaded bytes")
    file_unique_id: Optional[str] = Field(default=None, description="Telegram unique file ID")


class TelegramDownloader:
    """Dedicated service for downloading files from Telegram Bot API with memory-safe streaming."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def get_file_info(self, file_id: str) -> TelegramFileInfo:
        """Query Telegram Bot API for file metadata and remote download path.

        Raises:
            TelegramPermanentError: If the file ID is invalid or cannot be retrieved.
            TelegramDownloadError: If a transient network or server error occurs.
        """
        try:
            tg_file = await self.bot.get_file(file_id)
        except TelegramBadRequest as e:
            logger.error(f"Permanent Telegram error retrieving file info for {file_id}: {e}")
            raise TelegramPermanentError(
                message=f"Telegram rejected file ID: {str(e)}",
                details={"file_id": file_id, "error": str(e)},
            ) from e
        except TelegramAPIError as e:
            logger.warning(f"Telegram API error retrieving file info for {file_id}: {e}")
            raise TelegramDownloadError(
                message=f"Telegram API error: {str(e)}",
                details={"file_id": file_id, "error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error getting Telegram file info for {file_id}: {e}")
            raise TelegramDownloadError(
                message=f"Failed to retrieve file info: {str(e)}",
                details={"file_id": file_id, "error": str(e)},
            ) from e

        if not tg_file or not tg_file.file_path:
            raise TelegramPermanentError(
                message="Telegram file path is unavailable (file may exceed Bot API 20MB limit or be expired)",
                details={"file_id": file_id},
            )

        return TelegramFileInfo(
            file_id=tg_file.file_id,
            file_unique_id=tg_file.file_unique_id,
            file_path=tg_file.file_path,
            file_size=tg_file.file_size,
        )

    async def download_stream(
        self,
        file_path: str,
        chunk_size: int = 65536,
        timeout: int = 60,
    ) -> AsyncIterator[bytes]:
        """Stream chunks of binary content directly from Telegram Bot API."""
        try:
            url = self.bot.session.api.file_url(self.bot.token, file_path)
            async for chunk in self.bot.session.stream_content(
                url=url,
                timeout=timeout,
                chunk_size=chunk_size,
                raise_for_status=True,
            ):
                if chunk:
                    yield chunk
        except (TelegramAPIError, asyncio.TimeoutError, TimeoutError, ConnectionError) as e:
            logger.warning(f"Transient streaming error for path {file_path}: {e}")
            raise TelegramDownloadError(
                message=f"Telegram streaming error: {str(e)}",
                details={"file_path": file_path, "error": str(e)},
            ) from e
        except Exception as e:
            logger.error(f"Unexpected streaming error for path {file_path}: {e}")
            raise TelegramDownloadError(
                message=f"Failed to stream Telegram file: {str(e)}",
                details={"file_path": file_path, "error": str(e)},
            ) from e

    async def download_to_temp_file(
        self,
        file_id: str,
        temp_dir: Path,
        chunk_size: int = 65536,
        expected_size: Optional[int] = None,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
        progress_interval_seconds: float = 1.5,
    ) -> DownloadResult:
        """Stream Telegram file directly into a secure temporary file while incrementally calculating SHA-256.

        Ensures O(chunk_size) memory usage and cleans up temporary files on error.
        """
        temp_dir = temp_dir.resolve()
        await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)

        unique_id = uuid.uuid4().hex
        temp_path = temp_dir / f".tmp_dl_{unique_id}.bin"

        file_info = await self.get_file_info(file_id)
        target_size = file_info.file_size or expected_size or 0

        hasher = hashlib.sha256()
        downloaded_bytes = 0
        last_progress_time = time.monotonic()

        try:
            def _open_temp():
                return open(temp_path, "wb")

            f = await asyncio.to_thread(_open_temp)
            try:
                async for chunk in self.download_stream(file_info.file_path, chunk_size=chunk_size):
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
                                logger.debug(f"Progress callback ignored error: {pe}")

                await asyncio.to_thread(f.flush)
                await asyncio.to_thread(os.fsync, f.fileno())
            finally:
                await asyncio.to_thread(f.close)

            # Check file integrity if Telegram size was provided
            if file_info.file_size is not None and file_info.file_size > 0:
                if downloaded_bytes != file_info.file_size:
                    raise TelegramDownloadError(
                        message=f"Downloaded size mismatch: received {downloaded_bytes} bytes, expected {file_info.file_size} bytes",
                        details={
                            "file_id": file_id,
                            "downloaded_bytes": downloaded_bytes,
                            "expected_size": file_info.file_size,
                        },
                    )

            # Final 100% progress update if callback supplied
            if on_progress:
                try:
                    await on_progress(downloaded_bytes, downloaded_bytes or target_size)
                except Exception:
                    pass

            sha256_hex = hasher.hexdigest()
            logger.debug(
                f"Completed download of {file_id}: {downloaded_bytes} bytes, sha256={sha256_hex[:8]}..."
            )

            return DownloadResult(
                temp_path=temp_path,
                sha256=sha256_hex,
                file_size=downloaded_bytes,
                file_unique_id=file_info.file_unique_id,
            )

        except Exception as e:
            # Ensure temporary file is cleanly removed on any failure
            if temp_path.exists():
                try:
                    await asyncio.to_thread(temp_path.unlink, missing_ok=True)
                except Exception as clean_err:
                    logger.warning(f"Failed to remove temporary file {temp_path}: {clean_err}")
            raise
