"""/files command and interactive file management callback handlers."""

import html
from typing import Any, Dict, List, Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main import get_main_keyboard
from app.database.models.backup_item import ItemStatus
from app.services.backup_management_service import BackupManagementService
from app.services.backup_service import format_bytes
from app.services.folder_service import FolderService
from app.services.tag_service import TagService

router = Router(name="files")


def build_files_keyboard(
    items: List[Dict[str, Any]],
    page: int,
    total_pages: int,
    prefix: str = "files",
) -> InlineKeyboardMarkup:
    """Build an interactive inline keyboard for browsing files and navigating pages."""
    buttons: List[List[InlineKeyboardButton]] = []

    # File selection buttons (1 per row)
    for idx, item in enumerate(items, start=1):
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

    # Navigation controls row
    nav_row: List[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"{prefix}:page:{page - 1}"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{max(1, total_pages)}", callback_data=f"{prefix}:page:{page}"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"{prefix}:page:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"{prefix}:page:{page}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_file_details_keyboard(item_id: str, status: str) -> InlineKeyboardMarkup:
    """Build action buttons for a selected file."""
    buttons: List[List[InlineKeyboardButton]] = []

    action_row: List[InlineKeyboardButton] = []
    action_row.append(InlineKeyboardButton(text="🗑 Delete", callback_data=f"file:del_prompt:{item_id}"))

    if status == ItemStatus.FAILED.value:
        action_row.append(InlineKeyboardButton(text="🔄 Retry", callback_data=f"file:retry:{item_id}"))

    buttons.append(action_row)

    buttons.append([
        InlineKeyboardButton(text="📁 Move to Folder", callback_data=f"file:move_menu:{item_id}"),
        InlineKeyboardButton(text="🏷 Tags", callback_data=f"file:tag_menu:{item_id}"),
    ])

    buttons.append([
        InlineKeyboardButton(text="🔄 Refresh", callback_data=f"file:view:{item_id}"),
        InlineKeyboardButton(text="⬅️ Back to Files", callback_data="files:page:1"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("files"))
@router.message(F.text == "📁 My Files")
async def cmd_files(
    message: Message,
    management_service: Optional[BackupManagementService] = None,
    item_repo: Optional[Any] = None,
    user: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> None:
    """List backed-up files with pagination for the current user."""
    if not message.from_user:
        return

    user_id = message.from_user.id

    if management_service is None and item_repo is not None:
        items = await item_repo.list_items(user_id=user_id, limit=10, sort_desc=True)
        if not items:
            empty_text = (
                "📁 <b>Your Backup Vault is Empty</b>\n\n"
                "You haven't backed up any files yet.\n\n"
                "💡 <i>Send or forward a document, photo, or video to start backing up right away!</i>"
            )
            await message.answer(text=empty_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
            return
        lines = ["📁 <b>Your Recent Backups:</b>\n"]
        for idx, item in enumerate(items, start=1):
            filename = html.escape(item.get("original_filename") or "Unnamed file")
            size_str = format_bytes(item.get("file_size"))
            media_type = item.get("media_type", "file").capitalize()
            status_icon = "⏳" if item.get("status") == "pending" else ("✅" if item.get("status") == "completed" else "❌")
            lines.append(f"{idx}. {status_icon} <b>{filename}</b>\n   └ <i>{media_type} • {size_str}</i>")
        lines.append("\n💡 <i>Send new media to add to your backup library.</i>")
        await message.answer(text="\n".join(lines), reply_markup=get_main_keyboard(), parse_mode="HTML")
        return

    if management_service:
        res = await management_service.list_user_files(user_id=user_id, page=1, page_size=8)
        if not res.items:
            empty_text = (
                "📁 <b>Your Backup Vault is Empty</b>\n\n"
                "You haven't backed up any files yet.\n\n"
                "💡 <i>Send or forward a document, photo, or video to start backing up right away!</i>"
            )
            await message.answer(text=empty_text, reply_markup=get_main_keyboard(), parse_mode="HTML")
            return

        text = f"📁 <b>Your Backed-up Files ({res.total} total)</b>\n\n<i>Select a file below to view details and actions:</i>"
        kb = build_files_keyboard(res.items, res.page, res.total_pages)
        await message.answer(text=text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("files:page:"))
async def cb_files_pagination(
    callback: CallbackQuery,
    management_service: BackupManagementService,
) -> None:
    """Handle files page navigation callback."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    res = await management_service.list_user_files(user_id=user_id, page=page, page_size=8)
    if not res.items:
        await callback.message.edit_text(
            "📁 <b>No files found.</b>\n\nSend a document or photo to create your first backup.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    text = f"📁 <b>Your Backed-up Files ({res.total} total)</b>\n\n<i>Select a file below to view details and actions:</i>"
    kb = build_files_keyboard(res.items, res.page, res.total_pages)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:view:"))
async def cb_file_view(
    callback: CallbackQuery,
    management_service: BackupManagementService,
) -> None:
    """Display detailed metadata and action controls for a specific file."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    details = await management_service.get_file_details(user_id=user_id, item_id=item_id)
    if not details:
        await callback.answer("File not found or already deleted.", show_alert=True)
        return

    status_str = "✅ Completed" if details.status == ItemStatus.COMPLETED.value else (
        f"⏳ Processing ({details.task_progress or 0:.0f}%)" if details.status == ItemStatus.PROCESSING.value else (
            f"❌ Failed ({details.task_error or 'Unknown error'})" if details.status == ItemStatus.FAILED.value else "🕒 Pending"
        )
    )

    tags_str = ", ".join(f"#{t}" for t in details.tags) if details.tags else "None"
    folder_str = f"📁 {html.escape(details.folder_name)}" if details.folder_name else "Root (/)"
    size_str = format_bytes(details.file_size)
    filename_esc = html.escape(details.original_filename)
    date_str = details.created_at.strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"📄 <b>File Details</b>\n\n"
        f"• <b>Name:</b> <code>{filename_esc}</code>\n"
        f"• <b>Type:</b> <i>{details.media_type.capitalize()}</i>\n"
        f"• <b>Size:</b> <code>{size_str}</code>\n"
        f"• <b>Status:</b> {status_str}\n"
        f"• <b>Created:</b> <code>{date_str}</code>\n"
        f"• <b>SHA-256:</b> <code>{details.sha256_short or 'Calculating...'}</code>\n"
        f"• <b>Folder:</b> {folder_str}\n"
        f"• <b>Tags:</b> {tags_str}\n"
    )

    if details.caption:
        text += f"\n💬 <i>Caption: {html.escape(details.caption)}</i>\n"

    kb = build_file_details_keyboard(item_id, details.status)
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:del_prompt:"))
async def cb_file_delete_prompt(
    callback: CallbackQuery,
    management_service: BackupManagementService,
) -> None:
    """Prompt user for deletion confirmation."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    details = await management_service.get_file_details(user_id=user_id, item_id=item_id)
    if not details:
        await callback.answer("File not found.", show_alert=True)
        return

    text = (
        f"⚠️ <b>Delete this backup?</b>\n\n"
        f"<b>File:</b> <code>{html.escape(details.original_filename)}</code>\n"
        f"<b>Size:</b> <code>{format_bytes(details.file_size)}</code>\n\n"
        "This action will remove the backup permanently from storage."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm Delete", callback_data=f"file:del_confirm:{item_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"file:view:{item_id}"),
            ]
        ]
    )
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:del_confirm:"))
async def cb_file_delete_confirm(
    callback: CallbackQuery,
    management_service: BackupManagementService,
) -> None:
    """Execute confirmed file deletion and display outcome."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    try:
        result = await management_service.delete_file(user_id=user_id, item_id=item_id)
        text = f"🗑 <b>Backup Deleted</b>\n\n<code>{html.escape(result.filename)}</code> has been deleted successfully."
    except Exception as e:
        text = f"❌ <b>Deletion Failed</b>\n\n{html.escape(str(e))}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Back to Files", callback_data="files:page:1")]
        ]
    )
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:retry:"))
async def cb_file_retry(
    callback: CallbackQuery,
    management_service: BackupManagementService,
) -> None:
    """Re-queue a failed backup task for execution."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    try:
        result = await management_service.retry_failed_task(user_id=user_id, item_id=item_id)
        await callback.answer(result.message, show_alert=True)
        # Refresh view
        details = await management_service.get_file_details(user_id=user_id, item_id=item_id)
        if details:
            kb = build_file_details_keyboard(item_id, details.status)
            await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception as e:
        await callback.answer(f"Retry failed: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("file:move_menu:"))
async def cb_file_move_menu(
    callback: CallbackQuery,
    folder_service: FolderService,
) -> None:
    """Display folder selection list to move an item."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    folders = await folder_service.list_folders(user_id=user_id)

    buttons: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="📁 Root (/)", callback_data=f"file:move_to:{item_id}:root")]
    ]

    for f in folders:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {f['name']}", callback_data=f"file:move_to:{item_id}:{f['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data=f"file:view:{item_id}")])

    text = "📁 <b>Move File to Folder</b>\n\nSelect destination folder:"
    await callback.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:move_to:"))
async def cb_file_move_to(
    callback: CallbackQuery,
    folder_service: FolderService,
    management_service: BackupManagementService,
) -> None:
    """Move file to selected folder."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""
    target = parts[3] if len(parts) > 3 else ""

    folder_id = None if target == "root" else target

    try:
        await folder_service.move_item_to_folder(user_id=user_id, item_id=item_id, folder_id=folder_id)
        await callback.answer("File moved successfully!", show_alert=False)
        # Return to details view
        details = await management_service.get_file_details(user_id=user_id, item_id=item_id)
        if details:
            text = (
                f"📄 <b>File Details</b>\n\n"
                f"• <b>Name:</b> <code>{html.escape(details.original_filename)}</code>\n"
                f"• <b>Status:</b> {details.status}\n"
                f"• <b>Folder:</b> {html.escape(details.folder_name) if details.folder_name else 'Root (/)'}\n"
            )
            kb = build_file_details_keyboard(item_id, details.status)
            await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"Move failed: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("file:tag_menu:"))
async def cb_file_tag_menu(
    callback: CallbackQuery,
    tag_service: TagService,
) -> None:
    """Display tag toggle controls for a file."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""

    all_tags = await tag_service.list_tags(user_id=user_id)
    attached_tags = await tag_service.get_item_tags(user_id=user_id, item_id=item_id)
    attached_ids = {t["id"] for t in attached_tags}

    buttons: List[List[InlineKeyboardButton]] = []
    for t in all_tags:
        is_attached = t["id"] in attached_ids
        mark = "✅" if is_attached else "➕"
        action = "detach" if is_attached else "attach"
        buttons.append([
            InlineKeyboardButton(
                text=f"{mark} #{t['name']}",
                callback_data=f"file:tag_act:{item_id}:{t['id']}:{action}",
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅️ Back to File Details", callback_data=f"file:view:{item_id}")])

    text = "🏷 <b>Manage Tags</b>\n\nTap a tag to assign or remove it from this file:"
    await callback.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("file:tag_act:"))
async def cb_file_tag_action(
    callback: CallbackQuery,
    tag_service: TagService,
) -> None:
    """Attach or detach a tag from an item."""
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = parts[2] if len(parts) > 2 else ""
    tag_id = parts[3] if len(parts) > 3 else ""
    action = parts[4] if len(parts) > 4 else ""

    if action == "attach":
        await tag_service.assign_tag_to_item(user_id=user_id, item_id=item_id, tag_name_or_id=tag_id)
    else:
        await tag_service.remove_tag_from_item(user_id=user_id, item_id=item_id, tag_id=tag_id)

    # Re-render tag menu
    all_tags = await tag_service.list_tags(user_id=user_id)
    attached_tags = await tag_service.get_item_tags(user_id=user_id, item_id=item_id)
    attached_ids = {t["id"] for t in attached_tags}

    buttons: List[List[InlineKeyboardButton]] = []
    for t in all_tags:
        is_attached = t["id"] in attached_ids
        mark = "✅" if is_attached else "➕"
        act = "detach" if is_attached else "attach"
        buttons.append([
            InlineKeyboardButton(
                text=f"{mark} #{t['name']}",
                callback_data=f"file:tag_act:{item_id}:{t['id']}:{act}",
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅️ Back to File Details", callback_data=f"file:view:{item_id}")])

    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()
