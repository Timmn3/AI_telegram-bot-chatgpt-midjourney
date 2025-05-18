from aiogram.utils import executor
from aiogram import types
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import ADMINS_CODER
from create_bot import dp, bot
from utils import db
from utils.ai import mj_api
from handlers import admin, users, sub, users_image_openai # ← Регистрация хэндлеров
import logging

from utils.scheduled_tasks.daily_token_reset import refill_tokens

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')

# Инициализируем планировщик
scheduler = AsyncIOScheduler()


async def on_startup(_):
    """Функция выполняется при запуске бота."""

    await db.start()  # Подключение к БД

    await bot.set_my_commands([
        types.BotCommand("start", "Перезапустить бот"),
        types.BotCommand("chatgpt", "ChatGPT"),
        types.BotCommand("midjourney", "MidJourney"),
        types.BotCommand("image_openai", "Изображения от OpenAI"),
        types.BotCommand("account", "Аккаунт"),
        types.BotCommand("help", "Поддержка"),
        types.BotCommand("partner", "Партнерская программа")
    ])

    await bot.send_message(ADMINS_CODER, "Бот NeuronAgent 🤖 запущен")

    # Настроим и запустим планировщик
    set_scheduled_jobs()

    if not scheduler.running:  # Проверка, не запущен ли уже планировщик
        scheduler.start()


def set_scheduled_jobs():
    """Добавление задач в планировщик"""
    try:
        scheduler.add_job(refill_tokens, "cron", hour=0, minute=0)
    except Exception as e:
        logger.error(f"Error while adding scheduled jobs: {e}")


async def on_shutdown(_):
    """Функция выполняется при завершении работы бота."""
    logger.info("Закрытие сессий API и бота...")

    await mj_api.close()  # Закрываем API-сессии
    await bot.close()

    if scheduler.running:
        scheduler.shutdown(wait=False)  # Останавливаем планировщик

    logger.info("Все сессии закрыты.")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
