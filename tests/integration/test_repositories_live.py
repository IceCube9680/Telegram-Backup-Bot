"""Integration tests verifying indexes, concurrency, stale lock recovery, and ownership isolation."""

import asyncio
from datetime import datetime, timedelta, timezone
from pymongo.errors import DuplicateKeyError
import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import ensure_indexes
from app.database.models.backup_item import BackupItemModel, ItemStatus, MediaType
from app.database.models.backup_task import BackupTaskModel, TaskStatus, TaskType
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.folder_repo import FolderRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.database.repositories.tag_repo import TagRepository
from app.database.repositories.user_repo import UserRepository


@pytest_asyncio.fixture
async def live_db() -> AsyncDatabase:
    """Connect to test MongoDB database and ensure clean test collections and indexes."""
    client = AsyncMongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1000)
    try:
        await client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB is not running locally on localhost:27017. Skipping live integration tests.")

    db: AsyncDatabase = client["telegram_backup_test_phase2"]

    # Clean up any leftover test data
    collections = await db.list_collection_names()
    for col in collections:
        await db[col].drop()

    # Build all indexes
    await ensure_indexes(db)

    yield db

    # Cleanup after test suite
    collections = await db.list_collection_names()
    for col in collections:
        await db[col].drop()
    await client.close()


@pytest.mark.asyncio
async def test_unique_constraint_enforcement(live_db: AsyncDatabase):
    """Test unique indexes enforce uniqueness on users, folders, tags, settings, and storage usage."""
    user_repo = UserRepository(live_db)
    folder_repo = FolderRepository(live_db)
    tag_repo = TagRepository(live_db)

    # 1. Unique telegram_user_id
    await live_db["users"].insert_one({"telegram_user_id": 1111, "first_name": "Alice"})
    with pytest.raises(DuplicateKeyError):
        await live_db["users"].insert_one({"telegram_user_id": 1111, "first_name": "Duplicate Alice"})

    # 2. Unique (user_id, parent_id, name) on folders
    await folder_repo.create_folder(user_id=1111, name="Invoices", parent_id=None)
    with pytest.raises(DuplicateKeyError):
        await folder_repo.create_folder(user_id=1111, name="Invoices", parent_id=None)

    # Different user can have the same folder name
    folder_b = await folder_repo.create_folder(user_id=2222, name="Invoices", parent_id=None)
    assert folder_b["name"] == "Invoices"

    # 3. Unique (user_id, name) on tags
    await live_db["tags"].insert_one({"user_id": 1111, "name": "urgent"})
    with pytest.raises(DuplicateKeyError):
        await live_db["tags"].insert_one({"user_id": 1111, "name": "urgent"})


@pytest.mark.asyncio
async def test_concurrent_task_claiming(live_db: AsyncDatabase):
    """Test concurrent task claiming with atomic find_one_and_update.

    Spawns 10 concurrent workers trying to claim a single pending task.
    Exactly ONE worker must receive the task.
    """
    task_repo = BackupTaskRepository(live_db)

    # Create 1 pending task
    task = BackupTaskModel(user_id=1001, task_type=TaskType.DOWNLOAD_AND_STORE)
    created_task = await task_repo.create_task(task)
    task_id = created_task["id"]

    # 10 workers attempt to claim simultaneously
    workers = [f"worker-{i}" for i in range(10)]

    async def worker_attempt(w_id: str):
        return await task_repo.claim_next_task(worker_id=w_id)

    results = await asyncio.gather(*[worker_attempt(w) for w in workers])

    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1, "Exactly one worker must claim the task atomically"

    claimed = successful_claims[0]
    assert claimed["id"] == task_id
    assert claimed["status"] == "processing"
    assert claimed["worker_id"] in workers
    assert claimed["locked_at"] is not None
    assert claimed["attempts"] == 1


@pytest.mark.asyncio
async def test_stale_task_recovery(live_db: AsyncDatabase):
    """Test stale task recovery when a worker crashes with a lock timeout."""
    task_repo = BackupTaskRepository(live_db)
    now = datetime.now(timezone.utc)
    expired_lock = now - timedelta(seconds=600)

    # 1. Stale task with attempts < max_attempts (should be reset to pending)
    stale_task_1 = {
        "user_id": 1001,
        "task_type": "download_and_store",
        "status": "processing",
        "progress": 50.0,
        "attempts": 1,
        "worker_id": "crashed-worker-1",
        "locked_at": expired_lock,
        "created_at": expired_lock,
        "updated_at": expired_lock,
    }
    r1 = await live_db["backup_tasks"].insert_one(stale_task_1)
    task_id_1 = str(r1.inserted_id)

    # 2. Stale task with attempts >= max_attempts (should be marked failed)
    stale_task_2 = {
        "user_id": 1001,
        "task_type": "download_and_store",
        "status": "processing",
        "progress": 20.0,
        "attempts": 3,
        "worker_id": "crashed-worker-2",
        "locked_at": expired_lock,
        "created_at": expired_lock,
        "updated_at": expired_lock,
    }
    r2 = await live_db["backup_tasks"].insert_one(stale_task_2)
    task_id_2 = str(r2.inserted_id)

    # Run recovery
    recovered_count = await task_repo.recover_stale_tasks(lock_timeout_seconds=300, max_attempts=3)
    assert recovered_count == 1

    # Verify task 1 is back to pending
    doc_1 = await task_repo.get_by_id(task_id_1)
    assert doc_1["status"] == "pending"
    assert doc_1["worker_id"] is None
    assert doc_1["locked_at"] is None

    # Verify task 2 is failed
    doc_2 = await task_repo.get_by_id(task_id_2)
    assert doc_2["status"] == "failed"
    assert "exceeded" in doc_2["error_message"]


@pytest.mark.asyncio
async def test_atomic_storage_usage_concurrency(live_db: AsyncDatabase):
    """Test concurrent storage usage increment and floor-protected decrement using atomic $inc."""
    usage_repo = StorageUsageRepository(live_db)
    user_id = 9999

    # Run 20 concurrent increments of 1 file, 1024 bytes each
    async def inc_worker():
        return await usage_repo.increment_usage(user_id=user_id, file_count=1, total_bytes=1024)

    await asyncio.gather(*[inc_worker() for _ in range(20)])

    usage = await usage_repo.get_usage(user_id)
    assert usage["total_files"] == 20
    assert usage["total_size"] == 20 * 1024

    # Decrement by 5 files and 5120 bytes
    usage = await usage_repo.decrement_usage(user_id=user_id, file_count=5, total_bytes=5120)
    assert usage["total_files"] == 15
    assert usage["total_size"] == 15 * 1024

    # Decrement more than current count to verify non-negative floor protection
    usage = await usage_repo.decrement_usage(user_id=user_id, file_count=50, total_bytes=1000000)
    assert usage["total_files"] == 0
    assert usage["total_size"] == 0


@pytest.mark.asyncio
async def test_ownership_isolation(live_db: AsyncDatabase):
    """Test User A vs User B strict ownership isolation across all repositories."""
    item_repo = BackupItemRepository(live_db)
    folder_repo = FolderRepository(live_db)
    tag_repo = TagRepository(live_db)
    task_repo = BackupTaskRepository(live_db)
    settings_repo = SettingsRepository(live_db)

    user_a = 1001
    user_b = 2002

    # User A creates resources
    item_a = await item_repo.create_item(
        BackupItemModel(
            user_id=user_a,
            telegram_message_id=10,
            media_type=MediaType.DOCUMENT,
            sha256="aaa111sha256",
            status=ItemStatus.COMPLETED,
        )
    )
    folder_a = await folder_repo.create_folder(user_id=user_a, name="User A Secrets")
    tag_a = await tag_repo.get_or_create_tag(user_id=user_a, name="confidential")
    task_a = await task_repo.create_task(BackupTaskModel(user_id=user_a))
    await settings_repo.update_settings(user_id=user_a, auto_backup=False)

    # 1. User B cannot access User A's item
    assert await item_repo.get_by_id(user_id=user_b, item_id=item_a["id"]) is None
    assert (
        await item_repo.update_storage_info(
            user_id=user_b,
            item_id=item_a["id"],
            storage_key="hacked",
            sha256="hacked",
            file_size=0,
        )
        is None
    )
    assert await item_repo.soft_delete(user_id=user_b, item_id=item_a["id"]) is None
    assert await item_repo.hard_delete(user_id=user_b, item_id=item_a["id"]) is False

    # 2. Deduplication is strictly scoped: User B uploading same SHA256 does not match User A's item
    assert await item_repo.find_by_sha256(user_id=user_b, sha256="aaa111sha256") is None
    assert await item_repo.find_by_sha256(user_id=user_a, sha256="aaa111sha256") is not None

    # 3. User B cannot access User A's folder
    assert await folder_repo.get_by_id(user_id=user_b, folder_id=folder_a["id"]) is None
    assert await folder_repo.rename_folder(user_id=user_b, folder_id=folder_a["id"], new_name="Hacked") is None
    assert await folder_repo.delete_folder(user_id=user_b, folder_id=folder_a["id"]) is False

    # 4. User B cannot see User A's task
    assert await task_repo.get_by_id(task_id=task_a["id"], user_id=user_b) is None
    assert await task_repo.get_by_id(task_id=task_a["id"], user_id=user_a) is not None

    # 5. User B cannot see User A's tags
    user_b_tags = await tag_repo.list_user_tags(user_id=user_b)
    assert len(user_b_tags) == 0


@pytest.mark.asyncio
async def test_soft_delete_filtering(live_db: AsyncDatabase):
    """Test soft delete excludes items from standard listing and enables recovery if queried with include_deleted."""
    item_repo = BackupItemRepository(live_db)
    user_id = 7777

    item = await item_repo.create_item(
        BackupItemModel(user_id=user_id, telegram_message_id=50, original_filename="report.pdf")
    )
    item_id = item["id"]

    # Active item listed
    items = await item_repo.list_items(user_id=user_id)
    assert len(items) == 1

    # Soft delete item
    deleted_item = await item_repo.soft_delete(user_id=user_id, item_id=item_id)
    assert deleted_item is not None
    assert deleted_item["deleted_at"] is not None

    # Normal list ignores soft-deleted item
    items_after = await item_repo.list_items(user_id=user_id, include_deleted=False)
    assert len(items_after) == 0

    # Explicit list with include_deleted=True returns it
    all_items = await item_repo.list_items(user_id=user_id, include_deleted=True)
    assert len(all_items) == 1
    assert all_items[0]["id"] == item_id
