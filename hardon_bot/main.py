from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from hardon_bot.config import settings
from hardon_bot.database import Database
from hardon_bot.fragment import FragmentDelivery
from hardon_bot.handlers import router


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("Добавьте BOT_TOKEN в .env перед запуском")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(settings.database_path)
    await db.initialize()
    # Messages use Telegram entities directly for custom premium emoji.
    bot = Bot(settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot, db=db, settings=settings, fragment=FragmentDelivery(settings))


if __name__ == "__main__":
    asyncio.run(main())
