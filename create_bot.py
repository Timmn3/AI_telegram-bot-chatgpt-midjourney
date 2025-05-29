from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import BoundFilter
from aiogram.dispatcher import Dispatcher
from aiogram import types
from aiogram import Bot

from config import TOKEN, log_on
from config import ADMINS
from typing import Union

from middlewares.album import AlbumMiddleware
from utils import db
import logging


# Настройка логирования
if log_on:
    # Если логирование включено (log_on=True), то сохраняем логи в файл bot.log
    logging.basicConfig(level=logging.INFO, filename='bot.log', filemode='a',
                        format='%(asctime)s - %(levelname)s - %(message)s')
    log = logging.getLogger("logs")
else:
    # Если логирование выключено, то просто выводим логи в консоль
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    log = logging.getLogger("logs")


# Логирование для библиотеки OpenAI
logger = logging.getLogger('openai')
logger.setLevel(logging.WARNING)  # Уровень логов для OpenAI установлен на предупреждения


# Настройка хранилища состояний
stor = MemoryStorage()  # Хранение данных в памяти, это подойдет для небольших ботов


# Создание экземпляра бота с токеном, заданным в файле config.py
bot = Bot(token=TOKEN, parse_mode="HTML")  # parse_mode позволяет форматировать сообщения в HTML


# Создание диспетчера для управления логикой бота и его состояниями
dp = Dispatcher(bot, storage=stor)


# Фильтр для проверки, является ли пользователь администратором
class IsAdminFilter(BoundFilter):

    key = "is_admin"  # Ключ, по которому фильтр будет доступен в других частях кода

    def __init__(self, is_admin: bool):
        self.global_admin = is_admin  # Устанавливается флаг, проверяем админ пользователь или нет

    async def check(self, obj: Union[types.Message, types.CallbackQuery]):

        # Метод check будет вызываться для каждого сообщения или callback-запроса
        user = obj.from_user
        db_user = await db.get_user(user.id)  # Получаем данные пользователя из базы данных
        if user.id in ADMINS:
            # Если пользователь находится в списке администраторов, он считается админом
            return self.global_admin is True
        if db_user["role"] == "admin":
            # Если роль пользователя в базе данных — администратор
            return self.global_admin is True
        return self.global_admin is False


# Подключение middleware для проверки регистрации и альбомов
# dp.middleware.setup(CheckRegMiddleware())  # Middleware для проверки регистрации
dp.middleware.setup(AlbumMiddleware())  # Middleware для обработки альбомов (групповые сообщения с фото)


# Привязка фильтра для проверки администраторских прав к диспетчеру
dp.filters_factory.bind(IsAdminFilter)
