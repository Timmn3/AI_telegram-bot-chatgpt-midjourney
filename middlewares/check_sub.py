from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Update, ChatMember
from aiogram.utils.exceptions import ChatNotFound

from keyboards import user as user_kb  # Клавиатура для пользователей
from config import channel_id, ADMINS, check_channel


async def on_pre_process_update(self, update: Update, data: dict):
    # Проверяем, откуда пришло обновление: из сообщения или callback-запроса
    if update.message:
        user_id = update.message.from_user.id  # Получаем ID пользователя из сообщения
    elif update.callback_query:
        user_id = update.callback_query.from_user.id  # Получаем ID пользователя из callback
    else:
        return  # Если это не сообщение и не callback, middleware ничего не делает

    # ✅ Если проверка подписки отключена — не блокируем пользователя
    if not check_channel:
        return

    try:
        # Проверяем, не является ли это командой /start или фото (фото не блокируется подпиской)
        if (update.message.text and '/start' in update.message.text) or update.message.photo:
            return  # Если команда /start или фото — продолжаем выполнение без проверки подписки

    except AttributeError:
        # Если у объекта update нет атрибута text или photo, игнорируем ошибку
        pass

    try:
        # Получаем статус подписки пользователя на канал с ID channel_id
        status: ChatMember = await update.bot.get_chat_member(channel_id, user_id)
        # Если пользователь не подписан (status == "left"), блокируем дальнейшее выполнение
        if status.status == "left":
            if update.callback_query:
                # Если это callback-запрос, сообщаем пользователю, что нужно подписаться
                await update.callback_query.answer("Необходимо вступить в канал")
            else:
                try:
                    # Отправляем сообщение пользователю с просьбой подписаться на канал
                    await update.bot.send_message(
                        user_id,
                        "Для продолжения подпишитесь на наш канал",
                        reply_markup=user_kb.partner
                    )
                except:
                    pass  # Игнорируем ошибки при отправке сообщений

            raise CancelHandler()  # Отменяем обработку обновления (middleware останавливает его)
    except ChatNotFound as e:
        # Если канал не найден (ошибка ChatNotFound), уведомляем администратора
        pass
