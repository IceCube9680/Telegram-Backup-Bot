"""/start command handler."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
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


@router.message(Command("login"))
@router.message(Command("web"))
async def cmd_login(message: Message) -> None:
    """Generate a single-use 6-digit one-time login code for the Web Dashboard."""
    if not message.from_user:
        return

    from app.core.config import get_settings
    from app.core.security import LoginTokenManager
    from app.database.mongo import get_database

    user_id = message.from_user.id
    db = await get_database()
    code, expires_at = await LoginTokenManager.create_login_token(
        db=db,
        user_id=user_id,
        telegram_user_id=user_id,
        expire_minutes=10,
    )
    settings = get_settings()
    login_url = f"{settings.WEB_BASE_URL}/login"

    text = (
        f"🔐 <b>Web Dashboard Login</b>\n\n"
        f"Your one-time login code is:\n\n"
        f"<code>{code}</code>\n\n"
        f"⏱ <i>This code expires in 10 minutes and can only be used once.</i>\n\n"
        f"Go to the Web Dashboard and enter this code to log in."
    )
    await message.answer(text=text, parse_mode="HTML")
