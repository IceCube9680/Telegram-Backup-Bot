"""MongoDB collection index definitions and initialization."""

from typing import List
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import get_logger

logger = get_logger(__name__)


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotently create all required compound and unique indexes on MongoDB collections."""
    logger.info("Initializing MongoDB indexes...")

    # 1. users collection indexes
    user_indexes = [
        IndexModel([("telegram_user_id", ASCENDING)], unique=True, name="idx_users_telegram_id_unique"),
    ]
    await db["users"].create_indexes(user_indexes)

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
    await db["backup_items"].create_indexes(backup_item_indexes)

    # 3. backup_tasks collection indexes
    backup_task_indexes = [
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_tasks_status_created"),
        IndexModel([("status", ASCENDING), ("locked_at", ASCENDING)], name="idx_tasks_status_locked"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_tasks_user_created"),
    ]
    await db["backup_tasks"].create_indexes(backup_task_indexes)

    # 4. folders collection indexes
    folder_indexes = [
        IndexModel([("user_id", ASCENDING), ("parent_id", ASCENDING)], name="idx_folders_user_parent"),
        IndexModel(
            [("user_id", ASCENDING), ("parent_id", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="idx_folders_user_parent_name_unique",
        ),
    ]
    await db["folders"].create_indexes(folder_indexes)

    # 5. tags collection indexes
    tag_indexes = [
        IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], unique=True, name="idx_tags_user_name_unique"),
    ]
    await db["tags"].create_indexes(tag_indexes)

    # 6. item_tags collection indexes
    item_tag_indexes = [
        IndexModel(
            [("backup_item_id", ASCENDING), ("tag_id", ASCENDING)],
            unique=True,
            name="idx_item_tags_unique",
        ),
        IndexModel([("tag_id", ASCENDING), ("backup_item_id", ASCENDING)], name="idx_item_tags_tag_item"),
    ]
    await db["item_tags"].create_indexes(item_tag_indexes)

    # 7. user_settings collection indexes
    user_settings_indexes = [
        IndexModel([("user_id", ASCENDING)], unique=True, name="idx_settings_user_unique"),
    ]
    await db["user_settings"].create_indexes(user_settings_indexes)

    # 8. storage_usage collection indexes
    storage_usage_indexes = [
        IndexModel([("user_id", ASCENDING)], unique=True, name="idx_storage_user_unique"),
    ]
    await db["storage_usage"].create_indexes(storage_usage_indexes)

    logger.info("MongoDB indexes successfully verified/created.")
