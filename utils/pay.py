import hashlib  # Для генерации хешей
import hmac     # Для создания HMAC подписи
import json     # Для работы с JSON
import logging
import random   # Для генерации случайных чисел
from datetime import datetime, timedelta  # Для работы с датами
from urllib.parse import urlencode  # Для кодирования URL параметров

import requests  # Для выполнения HTTP-запросов

import config  # Импорт конфигурации
from config import FreeKassa, LAVA_API_KEY, LAVA_SHOP_ID, PayOK, Tinkoff  # Импорт настроек платежных систем
from utils import db  # Импорт функций работы с базой данных


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Функция для получения ссылки оплаты через Tinkoff
def get_pay_url_tinkoff(order_id, amount):

    # Формирование данных для запроса на оплату через Tinkoff
    data = {
        "TerminalKey": Tinkoff.terminal_id,
        "Amount": amount * 100,  # Сумма в копейках
        "OrderId": order_id,  # Идентификатор заказа
        "NotificationURL": "http://91.192.102.250/api/pay/tinkoff"  # URL для уведомлений о статусе оплаты
    }
    # Строка для подписи
    sing_str = f"{amount * 100}http://91.192.102.250/api/pay/tinkoff{order_id}{Tinkoff.api_token}{Tinkoff.terminal_id}"
    # Генерация подписи (SHA256)
    sign = hashlib.sha256(sing_str.encode('utf-8')).hexdigest()

    data["Token"] = sign  # Добавляем подпись в запрос

    # Отправка запроса на инициализацию оплаты
    res = requests.post("https://securepay.tinkoff.ru/v2/Init", json=data)
    logger.info(f'Tinkoff Response: {res.json()}')
    res_data = res.json()  # Получение ответа в формате JSON
    return res_data["PaymentURL"]  # Возвращаем URL для оплаты


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
    
    # Получаем информацию о заказе
    order = await db.get_order(order_id)

    # Проверяем, была ли оплата уже обработана
    if order["pay_time"]:
        return

    # Обновляем время оплаты
    await db.set_order_pay(order_id)

    user_id = order["user_id"]  # Получаем ID пользователя
    user = await db.get_user(user_id)  # Получаем информацию о пользователе
    user_discount = await db.get_user_notified_gpt(user_id)  # Была ли скидка?
    model = (order["order_type"]).replace('-', '_')
    amount = order["amount"]  # Заплаченная сумма
    discounts = {189, 315, 412, 628, 949, 1619, 2166, 3199, 227, 386, 509, 757, 550, 246, 989} # Сумма соответсвующая скидкам
    user_discount = await db.get_user_notified_gpt(user_id)

    logger.info(f"Оплата пользователя {user_id} успешно обработана. Тип заказа: {model}, количество: {order['quantity']}")

    # Начисление бонусных токенов 4o-mini
    bonus = 20000 if int(order["quantity"]) == 100000 else int((order["quantity"]) / 4) 
    total_bonus = user["tokens_4o_mini"] + bonus

    # Обновляем токены или запросы в зависимости от типа заказа
    if model in {'4o', 'o1_preview', 'o1_mini'}:
        new_tokens = int(user[f"tokens_{model}"]) + int(order["quantity"])
        await db.update_tokens(user_id, new_tokens, model)
        await db.update_tokens(user_id, total_bonus, "4o_mini")
        await bot.send_message(user_id, f"✅Добавлено {int(order['quantity'] / 1000)} тыс. токенов для GPT-{model}.\nБлагодарим за покупку!\nВ качестве бонуса 🎁 дарим Вам {int(bonus / 1000)} тыс. токенов GPT-4o-mini")
    elif order["order_type"] == "midjourney":
        new_requests = user["mj"] + order["quantity"]
        await db.update_requests(user_id, new_requests)
        await bot.send_message(user_id, f"✅Добавлено {order['quantity']} запросов для MidJourney.")

    if user_discount is not None and user_discount["used"] != True and amount in discounts:
        logger.info(f'Скидка использована: {user_discount["used"]}, покупка на сумму: {amount}')
        # Если была предложена скидка, пользователь ею не пользовался, но текущий заказ равен скидочной цене - значит убираем возможность скидки. 
        await db.update_used_discount_gpt(user_id)  
 