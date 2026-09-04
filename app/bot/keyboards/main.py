"""Telegram Bot Keyboard builders."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Return the persistent main reply keyboard with quick navigation buttons."""
    keyboard = [
        [
            KeyboardButton(text="📦 Backup"),
            KeyboardButton(text="📁 My Files"),
        ],
        [
            KeyboardButton(text="🔎 Search"),
            KeyboardButton(text="📊 Stats"),
        ],
        [
            KeyboardButton(text="⚙️ Settings"),
            KeyboardButton(text="❓ Help"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
