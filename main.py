from aiogram.utils import executor
from aiogram import types
from create_bot import dp, bot
from utils import db
from utils.ai import mj_api
from handlers import admin
from handlers import users
from handlers import sub
import logging

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.CRITICAL,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')

logging.disable(logging.WARNING)

async def on_startup(_):
    # Функция, которая выполняется при запуске бота.
    # Здесь вызывается метод start() из модуля db, который инициирует подключение к базе данных.
    await db.start()
    await bot.set_my_commands([
        types.BotCommand("start", "Перезапустить бот"),
        types.BotCommand("midjourney", "MidJourney"),
        types.BotCommand("chatgpt", "ChatGPT"),
        types.BotCommand("account", "Аккаунт"),
        types.BotCommand("help", "Поддержка"),
        types.BotCommand("partner", "Партнерская программа")
    ])


async def on_shutdown(dispatcher: dp):
    logger.info("Закрытие сессий API и бота...")
    await mj_api.close()  # Закрываем сессии GoAPI и ApiFrame
    await bot.close()
    logger.info("Все сессии закрыты.")


if __name__ == "__main__":
    # Если файл запускается как основной (а не импортируется как модуль),
    # бот начинает получать и обрабатывать обновления (сообщения, команды и т.д.)
    # dp - диспетчер из create_bot, который обрабатывает входящие сообщения
    # skip_updates=True - игнорирует старые обновления, накопившиеся до запуска бота
    # on_startup=on_startup - запускает функцию при старте
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)

