"""Unit tests for Telegram bot command and media handlers."""

from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Document, Message, User
import pytest

from app.bot.handlers.backup import cmd_backup, handle_direct_media
from app.bot.handlers.files import cmd_files
from app.bot.handlers.help import cmd_help
from app.bot.handlers.search import cmd_search
from app.bot.handlers.settings import cmd_settings
from app.bot.handlers.start import cmd_start
from app.bot.handlers.stats import cmd_stats
from app.bot.middlewares.user_middleware import UserMiddleware
from app.core.exceptions import ValidationError
from app.services.backup_service import BackupResult


def make_mock_message(
    user_id: int = 12345,
    first_name: str = "Alice",
    text: str = "",
    doc: Document = None,
) -> Message:
    """Create a mock aiogram Message instance."""
    user = User(id=user_id, is_bot=False, first_name=first_name, username="alice")
    msg = MagicMock(spec=Message)
    msg.message_id = 999
    msg.from_user = user
    msg.text = text
    msg.document = doc
    msg.photo = None
    msg.video = None
    msg.audio = None
    msg.voice = None
    msg.animation = None
    msg.video_note = None
    msg.caption = None
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_cmd_start_handler():
    """Test /start sends welcome message and main keyboard."""
    msg = make_mock_message(first_name="Bob")
    await cmd_start(msg)

    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Bob" in kwargs["text"]
    assert "Telegram Backup Bot" in kwargs["text"]
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_cmd_help_handler():
    """Test /help sends guidance manual."""
    msg = make_mock_message()
    await cmd_help(msg)

    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Help & Usage Guide" in kwargs["text"]
    assert "Documents" in kwargs["text"]


@pytest.mark.asyncio
async def test_cmd_backup_handler():
    """Test /backup sends backup instructions."""
    msg = make_mock_message()
    await cmd_backup(msg)

    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "How to Back Up Your Files" in kwargs["text"]


@pytest.mark.asyncio
async def test_handle_direct_media_success():
    """Test incoming media creates task and replies with Backup Queued message."""
    doc = Document(file_id="f1", file_unique_id="u1", file_name="invoice.pdf", file_size=1024)
    msg = make_mock_message(doc=doc)

    mock_backup_service = AsyncMock()
    mock_backup_service.enqueue_backup.return_value = BackupResult(
        task_id="task_hex_123456",
        item_id="item_hex_123456",
        original_filename="invoice.pdf",
        file_size_formatted="1.0 KB",
        media_type="document",
        is_duplicate=False,
    )

    await handle_direct_media(
        message=msg,
        backup_service=mock_backup_service,
        user={"is_active": True},
    )

    msg.reply.assert_awaited_once()
    args, kwargs = msg.reply.call_args
    assert "Backup Queued" in kwargs["text"]
    assert "invoice.pdf" in kwargs["text"]
    assert "#123456" in kwargs["text"]


@pytest.mark.asyncio
async def test_handle_direct_media_duplicate():
    """Test incoming duplicate media replies with Already Queued message."""
    doc = Document(file_id="f1", file_unique_id="u1", file_name="invoice.pdf", file_size=1024)
    msg = make_mock_message(doc=doc)

    mock_backup_service = AsyncMock()
    mock_backup_service.enqueue_backup.return_value = BackupResult(
        task_id="task_hex_999999",
        item_id="item_hex_999999",
        original_filename="invoice.pdf",
        file_size_formatted="1.0 KB",
        media_type="document",
        is_duplicate=True,
    )

    await handle_direct_media(
        message=msg,
        backup_service=mock_backup_service,
        user={"is_active": True},
    )

    msg.reply.assert_awaited_once()
    args, kwargs = msg.reply.call_args
    assert "Already Queued" in kwargs["text"]


@pytest.mark.asyncio
async def test_handle_direct_media_validation_error():
    """Test validation error in backup service sends friendly error message."""
    doc = Document(file_id="f1", file_unique_id="u1", file_name="huge.zip", file_size=100000000)
    msg = make_mock_message(doc=doc)

    mock_backup_service = AsyncMock()
    mock_backup_service.enqueue_backup.side_effect = ValidationError("File size exceeds 50 MB limit.")

    await handle_direct_media(
        message=msg,
        backup_service=mock_backup_service,
        user={"is_active": True},
    )

    msg.reply.assert_awaited_once()
    args, kwargs = msg.reply.call_args
    assert "Backup Rejected" in kwargs["text"]
    assert "File size exceeds 50 MB limit." in kwargs["text"]


@pytest.mark.asyncio
async def test_cmd_files_empty_and_populated():
    """Test /files command with empty list and with backed-up items."""
    msg = make_mock_message(user_id=12345)
    mock_item_repo = AsyncMock()

    # 1. Empty list
    mock_item_repo.list_items.return_value = []
    await cmd_files(message=msg, item_repo=mock_item_repo, user={"is_active": True})
    args, kwargs = msg.answer.call_args
    assert "Your Backup Vault is Empty" in kwargs["text"]

    # 2. Populated list
    mock_item_repo.list_items.return_value = [
        {"original_filename": "tax2025.pdf", "file_size": 2048, "media_type": "document", "status": "completed"}
    ]
    await cmd_files(message=msg, item_repo=mock_item_repo, user={"is_active": True})
    args, kwargs = msg.answer.call_args
    assert "tax2025.pdf" in kwargs["text"]
    assert "Document" in kwargs["text"]


@pytest.mark.asyncio
async def test_cmd_stats_handler():
    """Test /stats command."""
    msg = make_mock_message(user_id=12345)
    mock_item_repo = AsyncMock()
    mock_usage_repo = AsyncMock()

    mock_usage_repo.get_usage.return_value = {"total_files": 12, "total_size": 10485760}
    mock_item_repo.count_items.return_value = 12

    await cmd_stats(message=msg, item_repo=mock_item_repo, storage_usage_repo=mock_usage_repo, user={"is_active": True})
    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Your Backup Statistics" in kwargs["text"]
    assert "12" in kwargs["text"]
    assert "10.0 MB" in kwargs["text"]


@pytest.mark.asyncio
async def test_cmd_settings_handler():
    """Test /settings command."""
    msg = make_mock_message(user_id=12345)
    mock_settings_repo = AsyncMock()
    mock_settings_repo.get_or_create_settings.return_value = {
        "auto_backup": True,
        "duplicate_detection": True,
        "max_file_size": 52428800,
        "notifications_enabled": True,
    }

    await cmd_settings(message=msg, settings_repo=mock_settings_repo, user={"is_active": True})
    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Your Backup Settings" in kwargs["text"]
    assert "50.0 MB" in kwargs["text"]


@pytest.mark.asyncio
async def test_cmd_search_handler():
    """Test /search command."""
    msg = make_mock_message()
    await cmd_search(msg)
    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Search Your Backups" in kwargs["text"]


@pytest.mark.asyncio
async def test_user_middleware_registers_and_injects():
    """Test UserMiddleware automatically upserts user and populates context data."""
    mock_db = AsyncMock()
    middleware = UserMiddleware(mock_db)

    with patch.object(middleware.user_repo, "upsert_user", new_callable=AsyncMock) as mock_upsert:
        mock_upsert.return_value = {"telegram_user_id": 5555, "first_name": "Charlie"}

        user = User(id=5555, is_bot=False, first_name="Charlie")
        data = {"event_from_user": user}

        next_handler = AsyncMock(return_value="OK")
        res = await middleware(next_handler, MagicMock(), data)

        assert res == "OK"
        mock_upsert.assert_awaited_once_with(
            telegram_user_id=5555,
            first_name="Charlie",
            last_name=None,
            username=None,
        )
        assert data["user"] == {"telegram_user_id": 5555, "first_name": "Charlie"}
        assert "backup_service" in data
        assert "item_repo" in data
        assert "task_repo" in data
