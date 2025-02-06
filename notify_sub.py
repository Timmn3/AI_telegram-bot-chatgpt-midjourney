import asyncio  # Модуль для работы с асинхронными операциями
import logging  # Логирование
from datetime import timedelta, datetime  # Для работы с датами

import asyncpg  # Асинхронная работа с PostgreSQL
from config import DB_USER, DB_HOST, DB_DATABASE, DB_PASSWORD  # Импорт данных для подключения к базе данных

from create_bot import bot  # Импорт бота для отправки сообщений
from keyboards import user as user_kb  # Импорт пользовательских клавиатур


EXTEND_PRICE = 4  # Переменная для хранения цены продления подписки


# Основная асинхронная функция, которая отправляет уведомления пользователям
async def main():

    # Подключение к базе данных PostgreSQL
    conn = await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE, host=DB_HOST)
    
    # Выборка пользователей, у которых подписка заканчивается в течение 24 часов, и которые еще не получили уведомление
    users = await conn.fetch(
        "SELECT user_id, EXISTS(SELECT sub_order_id FROM sub_orders so WHERE so.user_id = users.user_id and with_discount = TRUE) as use_discount FROM users WHERE users.sub_time between now() and now() + interval '24 hour' and is_notified = false")
    
    # Цикл по каждому пользователю для отправки уведомления
    for user in users:
        # Если пользователь еще не использовал скидку
        if not user["use_discount"]:
            msg = """<b>У вас заканчивается подписка для NeuronAgent</b>

Специально для вас мы подготовили <b>персональную скидку</b>!
Выберите подходящий тариф для продления⤵️

Тариф <b>«Базовый»</b>
1 млн токенов для ChatGPT
10 запросов в Midjourney в день

Тариф <b>«Стандарт»</b>
2 млн токенов для ChatGPT
20 запросов в Midjourney в день

Тариф <b>«Премиум»</b>
5 млн токенов для ChatGPT
40 запросов в Midjourney в день

Тариф <b>«Иллюстратор»</b>
50 тыс токенов для ChatGPT
100 запросов в Midjourney в день

Тариф <b>«Автор»</b>
10 млн токенов для ChatGPT
5 запросов в Midjourney в день"""
        else:
            # Если пользователь уже использовал скидку, отправляется сообщение без скидки
            msg = """<b>У вас заканчивается подписка для NeuronAgent</b>

Выберите подходящий тариф для продления⤵️

Тариф <b>«Базовый»</b>
1 млн токенов для ChatGPT
10 запросов в Midjourney в день

Тариф <b>«Стандарт»</b>
2 млн токенов для ChatGPT
20 запросов в Midjourney в день

Тариф <b>«Премиум»</b>
5 млн токенов для ChatGPT
40 запросов в Midjourney в день

Тариф <b>«Иллюстратор»</b>
50 тыс токенов для ChatGPT
100 запросов в Midjourney в день

Тариф <b>«Автор»</b>
10 млн токенов для ChatGPT
5 запросов в Midjourney в день"""
        
        # Попытка отправить сообщение пользователю
        try:
            await bot.send_message(user["user_id"], msg, reply_markup=user_kb.get_notify_pay(not user["use_discount"]))
            
            # После успешной отправки обновляем статус уведомления
            if user["user_id"] != 796644977:  # Исключаем ID администратора
                await conn.execute("UPDATE users SET is_notified = TRUE where user_id = $1", user["user_id"])
        except:
            pass  # Игнорируем ошибки отправки


    # Закрытие сессии бота
    session = await bot.get_session()
    await session.close()


# Запуск функции при запуске скрипта
if __name__ == '__main__':
    asyncio.run(main())
