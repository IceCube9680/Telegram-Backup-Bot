"""/folders and folder hierarchy command and callback handlers."""

import html
from typing import Any, Dict, List, Optional
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.files import build_files_keyboard
from app.bot.keyboards.main import get_main_keyboard
from app.services.backup_management_service import BackupManagementService
from app.services.folder_service import FolderService

router = Router(name="folders")


def build_folders_keyboard(folders: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Build inline keyboard for folder list."""
    buttons: List[List[InlineKeyboardButton]] = []

    for f in folders:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {f['name']}", callback_data=f"folder:view:{f['id']}")
        ])

    buttons.append([
        InlineKeyboardButton(text="📁 View All Files", callback_data="files:page:1")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("folders"))
@router.message(F.text == "📂 Folders")
async def cmd_folders(
    message: Message,
    folder_service: FolderService,
) -> None:
    """List all folders for user."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    folders = await folder_service.list_folders(user_id=user_id)

    if not folders:
        text = (
            "📂 <b>No Folders Yet</b>\n\n"
            "You haven't created any folders yet.\n\n"
            "<b>To create a folder:</b>\n"
            "<code>/newfolder &lt;folder_name&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/newfolder Work Documents</code>"
        )
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    text = (
        f"📂 <b>Your Folders ({len(folders)} total)</b>\n\n"
        "<i>Select a folder to view its contents, or use <code>/newfolder &lt;name&gt;</code> to create one:</i>"
    )
    kb = build_folders_keyboard(folders)
    await message.answer(text=text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("newfolder"))
@router.message(Command("mkdir"))
async def cmd_newfolder(
    message: Message,
    folder_service: FolderService,
    command: Optional[CommandObject] = None,
) -> None:
    """Create a new folder via command."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    name = (command.args if command and command.args else "").strip()

    if not name:
        text = (
            "📁 <b>Create New Folder</b>\n\n"
            "Usage: <code>/newfolder &lt;folder_name&gt;</code>\n"
            "Example: <code>/newfolder Personal Receipts</code>"
        )
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    try:
        folder = await folder_service.create_folder(user_id=user_id, name=name)
        text = f"✅ <b>Folder Created</b>\n\n📁 <code>{html.escape(folder['name'])}</code> has been created successfully!"
        await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ <b>Error:</b> {html.escape(str(e))}", parse_mode="HTML")


@router.callback_query(F.data.startswith("folder:view:"))
async def cb_folder_view(
    callback: CallbackQuery,
    folder_service: FolderService,
    management_service: BackupManagementService,
) -> None:
    """View contents of a selected folder."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    folder_id = parts[2] if len(parts) > 2 else ""

    folder = await folder_service.get_folder(user_id=user_id, folder_id=folder_id)
    if not folder:
        await callback.answer("Folder not found.", show_alert=True)
        return

    res = await management_service.list_user_files(user_id=user_id, folder_id=folder_id, page=1, page_size=8)

    folder_name_esc = html.escape(folder["name"])
    if not res.items:
        text = f"📁 <b>Folder: {folder_name_esc}</b>\n\nThis folder is currently empty.\nMove files here from the file details menu."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Delete Folder", callback_data=f"folder:del:{folder_id}")],
                [InlineKeyboardButton(text="⬅️ Back to Folders", callback_data="folders:list")],
            ]
        )
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    text = f"📁 <b>Folder: {folder_name_esc}</b> ({res.total} files)\n\n<i>Select a file to inspect:</i>"
    kb = build_files_keyboard(res.items, res.page, res.total_pages)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "folders:list")
async def cb_folders_list(
    callback: CallbackQuery,
    folder_service: FolderService,
) -> None:
    """Return to folders list view."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    folders = await folder_service.list_folders(user_id=user_id)

    text = f"📂 <b>Your Folders ({len(folders)} total)</b>\n\n<i>Select a folder to view contents:</i>"
    kb = build_folders_keyboard(folders)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("folder:del:"))
async def cb_folder_delete(
    callback: CallbackQuery,
    folder_service: FolderService,
) -> None:
    """Delete folder."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    folder_id = parts[2] if len(parts) > 2 else ""

    deleted = await folder_service.delete_folder(user_id=user_id, folder_id=folder_id)
    if deleted:
        await callback.answer("Folder deleted. Contained files moved to root.", show_alert=True)
    else:
        await callback.answer("Folder could not be deleted.", show_alert=True)

    # Return to folder list
    folders = await folder_service.list_folders(user_id=user_id)
    text = f"📂 <b>Your Folders ({len(folders)} total)</b>"
    kb = build_folders_keyboard(folders)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
