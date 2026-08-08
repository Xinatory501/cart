from __future__ import annotations
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.database import close_db, init_db
from handlers import chat, menu, start, help
from handlers import settings as settings_handler
from handlers.admin import (
    antiflood_settings,
    api_keys,
    database_backup,
    export as admin_export,
    main as admin_main,
    privacy_policy,
    reports,
    training,
    user_management,
)
from handlers.group import support
from middlewares.antiflood import AntiFloodMiddleware
from middlewares.ban_check import BanCheckMiddleware
from middlewares.admin_auth import AdminAuthMiddleware
from services.bot_profile_service import get_launch_profiles, register_runtime_profile
from services.pending_service import PendingService
from services.thread_service import ThreadService
from utils.logger import setup_logger
from utils.task_registry import task_registry


async def main():
    setup_logger()
    logger = logging.getLogger(__name__)

    if not settings.SUPPORT_GROUP_ID:
        logger.warning("SUPPORT_GROUP_ID is not set. Support group features are disabled.")

    await init_db()

    # Поддержка нового формата BOT_TOKEN (один экземпляр) и старого BOT1-BOT6
    primary_token = settings.primary_bot_token
    if not primary_token:
        raise RuntimeError(
            "Missing required BOT_TOKEN (or BOT1_TOKEN for legacy mode). "
            "Set BOT_TOKEN in .env for single-instance deployment."
        )

    launch_profiles = get_launch_profiles()

    bots: list = []
    for token, profile in launch_profiles:
        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        me = await bot.get_me()
        register_runtime_profile(me.id, profile)
        logger.info(
            "Registered bot @%s (%s, lang=%s, flag=%s)",
            me.username,
            profile.key,
            profile.default_language,
            profile.topic_flag,
        )
        if settings.SUPPORT_GROUP_ID:
            try:
                thread_service = ThreadService(bot)
                await thread_service.ensure_log_thread()
                updated = await thread_service.backfill_thread_ownership()
                if updated:
                    logger.info("Backfilled %s thread ownership records for %s", updated, profile.key)
            except Exception as error:
                logger.warning("Failed to ensure log thread for %s: %s", profile.key, error)
        bots.append(bot)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.middleware(BanCheckMiddleware())
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AdminAuthMiddleware())

    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(admin_main.router)

    dp.include_router(api_keys.router)
    dp.include_router(antiflood_settings.router)
    dp.include_router(user_management.router)
    dp.include_router(privacy_policy.router)
    dp.include_router(training.router)
    dp.include_router(database_backup.router)
    dp.include_router(reports.router)
    dp.include_router(admin_export.router)  # ADM-13: экспорт истории по тикету

    dp.include_router(support.router)

    dp.include_router(chat.router)
    dp.include_router(menu.router)
    dp.include_router(settings_handler.router)

    logger.info("Bots started successfully: %s", len(bots))

    await PendingService.process_pending_requests(bots)
    logger.info("Pending requests processed")

    # OPS-18: SLA timer
    from services.sla_service import SLAService
    sla_service = SLAService(bots)
    task_registry.register(sla_service.start(), "sla_service")

    from services.retention_service import RetentionService
    retention_service = RetentionService()
    task_registry.register(retention_service.start(), "retention_service")

    try:
        await dp.start_polling(*bots, allowed_updates=dp.resolve_used_update_types())
    finally:
        await close_db()
        await task_registry.graceful_shutdown()
        for bot in bots:
            await bot.session.close()
        logger.info("Bots stopped")


if __name__ == "__main__":
    asyncio.run(main())
