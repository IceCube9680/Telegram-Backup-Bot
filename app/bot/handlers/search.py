"""/search command and search pagination callback handlers."""

import html
import urllib.parse
from typing import Any, Dict, List, Optional
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main import get_main_keyboard
from app.database.models.backup_item import ItemStatus
from app.services.backup_service import format_bytes
from app.services.search_service import SearchService

router = Router(name="search")


def build_search_keyboard(
    items: List[Dict[str, Any]],
    query: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build keyboard for search results."""
    buttons: List[List[InlineKeyboardButton]] = []

    # File buttons
    for item in items:
        item_id = item["id"]
        filename = item.get("original_filename") or "Unnamed file"
        if len(filename) > 28:
            filename = f"{filename[:25]}..."
        status = item.get("status")
        icon = "✅" if status == ItemStatus.COMPLETED.value else ("⏳" if status == ItemStatus.PROCESSING.value else ("❌" if status == ItemStatus.FAILED.value else "🕒"))
        size_str = format_bytes(item.get("file_size"))

        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {filename} ({size_str})",
                callback_data=f"file:view:{item_id}",
            )
        ])

    # Navigation row
    encoded_query = urllib.parse.quote(query[:30])
    nav_row: List[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"search:pg:{encoded_query}:{page - 1}"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{max(1, total_pages)}", callback_data=f"search:pg:{encoded_query}:{page}"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"search:pg:{encoded_query}:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="📁 View All Files", callback_data="files:page:1")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("search"))
@router.message(F.text == "🔎 Search")
async def cmd_search(
    message: Message,
    search_service: Optional[SearchService] = None,
    command: Optional[CommandObject] = None,
    **kwargs: Any,
) -> None:
    """Handle /search command and search query."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    query_text = (command.args if command and command.args else "").strip()

    if not query_text or search_service is None:
        help_text = (
            "🔎 <b>Search Your Backups</b>\n\n"
            "To search your backed-up documents, photos, and media, use:\n"
            "<code>/search &lt;keyword or filename&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/search passport</code>\n"
            "• <code>/search .pdf</code>\n"
            "• <code>/search vacation photo</code>\n\n"
            "💡 <i>Tip: Search looks across filenames, captions, and MIME types.</i>"
        )
        await message.answer(text=help_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    res = await search_service.search_files(user_id=user_id, query=query_text, page=1, page_size=8)

    if res.total == 0:
        no_res_text = (
            f"🔎 <b>No files found for:</b> <code>{html.escape(query_text)}</code>\n\n"
            "Try a different keyword or check your file list with <code>/files</code>."
        )
        await message.answer(text=no_res_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    text = f"🔎 <b>Search Results for:</b> <code>{html.escape(query_text)}</code> ({res.total} matches)\n\n<i>Tap a file to open details:</i>"
    kb = build_search_keyboard(res.items, query_text, res.page, res.total_pages)
    await message.answer(text=text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("search:pg:"))
async def cb_search_pagination(
    callback: CallbackQuery,
    search_service: SearchService,
) -> None:
    """Handle search results page navigation."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    encoded_query = parts[2] if len(parts) > 2 else ""
    query = urllib.parse.unquote(encoded_query)
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    res = await search_service.search_files(user_id=user_id, query=query, page=page, page_size=8)
    if res.total == 0:
        await callback.message.edit_text(f"🔎 No results found for '{html.escape(query)}'.", parse_mode="HTML")
        await callback.answer()
        return

    text = f"🔎 <b>Search Results for:</b> <code>{html.escape(query)}</code> ({res.total} matches)\n\n<i>Tap a file to open details:</i>"
    kb = build_search_keyboard(res.items, query, res.page, res.total_pages)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
