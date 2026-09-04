"""Background worker daemon for polling, claiming, and executing backup tasks concurrently."""

import asyncio
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any, Dict, Optional, Set
import uuid
from aiogram import Bot
from pymongo.asynchronous.database import AsyncDatabase

from app.bot.bot import create_bot
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.database.indexes import ensure_indexes
from app.database.mongo import mongo_manager
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.services.mtproto_client import TelethonClientManager
from app.services.storage_service import LocalStorageService, StorageService, get_storage_service
from app.workers.tasks import TaskProcessor
from app.workers.telegram_downloader import TelegramDownloader

logger = get_logger(__name__)


class BackupWorker:
    """Production asynchronous background worker for processing backup queues."""

    def __init__(
        self,
        db: Optional[AsyncDatabase] = None,
        bot: Optional[Bot] = None,
        storage_service: Optional[StorageService] = None,
        worker_id: Optional[str] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.worker_id = worker_id or self.settings.WORKER_ID or f"worker-{uuid.uuid4().hex[:8]}"
        self.db = db
        self.bot = bot
        self.storage = storage_service or get_storage_service()
        self.task_processor: Optional[TaskProcessor] = None
        self.task_repo: Optional[BackupTaskRepository] = None
        self.mtproto_client_manager: Optional[TelethonClientManager] = None

        self._running: bool = False
        self._stop_event = asyncio.Event()
        self._active_tasks: Set[asyncio.Task[Any]] = set()
        self._owns_lifecycle: bool = False

    async def initialize(self) -> None:
        """Initialize MongoDB, Bot, MTProto client, repositories, and task processor."""
        if self.db is None:
            self.db = await mongo_manager.connect()
            await ensure_indexes(self.db)
            self._owns_lifecycle = True

        if self.bot is None:
            self.bot = create_bot()

        # Initialize MTProto client if enabled
        if self.settings.MT_PROTO_ENABLED:
            self.mtproto_client_manager = TelethonClientManager(self.settings)
            try:
                await self.mtproto_client_manager.initialize()
            except Exception as me:
                logger.error(f"Worker failed to initialize MTProto client: {me}")
                raise

        self.task_repo = BackupTaskRepository(self.db)
        downloader = TelegramDownloader(self.bot)
        self.task_processor = TaskProcessor(
            db=self.db,
            bot=self.bot,
            worker_id=self.worker_id,
            storage_service=self.storage,
            downloader=downloader,
            mtproto_client_manager=self.mtproto_client_manager,
            settings=self.settings,
        )

        # Ensure temporary download directory exists and clean stale temp files
        temp_dir = Path(self.settings.STORAGE_PATH) / ".tmp-downloads"
        await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
        await self.cleanup_stale_temp_files(max_age_seconds=3600)

    async def cleanup_stale_temp_files(self, max_age_seconds: int = 3600) -> int:
        """Clean temporary download files older than max_age_seconds from previous crashed tasks."""
        temp_dir = Path(self.settings.STORAGE_PATH) / ".tmp-downloads"
        if not temp_dir.exists():
            return 0

        now = time.time()
        cleaned_count = 0

        def _scan_and_clean() -> int:
            cleaned = 0
            for item in temp_dir.iterdir():
                if item.is_file():
                    try:
                        mtime = item.stat().st_mtime
                        if now - mtime > max_age_seconds:
                            item.unlink(missing_ok=True)
                            cleaned += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove stale temp file {item}: {e}")
            return cleaned

        try:
            cleaned_count = await asyncio.to_thread(_scan_and_clean)
            if cleaned_count > 0:
                logger.info(f"[stale_temp_cleaned] worker={self.worker_id} cleaned_files={cleaned_count}")
        except Exception as err:
            logger.warning(f"Error during temp directory cleanup: {err}")

        return cleaned_count

    async def recover_stale_tasks(self) -> int:
        """Recover tasks from crashed workers whose lock leases expired."""
        if self.task_repo is None:
            return 0
        try:
            count = await self.task_repo.recover_stale_tasks(
                lock_timeout_seconds=self.settings.WORKER_LOCK_TIMEOUT,
                max_attempts=self.settings.WORKER_MAX_ATTEMPTS,
            )
            if count > 0:
                logger.info(f"[stale_tasks_recovered] worker={self.worker_id} recovered_count={count}")
            return count
        except Exception as e:
            logger.error(f"Error during stale task recovery: {e}")
            return 0

    async def _process_task_wrapper(self, task_doc: Dict[str, Any]) -> None:
        """Wrapper to execute task and clean up task references."""
        try:
            if self.task_processor:
                await self.task_processor.process_task(task_doc)
        except Exception as e:
            logger.error(f"Unhandled exception processing task {task_doc.get('id')}: {e}")

    async def start(self) -> None:
        """Start the worker polling loop and process queued tasks."""
        await self.initialize()
        self._running = True
        self._stop_event.clear()

        logger.info(
            f"[worker_started] worker_id={self.worker_id} concurrency={self.settings.WORKER_CONCURRENCY} poll_interval={self.settings.WORKER_POLL_INTERVAL}s"
        )

        # Initial stale tasks recovery
        await self.recover_stale_tasks()
        last_stale_check = time.monotonic()
        stale_check_interval = 60.0  # Run stale check every minute

        while self._running:
            try:
                # Periodic stale task recovery
                now = time.monotonic()
                if now - last_stale_check >= stale_check_interval:
                    last_stale_check = now
                    await self.recover_stale_tasks()

                # Check if we have capacity for more concurrent jobs
                concurrency = max(1, self.settings.WORKER_CONCURRENCY)
                if len(self._active_tasks) < concurrency:
                    assert self.task_repo is not None
                    task_doc = await self.task_repo.claim_next_task(self.worker_id)

                    if task_doc:
                        task_id = str(task_doc.get("id"))
                        logger.info(f"[task_claimed] worker={self.worker_id} task_id={task_id}")

                        t = asyncio.create_task(self._process_task_wrapper(task_doc))
                        self._active_tasks.add(t)
                        t.add_done_callback(self._active_tasks.discard)

                        # Check immediately if more tasks can be claimed within concurrency limit
                        continue

                # If no tasks claimed or at max concurrency, wait or sleep
                if self._active_tasks:
                    # Wait for either a running task to complete or the stop signal
                    done, _ = await asyncio.wait(
                        self._active_tasks,
                        timeout=self.settings.WORKER_POLL_INTERVAL,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                else:
                    # No active tasks and no tasks claimed -> sleep for poll interval
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self.settings.WORKER_POLL_INTERVAL,
                        )
                    except asyncio.TimeoutError:
                        pass

            except (asyncio.CancelledError, KeyboardInterrupt):
                logger.info(f"Worker {self.worker_id} received stop signal.")
                break
            except Exception as e:
                logger.error(f"Error in worker main loop: {e}")
                await asyncio.sleep(self.settings.WORKER_POLL_INTERVAL)

        await self.shutdown()

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Gracefully stop worker, await in-flight tasks, and close resources."""
        self._running = False
        self._stop_event.set()
        logger.info(f"Stopping worker {self.worker_id}... Waiting for {len(self._active_tasks)} active tasks.")

        if self._active_tasks:
            # Wait for active tasks to complete up to timeout
            done, pending = await asyncio.wait(self._active_tasks, timeout=timeout)
            if pending:
                logger.warning(f"Cancelling {len(pending)} remaining tasks after shutdown timeout...")
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        if self.mtproto_client_manager:
            try:
                await self.mtproto_client_manager.close()
            except Exception as mce:
                logger.warning(f"Error disconnecting MTProto client on shutdown: {mce}")

        if self._owns_lifecycle:
            if self.bot and self.bot.session:
                try:
                    await self.bot.session.close()
                except Exception as be:
                    logger.warning(f"Error closing bot session: {be}")

            try:
                await mongo_manager.disconnect()
            except Exception as me:
                logger.warning(f"Error disconnecting MongoDB: {me}")

        logger.info(f"[worker_stopped] worker_id={self.worker_id}")


async def run_worker() -> None:
    """Application entrypoint for running background worker process."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    worker = BackupWorker(settings=settings)

    loop = asyncio.get_running_loop()

    def _handle_signal():
        logger.info("Received termination signal. Triggering graceful shutdown...")
        worker._running = False
        worker._stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows or specific environments
            pass

    try:
        await worker.start()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    asyncio.run(run_worker())
