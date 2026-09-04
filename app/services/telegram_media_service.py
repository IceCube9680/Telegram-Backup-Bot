"""Telegram Media extraction and normalization service."""

from typing import Any, List, Optional
from aiogram.types import Message
from pydantic import BaseModel, Field

from app.database.models.backup_item import MediaType


class TelegramMediaInfo(BaseModel):
    """Normalized metadata extracted from incoming Telegram media messages."""

    user_id: int = Field(..., description="Telegram user ID")
    telegram_message_id: int = Field(..., description="Telegram message ID")
    file_id: str = Field(..., description="Telegram download file ID")
    file_unique_id: str = Field(..., description="Telegram unique file ID")
    media_type: MediaType = Field(..., description="Classified media type")
    original_filename: str = Field(..., description="Normalized display filename")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    file_size: Optional[int] = Field(default=None, ge=0, description="File size in bytes if known")
    caption: Optional[str] = Field(default=None, description="User provided message caption")


class TelegramMediaService:
    """Service to extract and normalize media from aiogram Message updates."""

    @classmethod
    def extract_media(cls, message: Message) -> Optional[TelegramMediaInfo]:
        """Inspect Telegram Message and extract normalized TelegramMediaInfo or return None if unsupported."""
        if not message.from_user:
            return None

        user_id = message.from_user.id
        msg_id = message.message_id
        caption = message.caption

        # 1. Document
        if message.document:
            doc = message.document
            filename = doc.file_name or f"document_{doc.file_unique_id}.bin"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=doc.file_id,
                file_unique_id=doc.file_unique_id,
                media_type=MediaType.DOCUMENT,
                original_filename=filename,
                mime_type=doc.mime_type,
                file_size=doc.file_size,
                caption=caption,
            )

        # 2. Photo (select highest resolution photo in list)
        if message.photo:
            best_photo = max(
                message.photo,
                key=lambda p: ((p.width or 0) * (p.height or 0), p.file_size or 0),
            )
            filename = f"photo_{best_photo.file_unique_id}.jpg"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=best_photo.file_id,
                file_unique_id=best_photo.file_unique_id,
                media_type=MediaType.PHOTO,
                original_filename=filename,
                mime_type="image/jpeg",
                file_size=best_photo.file_size,
                caption=caption,
            )

        # 3. Video
        if message.video:
            video = message.video
            filename = video.file_name or f"video_{video.file_unique_id}.mp4"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=video.file_id,
                file_unique_id=video.file_unique_id,
                media_type=MediaType.VIDEO,
                original_filename=filename,
                mime_type=video.mime_type or "video/mp4",
                file_size=video.file_size,
                caption=caption,
            )

        # 4. Audio
        if message.audio:
            audio = message.audio
            filename = audio.file_name or f"audio_{audio.file_unique_id}.mp3"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=audio.file_id,
                file_unique_id=audio.file_unique_id,
                media_type=MediaType.AUDIO,
                original_filename=filename,
                mime_type=audio.mime_type or "audio/mpeg",
                file_size=audio.file_size,
                caption=caption,
            )

        # 5. Voice
        if message.voice:
            voice = message.voice
            filename = f"voice_{voice.file_unique_id}.ogg"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=voice.file_id,
                file_unique_id=voice.file_unique_id,
                media_type=MediaType.VOICE,
                original_filename=filename,
                mime_type=voice.mime_type or "audio/ogg",
                file_size=voice.file_size,
                caption=caption,
            )

        # 6. Animation (GIF/MP4 animation)
        if message.animation:
            anim = message.animation
            filename = anim.file_name or f"animation_{anim.file_unique_id}.mp4"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=anim.file_id,
                file_unique_id=anim.file_unique_id,
                media_type=MediaType.ANIMATION,
                original_filename=filename,
                mime_type=anim.mime_type or "video/mp4",
                file_size=anim.file_size,
                caption=caption,
            )

        # 7. Video Note (round video)
        if message.video_note:
            vnote = message.video_note
            filename = f"videonote_{vnote.file_unique_id}.mp4"
            return TelegramMediaInfo(
                user_id=user_id,
                telegram_message_id=msg_id,
                file_id=vnote.file_id,
                file_unique_id=vnote.file_unique_id,
                media_type=MediaType.VIDEO_NOTE,
                original_filename=filename,
                mime_type="video/mp4",
                file_size=vnote.file_size,
                caption=caption,
            )

        return None
