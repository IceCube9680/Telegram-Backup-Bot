"""/stats command handler."""

from typing import Any, Dict
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.services.backup_service import format_bytes

router = Router(name="stats")


@router.message(Command("stats"))
@router.message(F.text == "📊 Stats")
async def cmd_stats(
    message: Message,
    item_repo: BackupItemRepository,
    storage_usage_repo: StorageUsageRepository,
    user: Dict[str, Any],
) -> None:
    """Show user storage and backup statistics."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    usage = await storage_usage_repo.get_usage(user_id)
    total_active_items = await item_repo.count_items(user_id)

    total_size_formatted = format_bytes(usage.get("total_size", 0))

    stats_text = (
        "📊 <b>Your Backup Statistics</b>\n\n"
        f"• <b>Total Active Files:</b> <code>{total_active_items}</code>\n"
        f"• <b>Total Storage Used:</b> <code>{total_size_formatted}</code>\n"
        f"• <b>Account Status:</b> <code>{'Active ✅' if user.get('is_active', True) else 'Disabled ❌'}</code>\n"
        f"• <b>User ID:</b> <code>{user_id}</code>\n\n"
        "🔒 <i>All files are stored securely in your private backup storage.</i>"
    )
    await message.answer(text=stats_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
