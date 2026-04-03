"""
Entry point for the Avito Telegram notification bot.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
import avito_poller as poller
from config import BOT_TOKEN
from handlers import accounts, members, commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    await db.init_db()

    bot = Bot(token=BOT_TOKEN)
    poller.set_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(commands.router)
    dp.include_router(members.router)
    dp.include_router(accounts.router)

    # Start polling loop as a background task
    poll_task = asyncio.create_task(poller.polling_loop())

    log.info("Bot started.")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        poll_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
