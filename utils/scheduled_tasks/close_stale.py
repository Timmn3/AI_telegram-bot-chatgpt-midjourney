from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from create_bot import bot
from utils import db
import logging
from datetime import datetime, timedelta


INACTIVITY_MINUTES = 1440 # для теста, потом 1440 (24 часа)

async def close_stale_chats_job():
    """Закрываем активные чаты, если по пользователю не было активности > INACTIVITY_MINUTES."""
    now = datetime.utcnow()
    users = await db.get_users_with_active_chat()
    for u in users:
        user_id = u["user_id"]
        chat_id = u["current_chat_id"]

        last = await db.get_user_last_activity(user_id)
        if not last:
            continue

        # Проверяем неактивность
        if now - last <= timedelta(minutes=INACTIVITY_MINUTES):
            continue

        chat = await db.get_chat_by_id(chat_id)
        chat_name = chat["name"] if chat and chat.get("name") else "Без названия"


        kb = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("🗂Мои чаты", callback_data="my_chats")
        )

        try:
            await bot.send_message(
                user_id,
                f'Ваш диалог "*{chat_name}*" был закрыт, '
                f'введите новый запрос или откройте предыдущий диалог из списка ⤵️',
                parse_mode="Markdown",
                reply_markup=kb
            )
            logging.info(f"[stale-check] уведомление отправлено пользователю {user_id}")
        except Exception as e:
            logging.warning(f"[stale-check] не удалось отправить сообщение пользователю {user_id}: {e}")

        # Сбрасываем активный чат и режим
        await db.set_current_chat(user_id, None)
        await db.change_default_ai(user_id, "chatgpt")
