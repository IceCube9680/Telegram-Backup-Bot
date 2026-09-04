"""/files command handler."""

import html
from typing import Any, Dict
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.services.backup_service import format_bytes

router = Router(name="files")


@router.message(Command("files"))
@router.message(F.text == "📁 My Files")
async def cmd_files(
    message: Message,
    item_repo: BackupItemRepository,
    user: Dict[str, Any],
) -> None:
    """List recent backed-up files for the current user."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    items = await item_repo.list_items(user_id=user_id, limit=10, sort_desc=True)

    if not items:
        empty_text = (
            "📁 <b>Your Backup Vault is Empty</b>\n\n"
            "You haven't backed up any files yet.\n\n"
            "💡 <i>Send or forward a document, photo, or video to start backing up right away!</i>"
        )
        await message.answer(text=empty_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    lines = ["📁 <b>Your Recent Backups (Last 10):</b>\n"]
    for idx, item in enumerate(items, start=1):
        filename = html.escape(item.get("original_filename") or "Unnamed file")
        size_str = format_bytes(item.get("file_size"))
        media_type = item.get("media_type", "file").capitalize()
        status_icon = "⏳" if item.get("status") == "pending" else ("✅" if item.get("status") == "completed" else "❌")

        lines.append(f"{idx}. {status_icon} <b>{filename}</b>\n   └ <i>{media_type} • {size_str}</i>")

    lines.append("\n💡 <i>Send new media to add to your backup library.</i>")
    await message.answer(text="\n".join(lines), reply_markup=get_main_keyboard(), parse_mode="HTML")
