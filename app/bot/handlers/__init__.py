"""Bot handlers module."""

from aiogram import Router

from app.bot.handlers.backup import router as backup_router
from app.bot.handlers.files import router as files_router
from app.bot.handlers.folders import router as folders_router
from app.bot.handlers.help import router as help_router
from app.bot.handlers.search import router as search_router
from app.bot.handlers.settings import router as settings_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.stats import router as stats_router
from app.bot.handlers.tags import router as tags_router


def get_all_routers() -> list[Router]:
    """Return all configured bot routers in priority order."""
    return [
        start_router,
        help_router,
        backup_router,
        files_router,
        folders_router,
        tags_router,
        search_router,
        stats_router,
        settings_router,
    ]
