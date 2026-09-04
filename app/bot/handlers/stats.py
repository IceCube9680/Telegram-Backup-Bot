"""/stats command handler."""

from typing import Any, Dict, Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard
from app.services.backup_management_service import BackupManagementService
from app.services.backup_service import format_bytes

router = Router(name="stats")


@router.message(Command("stats"))
@router.message(F.text == "📊 Stats")
async def cmd_stats(
    message: Message,
    management_service: Optional[BackupManagementService] = None,
    item_repo: Optional[Any] = None,
    storage_usage_repo: Optional[Any] = None,
    user: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> None:
    """Show user storage and backup statistics with breakdown by status."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    user_dict = user or {}

    if management_service:
        stats = await management_service.get_user_stats(user_id)
        total_files = stats.total_files
        total_size_bytes = stats.total_size_bytes
        completed_count = stats.completed_count
        processing_count = stats.processing_count
        pending_count = stats.pending_count
        failed_count = stats.failed_count
    else:
        usage = await storage_usage_repo.get_usage(user_id) if storage_usage_repo else {}
        total_files = await item_repo.count_items(user_id) if item_repo else usage.get("total_files", 0)
        total_size_bytes = usage.get("total_size", 0)
        completed_count = total_files
        processing_count = 0
        pending_count = 0
        failed_count = 0

    total_size_formatted = format_bytes(total_size_bytes)

    stats_text = (
        "📊 <b>Your Backup Statistics</b>\n\n"
        f"• <b>Total Active Files:</b> <code>{total_files}</code>\n"
        f"• <b>Total Storage Used:</b> <code>{total_size_formatted}</code>\n\n"
        "<b>Status Breakdown:</b>\n"
        f"  ✅ <b>Completed:</b> <code>{completed_count}</code>\n"
        f"  ⏳ <b>Processing:</b> <code>{processing_count}</code>\n"
        f"  🕒 <b>Pending Queue:</b> <code>{pending_count}</code>\n"
        f"  ❌ <b>Failed:</b> <code>{failed_count}</code>\n\n"
        f"• <b>Account Status:</b> <code>{'Active ✅' if user_dict.get('is_active', True) else 'Disabled ❌'}</code>\n"
        f"• <b>User ID:</b> <code>{user_id}</code>\n\n"
        "🔒 <i>All files are isolated and securely encrypted in your private vault.</i>"
    )
    await message.answer(text=stats_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
