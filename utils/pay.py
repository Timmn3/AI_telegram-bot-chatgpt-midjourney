import hashlib  # Для генерации хешей
import hmac     # Для создания HMAC подписи
import json     # Для работы с JSON
import logging
import random   # Для генерации случайных чисел
from datetime import datetime, timedelta  # Для работы с датами
from urllib.parse import urlencode  # Для кодирования URL параметров
import hashlib
import requests
import uuid
import config  # Импорт конфигурации
from config import FreeKassa, LAVA_API_KEY, LAVA_SHOP_ID, PayOK, Tinkoff  # Импорт настроек платежных систем
from utils import db  # Импорт функций работы с базой данных
from utils.db import get_conn
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')




def get_pay_url_tinkoff(order_id, amount):
    # Приводим UUID к строке, если он не строка
    if isinstance(order_id, uuid.UUID):
        order_id = str(order_id)
    # Формирование данных для запроса на оплату через Tinkoff
    data = {
        "TerminalKey": Tinkoff.terminal_id,
        "Amount": amount * 100,
        "CallbackUrl": "https://neuronbot.ru/api/pay/tinkoff/receipt",
        "OrderId": order_id,
        "NotificationURL": "https://91.192.102.250/api/pay/tinkoff",
        "Receipt": {
            "Email": "bills.group@mail.ru",
            "Phone": "+79530983630",
            "Taxation": "patent",
            "Items": [
                {
                    "Name": "Подписка на бот на основе кроссплатформенного мессенджера Telegram NeuronAgent",
                    "Price": amount * 100,
                    "Quantity": 1.0,
                    "Amount": amount * 100,
                    "PaymentMethod": "full_payment",
                    "PaymentObject": "commodity",
                    "Tax": "none"
                }
            ]
        }
    }

    # Строка для подписи
    sign_str = f"{amount * 100}https://91.192.102.250/api/pay/tinkoff{order_id}{Tinkoff.api_token}{Tinkoff.terminal_id}"
    sign = hashlib.sha256(sign_str.encode('utf-8')).hexdigest()

    data["Token"] = sign  # Добавляем подпись в запрос

    # Отправка запроса на инициализацию оплаты
    res = requests.post("https://securepay.tinkoff.ru/v2/Init", json=data)
    res_data = res.json()  # Получение ответа в формате JSON

    # Логируем ответ для отладки
    logger.info(f'Tinkoff Response: {res_data}')

    # Сохраняем payment_id в базу, если он есть
    payment_id = res_data.get("PaymentId")
    if payment_id:
        # Вызов асинхронной функции из sync-кода — через asyncio
        import asyncio
        asyncio.create_task(save_payment_id(order_id, payment_id))

    return res_data["PaymentURL"]


async def save_payment_id(order_id, payment_id):
    conn = await get_conn()
    await conn.execute("UPDATE orders SET payment_id = $1 WHERE order_id = $2", payment_id, order_id)
    await conn.close()

import requests

async def get_receipt_url(payment_id):
    # Отправляем запрос в Tinkoff API для получения чека по payment_id
    data = {
        "TerminalKey": Tinkoff.terminal_id,
        "PaymentId": payment_id,
        "Token": generate_receipt_token(payment_id)  # Нужно создать токен для подписи
    }
    response = requests.post("https://securepay.tinkoff.ru/v2/CheckOrder", json=data)

    if response.status_code == 200:
        result = response.json()
        if result.get("Success"):
            # Если запрос успешен, возвращаем URL чека
            return result.get("ReceiptUrl")  # Это URL на изображение чека
    return None

def generate_receipt_token(payment_id):
    sign_str = f"{payment_id}{Tinkoff.api_token}{Tinkoff.terminal_id}"
    return hashlib.sha256(sign_str.encode('utf-8')).hexdigest()



# Функция для получения ссылки оплаты через PayOK
def get_pay_url_payok(order_id, amount):

    desc = "Пополнение баланса NeuronAgent"  # Описание платежа
    currency = "RUB"  # Валюта
    # Формирование строки для подписи
    sign_string = '|'.join(
        str(item) for item in
        [amount, order_id, PayOK.shop_id, currency, desc, PayOK.secret]
    )
    # Генерация подписи (MD5)
    sign = hashlib.md5(sign_string.encode())

    # Параметры для оплаты
    params = {"amount": amount, "payment": order_id, "shop": PayOK.shop_id, "desc": desc, "currency": currency,
              "sign": sign.hexdigest()}

    # Возвращаем URL для оплаты через PayOK
    return "https://payok.io/pay?" + urlencode(params)


# Функция для получения ссылки оплаты через FreeKassa
def get_pay_url_freekassa(order_id, amount):

    md5 = hashlib.md5()  # Инициализация MD5 хеша
    # Формируем строку для подписи
    md5.update(
        f'{FreeKassa.shop_id}:{amount}:{FreeKassa.secret1}:RUB:{order_id}'.encode('utf-8'))
    pwd = md5.hexdigest()  # Генерация подписи
    # Формируем URL для оплаты через FreeKassa
    pay_url = f"https://pay.freekassa.com/?m={FreeKassa.shop_id}&oa={amount}&currency=RUB&o={order_id}&s={pwd}"
    return pay_url


# Вспомогательная функция для сортировки словаря
def sortDict(data: dict):

    sorted_tuple = sorted(data.items(), key=lambda x: x[0])  # Сортировка по ключам
    return dict(sorted_tuple)


# Функция для получения ссылки оплаты через Lava
def get_pay_url_lava(user_id, amount):

    # Формирование данных для платежа
    payload = {
        "sum": amount,
        "orderId": str(user_id) + ":" + str(random.randint(10000, 1000000)),  # Уникальный идентификатор заказа
        "shopId": LAVA_SHOP_ID
    }

    # Сортировка данных
    payload = sortDict(payload)
    jsonStr = json.dumps(payload).encode()

    # Генерация подписи (HMAC-SHA256)
    sign = hmac.new(bytes(LAVA_API_KEY, 'UTF-8'), jsonStr, hashlib.sha256).hexdigest()
    headers = {"Signature": sign, "Accept": "application/json", "Content-Type": "application/json"}
    
    # Отправляем запрос на создание счета
    res = requests.post("https://api.lava.ru/business/invoice/create", json=payload, headers=headers)
    return res.json()["data"]["url"]  # Возвращаем URL для оплаты


# Функция для обработки успешной оплаты токенов/запросов
async def process_purchase(bot, order_id):
    """
    Обрабатывает успешную оплату заказа.

    ВАЖНО:
    - Тип покупки берём из order["order_type"].
    - Для покупки "gpt14" (доступ к ChatGPT на 14 дней) продлеваем доступ через extend_gpt_access().
    """

    # Получаем информацию о заказе
    order = await db.get_order(order_id)

    # Проверяем, была ли оплата уже обработана
    if order["pay_time"]:
        return

    # Обновляем время оплаты
    await db.set_order_pay(order_id)

    user_id = order["user_id"]  # Получаем ID пользователя
    user = await db.get_user(user_id)  # Получаем информацию о пользователе

    # Тип заказа хранится в order_type
    model = ((order.get("order_type") or "").strip()).replace("-", "_").replace(".", "_")
    amount = order["amount"]  # Заплаченная сумма

    discounts = {189, 315, 412, 628, 949, 1619, 2166, 3199, 227, 386, 509, 757, 550, 246, 989}  # Сумма соответсвующая скидкам
    user_discount = await db.get_user_notified_gpt(user_id)

    logger.info(
        f"Оплата пользователя {user_id} успешно обработана. Тип заказа: {model}, количество: {order['quantity']}"
    )

    # Обновляем токены или запросы в зависимости от типа заказа
    if model == "midjourney":
        new_requests = user["mj"] + order["quantity"]
        await db.update_requests(user_id, new_requests)
        await bot.send_message(user_id, f"✅ Добавлено {order['quantity']} запросов для MidJourney.")

    elif model == "gpt14":
        # ✅ Покупка доступа к ChatGPT на N дней (обычно 14)
        days = int(order["quantity"])
        await db.extend_gpt_access(user_id, days)
        await bot.send_message(user_id, f"✅ Вам добавлено {days} дней доступа к ChatGPT.")

    else:
        new_tokens = int(user[f"tokens_{model}"]) + int(order["quantity"])
        await db.update_tokens(user_id, new_tokens, model)
        await bot.send_message(
            user_id,
            f"✅ Добавлено {int(order['quantity'] / 1000)} тыс. токенов для GPT-{model}.\nБлагодарим за покупку!"
        )

    # Логика скидок / партнёрки (оставляем как было)
    if user_discount is not None and user_discount["used"] != True and amount in discounts:
        logger.info(f'Скидка использована: {user_discount["used"]}, покупка на сумму: {amount}')
        # Если была предложена скидка, пользователь ею не пользовался, но текущий заказ равен скидочной цене - значит убираем возможность скидки.
        await db.update_used_discount_gpt(user_id)

        # 💰 Уведомление о партнерском доходе + +14 дней ChatGPT
        inviter_id = user.get("inviter_id")
        if inviter_id:
            inviter = await db.get_user(inviter_id)
            if inviter and inviter.get("ref_notifications_enabled", True):
                partner_percent = 0.15
                partner_reward = int(amount * partner_percent)

                keyboard = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("Отключить уведомления", callback_data="disable_ref_notifications")
                )

                try:
                    await bot.send_message(
                        inviter_id,
                        f"""📈 У Вас новый реферал
        └ Аккаунт: {user_id}

        ✅ Партнерское вознаграждение
        ├ Аккаунт: {user_id}
        ├ Сумма зачисления: {amount}₽
        ├ Ваш доход: {partner_reward}₽ (15%)
        └ Добавили вам 2 недели ChatGPT бесплатно""",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление о партнерском доходе: {e}")

