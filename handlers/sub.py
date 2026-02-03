import logging
from datetime import datetime, timedelta

from aiogram.dispatcher.filters import Text
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery

import config
import keyboards.user as user_kb  # Клавиатуры для взаимодействия с пользователями (выбор подписки, оплата)
import utils
from config import ADMINS_CODER
from create_bot import dp  # Диспетчер для регистрации хендлеров
from utils import db, pay  # Модули для работы с базой данных и платежными сервисами

vary_types = {"subtle": "Subtle", "strong": "Strong"}  # Типы вариаций для MidJourney

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Функция для получения ссылок на оплату для разных сервисов
def get_pay_urls(order_id, amount):
    return {
        "tinkoff": pay.get_pay_url_tinkoff(order_id, amount),  # Ссылка для оплаты через Tinkoff
        "freekassa": pay.get_pay_url_freekassa(order_id, amount),  # Ссылка для оплаты через FreeKassa
        "payok": pay.get_pay_url_payok(order_id, amount),  # Ссылка для оплаты через PayOK
    }


'''Новые функции выбора покупки токенов - GPT или MJ'''

# Меню для выбора между ChatGPT и MidJourney
@dp.callback_query_handler(text="buy_sub") 
async def choose_neural_network(call: CallbackQuery):
    
    await call.message.edit_text("""
Выберите нейросеть⤵️""", 
    reply_markup=user_kb.get_neural_network_menu())


# # Меню выбора модели для покупки токенов ChatGPT
# @dp.callback_query_handler(text="select_gpt_tokens")
# async def choose_gpt_tokens(call: CallbackQuery):
#
#     user_id = call.from_user.id
#
#     await call.message.edit_text("""
# Выберите модель ChatGPT⤵️""",
#     reply_markup=user_kb.get_chatgpt_models())


# Меню для выбора количества токенов ChatGPT
# @dp.callback_query_handler(Text(startswith="buy_chatgpt_tokens"))
# async def choose_chatgpt_tokens(call: CallbackQuery):
#
#     user_id = call.from_user.id
#     model = call.data.split(":")[1]
#     mode = call.data.split(":")[2]
#
#     logger.info(f"User ID: {user_id}, модель ChatGPT: {model}, скидочное : {mode}")
#
#     # Получаем данные о последнем уведомлении пользователя
#     user_data = await db.get_user_notified_gpt(user_id)
#     now = datetime.now()
#
#     # Проверяем, было ли уведомление отправлено менее 24 часов назад
#     if user_data and user_data['last_notification']:
#         last_notification = user_data['last_notification']
#
#         # Если уведомление было менее 24 часов назад, показываем меню со скидкой
#         if now < last_notification + timedelta(hours=24):
#             await call.message.edit_text('''
# Успейте приобрести токены со <b>скидкой<b>
# предложение актуально </b>24 часа⤵️</b>''',
#                 reply_markup=user_kb.get_chatgpt_tokens_menu('discount', model)
#             )
#             return
#
#     if mode == 'discount':
#         answer = '''
# Успейте приобрести токены со <b>скидкой<b>
# предложение актуально </b>24 часа⤵️</b>'''
#     else:
#         answer = "Выберите количество токенов⤵️"
#
#     await call.message.edit_text(
#         answer,
#         reply_markup=user_kb.get_chatgpt_tokens_menu(mode, model)
#     )


# Меню для выбора количества запросов MidJourney
@dp.callback_query_handler(text="buy_midjourney_requests")
async def choose_midjourney_requests(call: CallbackQuery):
    user_id = call.from_user.id
    
    # Получаем данные о последнем уведомлении пользователя
    user_data = await db.get_user_notified_mj(user_id)
    now = datetime.now()

    # Проверяем, было ли уведомление отправлено менее 24 часов назад
    if user_data and user_data['last_notification']:
        last_notification = user_data['last_notification']
        
        # Если уведомление было менее 24 часов назад, показываем меню со скидкой
        if now < last_notification + timedelta(hours=24):
            await call.message.edit_text(
                "Выберите количество запросов со скидкой⤵️",
                reply_markup=user_kb.get_midjourney_discount_requests_menu()
            )

    await call.message.edit_text("""
Выберите количество запросов⤵️""",
    reply_markup=user_kb.get_midjourney_requests_menu())


# Реагирование на нажатие кнопки с выбором количества токенов для GPT
@dp.callback_query_handler(Text(startswith="tokens:"))
async def handle_chatgpt_tokens_purchase(call: CallbackQuery):

    user_id = call.from_user.id
    logger.info(f"User ID: {user_id} выбирает количество токенов ChatGPT: {call.data}") 

    tokens = int(call.data.split(":")[1])  # Получаем количество токенов
    model = str(call.data.split(":")[2])  # Получаем модель СhatGPT
    amount = int(call.data.split(":")[3])  # Получаем цену за количество токенов
    src = str(call.data.split(":")[4])  # Источник сообщения - из уведомления или аккаунта

    logger.info(f"Разобранный callback: {tokens}, {model}, {amount}, {src}")
    
    discounts = {189, 315, 412, 628, 949, 1619, 2166, 3199, 227, 386, 509, 757}
    user_discount = await db.get_user_notified_gpt(user_id)

    if user_discount is None or (user_discount['used'] != True or (user_discount['used'] == True and amount not in discounts)):
        
        if amount in discounts:  # Покупка со скидкой. ПО ХОРОШЕМУ, ДОЛЖНА СРАБАТЫВАТЬ ПОСЛЕ ОПЛАТЫ...
            await db.update_used_discount_gpt(user_id)

        # Создаем заказ для покупки токенов в базе данных
        order_id = await db.add_order(call.from_user.id, amount, model, tokens)

        # Генерируем ссылки для оплаты
        urls = get_pay_urls(order_id, amount)
    
        # Отправляем пользователю сообщение с выбором способа оплаты
        await call.message.edit_text(f"✅{int(tokens / 1000)} тыс. токенов для GPT-{model}\n💰Сумма: {amount}₽.",
                                     reply_markup=user_kb.get_pay_urls(urls, order_id, model, src))
    
    else:
        await call.message.edit_text("Вы уже использовали скидку")

# Реагирование на нажатие кнопки с выбором количества запросов для Midjourney
@dp.callback_query_handler(Text(startswith="select_midjourney_requests:"))
async def handle_midjourney_requests_purchase(call: CallbackQuery):

    user_id = call.from_user.id
    requests_count = int(call.data.split(":")[1])  # Получаем количество запросов
    amount = int(call.data.split(":")[2])  # Получаем цену за количество запросов
    src = str(call.data.split(":")[3])  # Источник сообщения - из уведомления или аккаунта
    discounts = {246, 550, 989}
    user_discount = await db.get_user_notified_mj(user_id)

    if user_discount is None or (user_discount['used'] != True or (user_discount['used'] == True and amount not in discounts)):
        
        if amount in discounts:  # Покупка со скидкой
            await db.update_used_discount_mj(user_id)
        model = "midjourney"
        # Создаем заказ для покупки запросов в базе данных
        order_id = await db.add_order(call.from_user.id, amount, model, requests_count)

        # Генерируем ссылки для оплаты
        urls = get_pay_urls(order_id, amount)

        # Отправляем пользователю сообщение с выбором способа оплаты
        await call.message.edit_text(f"✅{requests_count} запросов для 🎨MidJourney\n💰Сумма: {amount}₽.",
                                     reply_markup=user_kb.get_pay_urls(urls, order_id, model, src))
    else:
        await call.message.edit_text("Вы уже использовали скидку")


# Уведомение о низком количестве токенов GPT
# @dp.callback_query_handler(text="back_to_discount")
# async def back_to_discount_notification(call: CallbackQuery):
#
#     logger.info('back_to_discount')
#
#     await call.message.edit_text("""
# У вас заканчиваются запросы для 💬ChatGPT
# Специально для вас мы подготовили <b>персональную скидку</b>!
# Выберите интересующую Вас модель⤵️
#     """, reply_markup=user_kb.get_chatgpt_models_noback('discount'))
#     await call.answer()


# Хендлер для оплаты через Telegram (проплаченный функционал)
@dp.callback_query_handler(Text(startswith="tg_stars:"))
async def back_to_buy_vpn(call: CallbackQuery):

    order_id = call.data.split(":")[1]  # Теперь order_id остаётся строкой
    order = await db.get_order(order_id)  # Убедитесь, что get_order принимает строку
    user_id = call.from_user.id
    amount = order["amount"]  # Сумма в рублях

    await db.add_star(user_id, amount, order_id)
    # Отправляем пользователю инвойс для оплаты через Telegram
    await call.bot.send_invoice(call.from_user.id,
                                title="Приобретение подписки",
                                description=f"""💰 Сумма: {order['amount']} рублей

♻️ Средства зачислятся автоматически""",
                                provider_token="",  # Токен для оплаты (платежный провайдер)
                                payload=f"{order_id}",  # ID заказа
                                currency="XTR",  # Валюта оплаты
                                prices=[LabeledPrice(label="Подписка", amount=order["amount"] // 2)],  # Цена подписки order["amount"] // 2
                                reply_markup=user_kb.get_tg_stars_pay()  # Кнопка оплаты
                                )
    await call.answer()


# Хендлер для подтверждения оплаты через Telegram
@dp.pre_checkout_query_handler()
async def approve_order(pre_checkout_query: PreCheckoutQuery):

    # Подтверждаем заказ (оплата успешна)
    await pre_checkout_query.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# Хендлер для обработки успешной оплаты
@dp.message_handler(content_types="successful_payment")
async def process_successful_payment(message: Message):
    order_id = message.successful_payment.invoice_payload  # Получаем ID заказа из payload
    await utils.pay.process_purchase(message.bot, order_id)  # Обрабатываем подписку (обновляем в базе)
    # Сохраняем данные о звездах в таблицу stars
    await db.mark_star_paid(order_id)


# Хэндлдер для возврата ссылки на оплату Tinkoff:
@dp.callback_query_handler(Text(startswith="open_url"))
async def open_url(call: CallbackQuery):
    
    splitted = call.data.split(":")
    url = str(splitted[1] + ":" + splitted[2])

    await call.bot.send_message(call.from_user.id, f'Ваша ссылка на оплату:\n{url}\n\nСкопируйте и откройте в стороннем браузере\n\
Не открывайте через Telegram-браузер')

    await call.answer()


# Обработчик для покупки доступа к ChatGPT на 14 дней
@dp.callback_query_handler(text="buy_chatgpt_14days")
async def handle_chatgpt_14days_purchase(call: CallbackQuery):
    user_id = call.from_user.id
    amount = 199
    days = 14
    model = "gpt14"

    # Создаем заказ
    order_id = await db.add_order(user_id, amount, model, days)

    # Генерируем ссылки для оплаты
    urls = get_pay_urls(order_id, amount)

    # Отправляем сообщение с выбором способа оплаты
    await call.message.edit_text(
        f"✅14 дней для ChatGPT\n💰Сумма: {amount}₽.",
        reply_markup=user_kb.get_pay_urls(urls, order_id, model, src='acc')
    )