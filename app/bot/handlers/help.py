"""/help command handler."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard

router = Router(name="help")


@router.message(Command("help"))
@router.message(F.text == "❓ Help")
async def cmd_help(message: Message) -> None:
    """Handle /help command and '❓ Help' button."""
    help_text = (
        "📖 <b>Telegram Backup Bot — Help & Usage Guide</b>\n\n"
        "<b>📦 Supported Content Types:</b>\n"
        "• <b>Documents</b>: PDF, ZIP, DOCX, TXT, APK, etc.\n"
        "• <b>Photos</b>: High-resolution images & graphics\n"
        "• <b>Videos</b>: MP4, MKV, MOV video clips\n"
        "• <b>Audio & Voice</b>: MP3, M4A, FLAC & Voice messages\n"
        "• <b>Animations & Video Notes</b>: GIFs and round video notes\n\n"
        "<b>⚡ Available Commands:</b>\n"
        "• /backup — Instructions on backing up files\n"
        "• /files — View your recent backed-up files\n"
        "• /stats — View your current storage quota & count\n"
        "• /settings — View backup preferences\n"
        "• /help — Show this help manual\n\n"
        "💡 <i>Tip: You don't need to type any command to back up. Just forward or send files directly!</i>"
    )
    await message.answer(
        text=help_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML",
    )
