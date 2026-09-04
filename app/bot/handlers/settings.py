"""/settings command handler."""

from typing import Any, Dict
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard
from app.database.repositories.settings_repo import SettingsRepository
from app.services.backup_service import format_bytes

router = Router(name="settings")


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Settings")
async def cmd_settings(
    message: Message,
    settings_repo: SettingsRepository,
    user: Dict[str, Any],
) -> None:
    """Show current user settings and preferences."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    settings_doc = await settings_repo.get_or_create_settings(user_id)

    auto_backup_status = "Enabled ✅" if settings_doc.get("auto_backup", True) else "Disabled ❌"
    dedup_status = "Enabled ✅" if settings_doc.get("duplicate_detection", True) else "Disabled ❌"
    notif_status = "Enabled ✅" if settings_doc.get("notifications_enabled", True) else "Disabled ❌"
    max_size_formatted = format_bytes(settings_doc.get("max_file_size", 52428800))

    settings_text = (
        "⚙️ <b>Your Backup Settings & Preferences</b>\n\n"
        f"• <b>Auto-Backup:</b> {auto_backup_status}\n"
        f"• <b>Duplicate Detection:</b> {dedup_status}\n"
        f"• <b>Max File Size Limit:</b> <code>{max_size_formatted}</code>\n"
        f"• <b>Completion Alerts:</b> {notif_status}\n\n"
        "💡 <i>Settings can be customized via the web dashboard or admin controls.</i>"
    )
    await message.answer(text=settings_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
