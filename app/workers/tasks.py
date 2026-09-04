"""Task execution orchestrator for processing background backup tasks."""

import asyncio
import os
from pathlib import Path
import shutil
from typing import Any, Dict, Optional, Tuple
from aiogram import Bot
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.models.backup_item import ItemStatus, MediaType
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.services.backup_service import format_bytes
from app.services.mtproto_client import TelegramFloodWaitError, TelethonClientManager
from app.services.storage_service import LocalStorageService, StorageService, get_storage_service
from app.workers.download_provider import (
    BotApiDownloader,
    MtProtoDownloader,
    TelegramDownloadProvider,
    TelegramSourceRef,
)
from app.workers.retry import TelegramDownloadError, TelegramPermanentError, is_retryable_error
from app.workers.telegram_downloader import DownloadResult, TelegramDownloader

logger = get_logger(__name__)


class TaskProcessor:
    """Orchestrates single backup task lifecycle: provider selection, streaming, hashing, storage, and retry."""

    def __init__(
        self,
        db: AsyncDatabase,
        bot: Bot,
        worker_id: str,
        storage_service: Optional[StorageService] = None,
        downloader: Optional[TelegramDownloader] = None,
        download_provider: Optional[TelegramDownloadProvider] = None,
        mtproto_client_manager: Optional[TelethonClientManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.bot = bot
        self.worker_id = worker_id
        self.settings = settings or get_settings()
        self.storage = storage_service or get_storage_service()
        self.downloader = downloader or TelegramDownloader(bot)
        self.mtproto_client_manager = mtproto_client_manager

        # Providers
        self._custom_provider = download_provider
        self.bot_downloader = BotApiDownloader(bot)
        self.mtproto_downloader: Optional[MtProtoDownloader] = None
        if self.mtproto_client_manager:
            self.mtproto_downloader = MtProtoDownloader(self.mtproto_client_manager, settings=self.settings)

        self.task_repo = BackupTaskRepository(db)
        self.item_repo = BackupItemRepository(db)
        self.usage_repo = StorageUsageRepository(db)

    def _extract_extension(self, original_filename: Optional[str], mime_type: Optional[str]) -> str:
        """Extract and sanitize file extension for storage key generation."""
        if original_filename and "." in original_filename:
            raw_ext = original_filename.rsplit(".", 1)[-1]
            clean = "".join(c for c in raw_ext if c.isalnum()).lower()
            if clean:
                return clean

        if mime_type and "/" in mime_type:
            raw_sub = mime_type.split("/", 1)[1]
            clean = "".join(c for c in raw_sub if c.isalnum()).lower()
            if clean:
                return clean

        return "bin"

    async def _heartbeat_loop(self, task_id: str) -> None:
        """Periodically renew task lock lease in MongoDB while processing is active."""
        interval = max(5.0, float(self.settings.WORKER_HEARTBEAT_INTERVAL))
        try:
            while True:
                await asyncio.sleep(interval)
                renewed = await self.task_repo.renew_lock(task_id, self.worker_id)
                if not renewed:
                    logger.warning(
                        f"Heartbeat: lock lease renewal failed for task {task_id} (worker={self.worker_id})"
                    )
                else:
                    logger.debug(f"Heartbeat: renewed lock for task {task_id}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Heartbeat loop encountered error for task {task_id}: {e}")

    def select_download_provider(self, file_size: Optional[int]) -> Tuple[TelegramDownloadProvider, str]:
        """Deterministically select BotApiDownloader or MtProtoDownloader based on file size threshold."""
        if self._custom_provider:
            return self._custom_provider, "custom"

        size = file_size or 0
        if size <= self.settings.LARGE_FILE_THRESHOLD:
            return self.bot_downloader, "bot_api"

        # Large file (> 20 MiB)
        if self.settings.MT_PROTO_ENABLED and self.mtproto_downloader:
            return self.mtproto_downloader, "mtproto"

        raise TelegramPermanentError(
            message=f"File size ({format_bytes(size)}) exceeds standard 20 MiB Bot API limit and MTProto large file support is not enabled.",
            details={"file_size": size, "threshold": self.settings.LARGE_FILE_THRESHOLD},
        )

    async def process_task(self, task: Dict[str, Any]) -> bool:
        """Process a claimed BackupTask through download, hashing, upload, and database synchronization.

        Returns:
            bool: True if completed or safely reconciled, False if failed/retried.
        """
        task_id = str(task.get("id") or task.get("_id"))
        user_id = int(task["user_id"])
        backup_item_id = task.get("backup_item_id")
        attempts = int(task.get("attempts", 1))

        logger.info(
            f"[task_started] worker={self.worker_id} task_id={task_id} user_id={user_id} attempt={attempts}"
        )

        # 1. Validate associated BackupItem
        if not backup_item_id:
            msg = "Missing backup_item_id in task document"
            logger.error(f"[task_failed] {msg} (task_id={task_id})")
            await self.task_repo.fail_task(task_id, msg, self.worker_id)
            return False

        item = await self.item_repo.get_by_id(user_id=user_id, item_id=backup_item_id, include_deleted=True)
        if not item:
            msg = f"BackupItem {backup_item_id} not found or user ownership mismatch"
            logger.error(f"[task_failed] {msg} (task_id={task_id})")
            await self.task_repo.fail_task(task_id, msg, self.worker_id)
            return False

        if item.get("deleted_at") is not None:
            msg = f"BackupItem {backup_item_id} was deleted before processing"
            logger.warning(f"[task_failed] {msg} (task_id={task_id})")
            await self.task_repo.fail_task(task_id, msg, self.worker_id)
            return False

        # 2. Idempotency Check: if item is already completed and storage exists, reconcile
        if item.get("status") == ItemStatus.COMPLETED.value and item.get("storage_key"):
            storage_key = item["storage_key"]
            if await self.storage.exists(storage_key):
                logger.info(
                    f"Idempotency: item {backup_item_id} is already completed at {storage_key}. Reconciling task {task_id}."
                )
                await self.task_repo.complete_task(task_id, self.worker_id)
                return True

        telegram_file_id = item.get("telegram_file_id")
        if not telegram_file_id:
            # Handle text/url items that don't have Telegram file binaries
            if item.get("media_type") in (MediaType.TEXT.value, MediaType.URL.value):
                await self.item_repo.update_status(user_id, backup_item_id, ItemStatus.COMPLETED)
                await self.task_repo.complete_task(task_id, self.worker_id)
                logger.info(f"[task_completed] Text/URL backup item completed (task_id={task_id})")
                return True

            msg = f"BackupItem {backup_item_id} has no telegram_file_id"
            logger.error(f"[task_failed] {msg} (task_id={task_id})")
            await self.task_repo.fail_task(task_id, msg, self.worker_id)
            await self.item_repo.update_status(user_id, backup_item_id, ItemStatus.FAILED)
            return False

        # 3. Start Heartbeat
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task_id))
        temp_download_file: Optional[Path] = None

        try:
            # 4. Select Download Provider
            expected_bytes = item.get("file_size")
            provider, transfer_method = self.select_download_provider(expected_bytes)

            # 5. Pre-flight Disk Space Headroom Check
            storage_dir = Path(self.settings.STORAGE_PATH)
            storage_dir.mkdir(parents=True, exist_ok=True)
            total_b, used_b, free_b = await asyncio.to_thread(shutil.disk_usage, storage_dir)
            usage_pct = (used_b / total_b) * 100.0 if total_b > 0 else 0.0

            file_size_val = expected_bytes or (10 * 1024 * 1024)
            required_space = file_size_val + self.settings.LARGE_FILE_DISK_SAFETY_MARGIN

            if usage_pct >= self.settings.DISK_CRITICAL_THRESHOLD_PCT or free_b < required_space:
                raise OSError(
                    f"Insufficient storage capacity: required {format_bytes(required_space)}, available {format_bytes(free_b)} ({usage_pct:.1f}% used)."
                )

            # 6. Progress Tracking callback (throttled)
            async def on_progress(downloaded: int, total: int) -> None:
                if total > 0:
                    pct = round((downloaded / total) * 100.0, 1)
                    await self.task_repo.update_progress(task_id, pct, self.worker_id)

            # 7. Construct SourceRef and Stream Download
            source_ref = TelegramSourceRef(
                user_id=user_id,
                chat_id=item.get("chat_id") or user_id,
                message_id=int(item.get("telegram_message_id", 0)),
                file_id=telegram_file_id,
                file_unique_id=item.get("telegram_file_unique_id"),
                media_type=item.get("media_type", "document"),
                expected_size=expected_bytes,
                task_id=task_id,
            )

            chunk_size = (
                self.settings.MT_PROTO_CHUNK_SIZE
                if transfer_method == "mtproto"
                else self.settings.WORKER_DOWNLOAD_CHUNK_SIZE
            )

            logger.info(
                f"[telegram_download_started] task_id={task_id} method={transfer_method} file_id={telegram_file_id}"
            )
            temp_dir = Path(self.settings.STORAGE_PATH) / ".tmp-downloads"

            download_res: DownloadResult = await provider.download_to_temp_file(
                source=source_ref,
                temp_dir=temp_dir,
                chunk_size=chunk_size,
                on_progress=on_progress,
                progress_interval_seconds=2.0,
                resume=self.settings.LARGE_FILE_RESUME_ENABLED,
            )
            temp_download_file = download_res.temp_path
            logger.info(
                f"[telegram_download_completed] task_id={task_id} size={download_res.file_size} sha256={download_res.sha256[:8]}..."
            )

            # 8. Atomically commit to permanent StorageService
            logger.info(f"[storage_upload_started] task_id={task_id}")
            ext = self._extract_extension(item.get("original_filename"), item.get("mime_type"))
            target_storage_key = self.storage.generate_storage_key(user_id=user_id, extension=ext)

            # Use store_from_file with atomic move to prevent duplicate disk storage
            storage_key = await self.storage.store_from_file(
                source_path=temp_download_file,
                storage_key=target_storage_key,
                move=True,
            )
            logger.info(f"[storage_upload_completed] task_id={task_id} key={storage_key}")

            # 9. Update BackupItem with verified storage metadata
            await self.item_repo.update_storage_info(
                user_id=user_id,
                item_id=backup_item_id,
                storage_key=storage_key,
                sha256=download_res.sha256,
                file_size=download_res.file_size,
                mime_type=item.get("mime_type"),
                original_filename=item.get("original_filename"),
                transfer_method=transfer_method,
                status=ItemStatus.COMPLETED,
            )

            # 10. Atomically increment StorageUsage (exactly once)
            await self.usage_repo.increment_usage(
                user_id=user_id,
                file_count=1,
                total_bytes=download_res.file_size,
            )

            # 11. Mark BackupTask completed
            await self.task_repo.complete_task(task_id, self.worker_id)
            logger.info(f"[task_completed] task_id={task_id} item_id={backup_item_id} user_id={user_id}")
            return True

        except Exception as exc:
            retryable = is_retryable_error(exc)
            max_attempts = self.settings.WORKER_MAX_ATTEMPTS
            safe_error_msg = f"{type(exc).__name__}: {str(exc)}"

            if isinstance(exc, TelegramFloodWaitError):
                logger.warning(f"[task_flood_wait] task_id={task_id} wait={exc.wait_seconds}s")
                safe_error_msg = f"Telegram rate limit: FLOOD_WAIT for {exc.wait_seconds}s"

            if retryable and attempts < max_attempts:
                logger.warning(
                    f"[task_retry] task_id={task_id} attempt={attempts}/{max_attempts} error={safe_error_msg}"
                )
                await self.task_repo.release_task_for_retry(
                    task_id=task_id,
                    error_message=f"Attempt {attempts} failed: {safe_error_msg}",
                    worker_id=self.worker_id,
                )
            else:
                logger.error(
                    f"[task_failed] task_id={task_id} permanent_or_exhausted attempt={attempts}/{max_attempts} error={safe_error_msg}"
                )
                await self.task_repo.fail_task(
                    task_id=task_id,
                    error_message=f"Task failed after {attempts} attempts: {safe_error_msg}",
                    worker_id=self.worker_id,
                )
                await self.item_repo.update_status(
                    user_id=user_id,
                    item_id=backup_item_id,
                    status=ItemStatus.FAILED,
                )
                # Cleanup .part on permanent failure
                if temp_download_file and temp_download_file.exists():
                    try:
                        await asyncio.to_thread(temp_download_file.unlink, missing_ok=True)
                    except Exception:
                        pass

            return False

        finally:
            # Cancel heartbeat lease renewal
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

