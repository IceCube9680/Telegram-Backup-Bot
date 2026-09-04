"""Telegram Bot application lifecycle, dispatcher configuration, and polling runner."""

import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pymongo.asynchronous.database import AsyncDatabase

from app.bot.handlers import get_all_routers
from app.bot.middlewares.user_middleware import UserMiddleware
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger, setup_logging
from app.database.indexes import ensure_indexes
from app.database.mongo import mongo_manager

logger = get_logger(__name__)


def create_dispatcher(db: AsyncDatabase) -> Dispatcher:
    """Instantiate and configure Dispatcher with middlewares and all routers."""
    dp = Dispatcher()

    # Register user registration and dependency injection middleware
    user_middleware = UserMiddleware(db)
    dp.message.outer_middleware(user_middleware)
    dp.callback_query.outer_middleware(user_middleware)

    # Register all routers
    for router in get_all_routers():
        dp.include_router(router)

    return dp


def create_bot(token: Optional[str] = None) -> Bot:
    """Create and configure aiogram Bot instance."""
    settings = get_settings()
    bot_token = token or settings.telegram_token

    if not bot_token:
        raise ConfigurationError(
            message="Telegram Bot Token is not configured. Set TELEGRAM_BOT_TOKEN in .env or environment.",
            details={"env_key": "TELEGRAM_BOT_TOKEN"},
        )

    return Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_bot() -> None:
    """Start Telegram bot polling lifecycle with database connection management."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info(f"Starting Telegram Backup Bot in {settings.TELEGRAM_MODE} mode...")

    # Connect to MongoDB
    db = await mongo_manager.connect()
    await ensure_indexes(db)

    bot = create_bot()
    dp = create_dispatcher(db)

    try:
        # Delete any existing webhook before starting polling
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Bot is active and listening for incoming Telegram updates...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Bot polling interrupted by system signal.")
    finally:
        logger.info("Shutting down bot session and closing MongoDB connection...")
        await bot.session.close()
        await mongo_manager.disconnect()
        logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    asyncio.run(run_bot())
