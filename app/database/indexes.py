"""MongoDB collection index definitions and initialization."""

from typing import List
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

from app.core.logging import get_logger

logger = get_logger(__name__)


async def _safe_create_indexes(db: AsyncDatabase, collection_name: str, indexes: List[IndexModel]) -> None:
    """Create indexes with automatic drop-and-recreate if index options have changed."""
    try:
        await db[collection_name].create_indexes(indexes)
    except OperationFailure as exc:
        if "already exists with" in str(exc) or exc.code in (85, 86):
            logger.info(f"Index conflict in '{collection_name}', updating index definitions...")
            for idx in indexes:
                idx_name = idx.document.get("name")
                if idx_name:
                    try:
                        await db[collection_name].drop_index(idx_name)
                    except Exception:
                        pass
            await db[collection_name].create_indexes(indexes)
        else:
            raise


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotently create all required compound and unique indexes on MongoDB collections."""
    logger.info("Initializing MongoDB indexes...")

    # 1. users collection indexes
    user_indexes = [
        IndexModel([("telegram_user_id", ASCENDING)], unique=True, name="idx_users_telegram_id_unique"),
    ]
    await _safe_create_indexes(db, "users", user_indexes)

    # 2. backup_items collection indexes (user-scoped)
    backup_item_indexes = [
        IndexModel(
            [("user_id", ASCENDING), ("telegram_message_id", ASCENDING)],
            unique=True,
            name="idx_items_user_message_unique",
        ),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_items_user_created"),
        IndexModel([("user_id", ASCENDING), ("sha256", ASCENDING)], name="idx_items_user_sha256"),
        IndexModel([("user_id", ASCENDING), ("original_filename", ASCENDING)], name="idx_items_user_filename"),
        IndexModel([("user_id", ASCENDING), ("media_type", ASCENDING)], name="idx_items_user_media_type"),
        IndexModel([("user_id", ASCENDING), ("folder_id", ASCENDING)], name="idx_items_user_folder"),
        IndexModel([("user_id", ASCENDING), ("deleted_at", ASCENDING)], name="idx_items_user_deleted"),
    ]
    await _safe_create_indexes(db, "backup_items", backup_item_indexes)

    # 3. backup_tasks collection indexes
    backup_task_indexes = [
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_tasks_status_created"),
        IndexModel([("status", ASCENDING), ("locked_at", ASCENDING)], name="idx_tasks_status_locked"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_tasks_user_created"),
    ]
    await _safe_create_indexes(db, "backup_tasks", backup_task_indexes)

    # 4. folders collection indexes
    folder_indexes = [
        IndexModel([("user_id", ASCENDING), ("parent_id", ASCENDING)], name="idx_folders_user_parent"),
        IndexModel(
            [("user_id", ASCENDING), ("parent_id", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="idx_folders_user_parent_name_unique",
        ),
    ]
    await _safe_create_indexes(db, "folders", folder_indexes)

    # 5. tags collection indexes
    tag_indexes = [
        IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], unique=True, name="idx_tags_user_name_unique"),
    ]
    await _safe_create_indexes(db, "tags", tag_indexes)

    # 6. item_tags collection indexes
    item_tag_indexes = [
        IndexModel(
            [("backup_item_id", ASCENDING), ("tag_id", ASCENDING)],
            unique=True,
            name="idx_item_tags_unique",
        ),
        IndexModel([("tag_id", ASCENDING), ("backup_item_id", ASCENDING)], name="idx_item_tags_tag_item"),
    ]
    await _safe_create_indexes(db, "item_tags", item_tag_indexes)

    # 7. user_settings collection indexes
    user_settings_indexes = [
        IndexModel([("user_id", ASCENDING)], unique=True, name="idx_settings_user_unique"),
    ]
    await _safe_create_indexes(db, "user_settings", user_settings_indexes)

    # 8. storage_usage collection indexes
    storage_usage_indexes = [
        IndexModel([("user_id", ASCENDING)], unique=True, name="idx_storage_user_unique"),
    ]
    await _safe_create_indexes(db, "storage_usage", storage_usage_indexes)

    # 9. web_sessions collection indexes (with TTL auto-cleanup)
    web_session_indexes = [
        IndexModel([("token_hash", ASCENDING)], unique=True, name="idx_sessions_token_hash_unique"),
        IndexModel([("user_id", ASCENDING)], name="idx_sessions_user_id"),
        IndexModel([("expires_at", ASCENDING)], name="idx_sessions_expires_at", expireAfterSeconds=0),
    ]
    await _safe_create_indexes(db, "web_sessions", web_session_indexes)

    # 10. login_tokens collection indexes (with TTL auto-cleanup)
    login_token_indexes = [
        IndexModel([("token_hash", ASCENDING)], unique=True, name="idx_login_tokens_token_hash_unique"),
        IndexModel([("telegram_user_id", ASCENDING)], name="idx_login_tokens_telegram_user"),
        IndexModel([("expires_at", ASCENDING)], name="idx_login_tokens_expires_at", expireAfterSeconds=0),
    ]
    await _safe_create_indexes(db, "login_tokens", login_token_indexes)

    logger.info("MongoDB indexes successfully verified/created.")
