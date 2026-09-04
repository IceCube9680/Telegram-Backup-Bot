"""/tags and tag management command and callback handlers."""

import html
from typing import Any, Dict, List, Optional
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.files import build_files_keyboard
from app.bot.keyboards.main import get_main_keyboard
from app.services.tag_service import TagService

router = Router(name="tags")


def build_tags_keyboard(tags: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Build inline keyboard for tags list."""
    buttons: List[List[InlineKeyboardButton]] = []

    # 2 tags per row
    row: List[InlineKeyboardButton] = []
    for t in tags:
        row.append(InlineKeyboardButton(text=f"🏷 #{t['name']}", callback_data=f"tag:view:{t['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="📁 View All Files", callback_data="files:page:1")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("tags"))
@router.message(F.text == "🏷 Tags")
async def cmd_tags(
    message: Message,
    tag_service: TagService,
) -> None:
    """List user tags."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    tags = await tag_service.list_tags(user_id=user_id)

    if not tags:
        text = (
            "🏷 <b>No Tags Yet</b>\n\n"
            "You haven't created any tags yet.\n\n"
            "<b>To create a tag:</b>\n"
            "<code>/newtag &lt;tag_name&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/newtag work</code>\n"
            "<code>/newtag receipts</code>\n\n"
            "💡 <i>You can also attach tags to files directly from the file details menu.</i>"
        )
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    text = (
        f"🏷 <b>Your Tags ({len(tags)} total)</b>\n\n"
        "<i>Select a tag to view associated files, or use <code>/newtag &lt;name&gt;</code>:</i>"
    )
    kb = build_tags_keyboard(tags)
    await message.answer(text=text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("newtag"))
@router.message(Command("tag"))
async def cmd_newtag(
    message: Message,
    tag_service: TagService,
    command: Optional[CommandObject] = None,
) -> None:
    """Create a new tag via command."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    name = (command.args if command and command.args else "").strip()

    if not name:
        text = (
            "🏷 <b>Create New Tag</b>\n\n"
            "Usage: <code>/newtag &lt;tag_name&gt;</code>\n"
            "Example: <code>/newtag important</code>"
        )
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    try:
        tag = await tag_service.create_tag(user_id=user_id, name=name)
        text = f"✅ <b>Tag Created</b>\n\n🏷 <code>#{html.escape(tag['name'])}</code> has been created successfully!"
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ <b>Error:</b> {html.escape(str(e))}", parse_mode="HTML")


@router.callback_query(F.data.startswith("tag:view:"))
async def cb_tag_view(
    callback: CallbackQuery,
    tag_service: TagService,
) -> None:
    """View files labeled with a selected tag."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    tag_id = parts[2] if len(parts) > 2 else ""

    result = await tag_service.list_tagged_files(user_id=user_id, tag_id=tag_id, limit=8, offset=0)
    tag_info = result.get("tag")
    if not tag_info:
        await callback.answer("Tag not found.", show_alert=True)
        return

    tag_name = tag_info["name"]
    items = result.get("items", [])
    total = result.get("total", 0)

    if not items:
        text = f"🏷 <b>Tag: #{html.escape(tag_name)}</b>\n\nNo files are currently assigned this tag."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Delete Tag", callback_data=f"tag:del:{tag_id}")],
                [InlineKeyboardButton(text="⬅️ Back to Tags", callback_data="tags:list")],
            ]
        )
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    text = f"🏷 <b>Files Tagged #{html.escape(tag_name)}</b> ({total} files)\n\n<i>Select a file to inspect:</i>"
    kb = build_files_keyboard(items, 1, 1)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "tags:list")
async def cb_tags_list(
    callback: CallbackQuery,
    tag_service: TagService,
) -> None:
    """Return to tags list view."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    tags = await tag_service.list_tags(user_id=user_id)

    text = f"🏷 <b>Your Tags ({len(tags)} total)</b>\n\n<i>Select a tag to view files:</i>"
    kb = build_tags_keyboard(tags)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("tag:del:"))
async def cb_tag_delete(
    callback: CallbackQuery,
    tag_service: TagService,
) -> None:
    """Delete a tag."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    tag_id = parts[2] if len(parts) > 2 else ""

    deleted = await tag_service.delete_tag(user_id=user_id, tag_id=tag_id)
    if deleted:
        await callback.answer("Tag deleted.", show_alert=True)
    else:
        await callback.answer("Tag could not be deleted.", show_alert=True)

    tags = await tag_service.list_tags(user_id=user_id)
    text = f"🏷 <b>Your Tags ({len(tags)} total)</b>"
    kb = build_tags_keyboard(tags)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
