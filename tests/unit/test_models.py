"""Unit tests for Phase 2 Pydantic models and schemas."""

from datetime import datetime
import pytest

from app.database.models.backup_item import BackupItemModel, ItemStatus, MediaType
from app.database.models.backup_task import BackupTaskModel, TaskStatus, TaskType
from app.database.models.folder import FolderModel
from app.database.models.settings import StorageUsageModel, UserSettingsModel
from app.database.models.tag import ItemTagModel, TagModel
from app.database.models.user import UserModel


def test_user_model_defaults_and_doc():
    """Test UserModel field defaults and serialization."""
    user = UserModel(telegram_user_id=123456, first_name="John", last_name="Doe", username="johndoe")
    assert user.telegram_user_id == 123456
    assert user.is_active is True
    assert user.is_admin is False
    assert isinstance(user.created_at, datetime)

    doc = user.to_doc()
    assert doc["telegram_user_id"] == 123456
    assert doc["first_name"] == "John"
    assert doc["is_active"] is True


def test_backup_item_model_defaults_and_doc():
    """Test BackupItemModel validation, media types, and soft delete field."""
    item = BackupItemModel(
        user_id=123456,
        telegram_message_id=999,
        media_type=MediaType.VIDEO,
        original_filename="clip.mp4",
        file_size=10240,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert item.user_id == 123456
    assert item.media_type == MediaType.VIDEO
    assert item.status == ItemStatus.PENDING
    assert item.deleted_at is None

    doc = item.to_doc()
    assert doc["media_type"] == "video"
    assert doc["status"] == "pending"
    assert doc["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_backup_task_model_defaults():
    """Test BackupTaskModel validation and status enums."""
    task = BackupTaskModel(user_id=123456, task_type=TaskType.DOWNLOAD_AND_STORE)
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0.0
    assert task.attempts == 0
    assert task.locked_at is None

    doc = task.to_doc()
    assert doc["status"] == "pending"
    assert doc["task_type"] == "download_and_store"


def test_folder_model():
    """Test FolderModel creation and serialization."""
    folder = FolderModel(user_id=123456, name="Documents")
    assert folder.name == "Documents"
    assert folder.parent_id is None
    doc = folder.to_doc()
    assert doc["name"] == "Documents"


def test_tag_models():
    """Test TagModel and ItemTagModel."""
    tag = TagModel(user_id=123456, name="work")
    assert tag.name == "work"
    assert tag.user_id == 123456

    item_tag = ItemTagModel(backup_item_id="65f1a2b3c4d5e6f7a8b9c0d1", tag_id="65f1a2b3c4d5e6f7a8b9c0d2")
    assert item_tag.backup_item_id == "65f1a2b3c4d5e6f7a8b9c0d1"


def test_settings_and_storage_usage_models():
    """Test UserSettingsModel and StorageUsageModel."""
    settings = UserSettingsModel(user_id=123456)
    assert settings.auto_backup is True
    assert settings.duplicate_detection is True
    assert settings.max_file_size == 52428800

    usage = StorageUsageModel(user_id=123456, total_files=5, total_size=1048576)
    assert usage.total_files == 5
    assert usage.total_size == 1048576
