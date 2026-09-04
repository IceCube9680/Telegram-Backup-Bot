"""Unit tests for BackupService orchestration and quota validations."""

from unittest.mock import AsyncMock, patch
import pytest

from app.core.exceptions import ValidationError
from app.database.models.backup_item import MediaType
from app.services.backup_service import BackupResult, BackupService, format_bytes
from app.services.telegram_media_service import TelegramMediaInfo


@pytest.fixture
def mock_db():
    """Return mocked AsyncDatabase."""
    return AsyncMock()


def make_media_info(
    user_id: int = 1001,
    msg_id: int = 500,
    file_size: int = 1048576,  # 1 MB
    filename: str = "notes.pdf",
) -> TelegramMediaInfo:
    """Helper to instantiate TelegramMediaInfo."""
    return TelegramMediaInfo(
        user_id=user_id,
        telegram_message_id=msg_id,
        file_id="tg_file_999",
        file_unique_id="tg_uniq_999",
        media_type=MediaType.DOCUMENT,
        original_filename=filename,
        mime_type="application/pdf",
        file_size=file_size,
    )


@pytest.mark.asyncio
async def test_enqueue_backup_successful(mock_db):
    """Test standard successful backup enqueueing creating item and task."""
    service = BackupService(mock_db)
    media = make_media_info(user_id=1001, msg_id=501, file_size=2048)

    with patch.object(service.settings_repo, "get_or_create_settings", new_callable=AsyncMock) as mock_settings, \
         patch.object(service.item_repo, "get_by_message_id", new_callable=AsyncMock) as mock_get_msg, \
         patch.object(service.item_repo, "create_item", new_callable=AsyncMock) as mock_create_item, \
         patch.object(service.task_repo, "create_task", new_callable=AsyncMock) as mock_create_task:

        mock_settings.return_value = {"max_file_size": 52428800, "default_folder_id": None}
        mock_get_msg.return_value = None
        mock_create_item.return_value = {"id": "item_id_111"}
        mock_create_task.return_value = {"id": "task_id_222"}

        result = await service.enqueue_backup(media_info=media, user_data={"is_active": True})

        assert isinstance(result, BackupResult)
        assert result.task_id == "task_id_222"
        assert result.item_id == "item_id_111"
        assert result.is_duplicate is False
        assert result.original_filename == "notes.pdf"
        assert result.file_size_formatted == "2.0 KB"

        mock_create_item.assert_awaited_once()
        mock_create_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_backup_inactive_user_rejected(mock_db):
    """Test inactive account is rejected with ValidationError."""
    service = BackupService(mock_db)
    media = make_media_info()

    with pytest.raises(ValidationError) as exc:
        await service.enqueue_backup(media_info=media, user_data={"is_active": False})

    assert "disabled" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_enqueue_backup_oversized_file_rejected(mock_db):
    """Test file exceeding user max_file_size limit is rejected with ValidationError."""
    service = BackupService(mock_db)
    # File is 60 MB
    media = make_media_info(file_size=60 * 1024 * 1024)

    with patch.object(service.settings_repo, "get_or_create_settings", new_callable=AsyncMock) as mock_settings:
        # User limit is 50 MB
        mock_settings.return_value = {"max_file_size": 50 * 1024 * 1024}

        with pytest.raises(ValidationError) as exc:
            await service.enqueue_backup(media_info=media, user_data={"is_active": True})

        assert "exceeds your allowed limit" in exc.value.message


@pytest.mark.asyncio
async def test_enqueue_backup_idempotency_duplicate(mock_db):
    """Test duplicate message ID does not recreate item/task and returns duplicate result."""
    service = BackupService(mock_db)
    media = make_media_info(msg_id=777)

    with patch.object(service.settings_repo, "get_or_create_settings", new_callable=AsyncMock) as mock_settings, \
         patch.object(service.item_repo, "get_by_message_id", new_callable=AsyncMock) as mock_get_msg, \
         patch.object(service.item_repo, "create_item", new_callable=AsyncMock) as mock_create_item, \
         patch.object(service.task_repo.collection, "find_one", new_callable=AsyncMock) as mock_find_task:

        mock_settings.return_value = {"max_file_size": 52428800}
        mock_get_msg.return_value = {
            "id": "existing_item_id",
            "original_filename": "notes.pdf",
            "file_size": 1048576,
            "media_type": "document",
        }
        mock_find_task.return_value = {"_id": "existing_task_id"}

        result = await service.enqueue_backup(media_info=media, user_data={"is_active": True})

        assert result.is_duplicate is True
        assert result.item_id == "existing_item_id"
        assert result.task_id == "existing_task_id"
        mock_create_item.assert_not_called()


def test_format_bytes_utility():
    """Test format_bytes utility formatting."""
    assert format_bytes(None) == "Unknown size"
    assert format_bytes(0) == "Unknown size"
    assert format_bytes(500) == "500 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_bytes(1073741824) == "1.0 GB"
