"""/start command handler."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command: greet user and present main menu keyboard."""
    first_name = message.from_user.first_name if message.from_user else "there"
    welcome_text = (
        f"👋 Hello, <b>{first_name}</b>!\n\n"
        f"Welcome to <b>Telegram Backup Bot</b> 📦\n\n"
        f"I automatically archive your media and files safely to your private backup storage.\n\n"
        f"<b>How to use:</b>\n"
        f"• Simply send or forward any document, photo, video, audio, or voice message directly to this chat.\n"
        f"• Use the menu below to view your backed-up files, storage stats, and settings."
    )
    await message.answer(
        text=welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML",
    )
