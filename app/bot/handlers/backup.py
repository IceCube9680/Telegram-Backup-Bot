"""Backup command and direct media message ingestion handler."""

import html
from typing import Any, Dict
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main import get_main_keyboard
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.services.backup_service import BackupService
from app.services.telegram_media_service import TelegramMediaService

logger = get_logger(__name__)

router = Router(name="backup")


@router.message(Command("backup"))
@router.message(F.text == "📦 Backup")
async def cmd_backup(message: Message) -> None:
    """Provide backup instructions when command is invoked without attached media."""
    text = (
        "📦 <b>How to Back Up Your Files</b>\n\n"
        "You can back up any file or media at any time!\n\n"
        "1. Simply <b>send</b> or <b>forward</b> a document, photo, video, or audio file directly to this chat.\n"
        "2. The bot will validate the file and place it in the secure backup processing queue.\n"
        "3. You will receive an immediate confirmation with your task tracking ID.\n\n"
        "🚀 <i>Go ahead and send a file now to try it out!</i>"
    )
    await message.answer(text=text, reply_markup=get_main_keyboard(), parse_mode="HTML")


@router.message(
    F.document | F.photo | F.video | F.audio | F.voice | F.animation | F.video_note
)
async def handle_direct_media(
    message: Message,
    backup_service: BackupService,
    user: Dict[str, Any],
) -> None:
    """Ingest incoming Telegram media, extract metadata, validate quotas, and enqueue backup task."""
    media_info = TelegramMediaService.extract_media(message)

    if not media_info:
        await message.reply(
            "⚠️ <b>Unsupported Media:</b> Unable to process the received message format.",
            parse_mode="HTML",
        )
        return

    try:
        result = await backup_service.enqueue_backup(media_info=media_info, user_data=user)

        # Generate a safe short task identifier (last 6 hex characters of task_id)
        short_task_id = result.task_id[-6:].upper() if len(result.task_id) >= 6 else result.task_id.upper()
        escaped_filename = html.escape(result.original_filename)

        if result.is_duplicate:
            response_text = (
                "ℹ️ <b>Already Queued</b>\n\n"
                f"📄 <b>File:</b> <code>{escaped_filename}</code>\n"
                f"🆔 <b>Task:</b> <code>#{short_task_id}</code>\n\n"
                "<i>This file was already received and is in the backup queue.</i>"
            )
        else:
            response_text = (
                "📦 <b>Backup Queued</b>\n\n"
                f"📄 <b>File:</b> <code>{escaped_filename}</code>\n"
                f"📊 <b>Size:</b> {result.file_size_formatted}\n"
                f"🔖 <b>Type:</b> {result.media_type.capitalize()}\n"
                f"🆔 <b>Task:</b> <code>#{short_task_id}</code>\n\n"
                "<i>Your file has been added to the backup queue.</i>"
            )

        await message.reply(
            text=response_text,
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )

    except ValidationError as exc:
        logger.warning(f"Backup validation failed for user {media_info.user_id}: {exc.message}")
        await message.reply(
            text=f"⚠️ <b>Backup Rejected</b>\n\n{html.escape(exc.message)}",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception(f"Unexpected error enqueuing backup for user {media_info.user_id}: {exc}")
        await message.reply(
            text="❌ <b>Backup Error:</b> An unexpected error occurred while queuing your file. Please try again later.",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )
