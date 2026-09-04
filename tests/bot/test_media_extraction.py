"""Unit tests for TelegramMediaService extraction and normalization."""

from datetime import datetime, timezone
from aiogram.types import Animation, Audio, Chat, Document, Message, PhotoSize, User, Video, VideoNote, Voice
import pytest

from app.database.models.backup_item import MediaType
from app.services.telegram_media_service import TelegramMediaInfo, TelegramMediaService


def make_user(user_id: int = 12345, first_name: str = "Alice") -> User:
    """Helper to instantiate an aiogram User."""
    return User(id=user_id, is_bot=False, first_name=first_name, username="alice")


def make_chat(chat_id: int = 12345) -> Chat:
    """Helper to instantiate an aiogram Chat."""
    return Chat(id=chat_id, type="private")


def test_extract_document_standard():
    """Test extracting document metadata with filename, size, and mime type."""
    user = make_user()
    chat = make_chat()
    doc = Document(
        file_id="doc_file_123",
        file_unique_id="doc_uniq_123",
        file_name="Annual_Report.pdf",
        mime_type="application/pdf",
        file_size=204800,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=101, date=now, chat=chat, from_user=user, document=doc, caption="Q4 Report")

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.user_id == 12345
    assert info.telegram_message_id == 101
    assert info.file_id == "doc_file_123"
    assert info.file_unique_id == "doc_uniq_123"
    assert info.media_type == MediaType.DOCUMENT
    assert info.original_filename == "Annual_Report.pdf"
    assert info.mime_type == "application/pdf"
    assert info.file_size == 204800
    assert info.caption == "Q4 Report"


def test_extract_photo_highest_resolution():
    """Test extracting photo selects highest resolution PhotoSize from array."""
    user = make_user()
    chat = make_chat()
    photos = [
        PhotoSize(file_id="p_small", file_unique_id="u_small", width=100, height=100, file_size=1000),
        PhotoSize(file_id="p_large", file_unique_id="u_large", width=1920, height=1080, file_size=500000),
        PhotoSize(file_id="p_med", file_unique_id="u_med", width=800, height=600, file_size=50000),
    ]
    now = datetime.now(timezone.utc)
    msg = Message(message_id=102, date=now, chat=chat, from_user=user, photo=photos)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.PHOTO
    assert info.file_id == "p_large"
    assert info.file_unique_id == "u_large"
    assert info.file_size == 500000
    assert info.mime_type == "image/jpeg"
    assert info.original_filename == "photo_u_large.jpg"


def test_extract_video():
    """Test extracting video metadata."""
    user = make_user()
    chat = make_chat()
    vid = Video(
        file_id="vid_123",
        file_unique_id="vid_uniq_123",
        width=1280,
        height=720,
        duration=60,
        file_name="vacation.mp4",
        mime_type="video/mp4",
        file_size=10485760,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=103, date=now, chat=chat, from_user=user, video=vid)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.VIDEO
    assert info.file_id == "vid_123"
    assert info.original_filename == "vacation.mp4"
    assert info.file_size == 10485760


def test_extract_audio():
    """Test extracting audio metadata."""
    user = make_user()
    chat = make_chat()
    aud = Audio(
        file_id="aud_123",
        file_unique_id="aud_uniq_123",
        duration=180,
        file_name="podcast.mp3",
        mime_type="audio/mpeg",
        file_size=5242880,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=104, date=now, chat=chat, from_user=user, audio=aud)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.AUDIO
    assert info.file_id == "aud_123"
    assert info.original_filename == "podcast.mp3"


def test_extract_voice():
    """Test extracting voice note."""
    user = make_user()
    chat = make_chat()
    voice = Voice(
        file_id="voice_123",
        file_unique_id="voice_uniq_123",
        duration=15,
        mime_type="audio/ogg",
        file_size=32000,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=105, date=now, chat=chat, from_user=user, voice=voice)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.VOICE
    assert info.file_id == "voice_123"
    assert info.original_filename == "voice_voice_uniq_123.ogg"


def test_extract_animation():
    """Test extracting animation (GIF)."""
    user = make_user()
    chat = make_chat()
    anim = Animation(
        file_id="anim_123",
        file_unique_id="anim_uniq_123",
        width=400,
        height=300,
        duration=3,
        file_name="meme.mp4",
        mime_type="video/mp4",
        file_size=500000,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=106, date=now, chat=chat, from_user=user, animation=anim)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.ANIMATION
    assert info.file_id == "anim_123"


def test_extract_video_note():
    """Test extracting round video note."""
    user = make_user()
    chat = make_chat()
    vnote = VideoNote(
        file_id="vnote_123",
        file_unique_id="vnote_uniq_123",
        length=240,
        duration=10,
        file_size=800000,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=107, date=now, chat=chat, from_user=user, video_note=vnote)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.media_type == MediaType.VIDEO_NOTE
    assert info.file_id == "vnote_123"


def test_extract_unsupported_text_message():
    """Test text-only messages return None from media extractor."""
    user = make_user()
    chat = make_chat()
    now = datetime.now(timezone.utc)
    msg = Message(message_id=108, date=now, chat=chat, from_user=user, text="Just plain text")

    info = TelegramMediaService.extract_media(msg)
    assert info is None


def test_extract_unicode_and_long_filename():
    """Test document with Unicode and long filenames."""
    user = make_user()
    chat = make_chat()
    unicode_name = "日本語のドキュメント_🎉_2026.pdf"
    doc = Document(
        file_id="doc_uni",
        file_unique_id="doc_u_uni",
        file_name=unicode_name,
        mime_type="application/pdf",
        file_size=1000,
    )
    now = datetime.now(timezone.utc)
    msg = Message(message_id=109, date=now, chat=chat, from_user=user, document=doc)

    info = TelegramMediaService.extract_media(msg)
    assert info is not None
    assert info.original_filename == unicode_name
