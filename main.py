from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher

from app.bot import create_bot, create_dispatcher
from app.config import load_settings
from app.db import Database
from app.handlers.admin import router as admin_router
from app.handlers.user import router as user_router
from app.models_logic import Repository
from app.scheduler import BroadcastScheduler


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def main() -> None:
    setup_logging()
    settings = load_settings()

    db = Database(settings.database_path)
    await db.init()

    repository = Repository(db=db, tzinfo=settings.tzinfo)
    bot = create_bot(settings.bot_token)
    dp: Dispatcher = create_dispatcher()

    broadcast_scheduler = BroadcastScheduler(repository, bot, settings.tzinfo)
    broadcast_scheduler.start()
    await broadcast_scheduler.restore_jobs()

    dp["repository"] = repository
    dp["admin_telegram_id"] = settings.admin_telegram_id
    dp["tzinfo"] = settings.tzinfo
    dp["broadcast_scheduler"] = broadcast_scheduler

    dp.include_router(user_router)
    dp.include_router(admin_router)

    try:
        await dp.start_polling(bot)
    finally:
        await broadcast_scheduler.shutdown()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
