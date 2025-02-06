from aiogram import Bot, Dispatcher, types, executor
from config_test import TOKEN
import logging

# Установите ваш токен здесь
API_TOKEN = TOKEN

# Включаем логирование
# logging.basicConfig(level=logging.INFO)
logging.disable(logging.WARNING)

# Создаем объекты бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Обработчик для всех сообщений
# @dp.message_handler()
# async def maintenance_message(message: types.Message):
#     await message.reply(
#     "⚙️ Бот временно недоступен из-за технического обслуживания. Пожалуйста, попробуйте позже. Спасибо за ваше понимание! 🙏\n\n"
#     "Для новостей и обновлений, следите за нашим [Telegram-каналом](https://t.me/NeuronAgent) 📢"
# )


if __name__ == "__main__":
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
