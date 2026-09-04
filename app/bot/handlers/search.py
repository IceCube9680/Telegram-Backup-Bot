"""/search command handler."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard

router = Router(name="search")


@router.message(Command("search"))
@router.message(F.text == "🔎 Search")
async def cmd_search(message: Message) -> None:
    """Handle /search command and '🔎 Search' button."""
    text = (
        "🔎 <b>Search Your Backups</b>\n\n"
        "Advanced search across filenames, captions, media types, folders, and tags is currently being indexed.\n\n"
        "💡 <i>Tip: Use <code>/files</code> to view your most recent backed-up documents and media.</i>"
    )
    await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
