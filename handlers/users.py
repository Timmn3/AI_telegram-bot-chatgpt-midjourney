import logging
from datetime import datetime, timedelta
from typing import List

import requests
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ChatActions, ContentType, MediaGroup, Update
from aiogram.types.input_file import InputFile
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext

import matplotlib.pyplot as plt
import io
import re
import tempfile
import os
import config
from utils import db, ai, more_api, pay # Импорт утилит для взаимодействия с БД и внешними API
from states import user as states  # Состояния FSM для пользователя
import keyboards.user as user_kb  # Клавиатуры для взаимодействия с пользователями
from config import bot_url, TOKEN, NOTIFY_URL, bug_id, PHOTO_PATH, MJ_PHOTO_BASE_URL, ADMINS_CODER
from create_bot import dp  # Диспетчер из create_bot.py
from utils.ai import mj_api, text_to_speech, voice_to_text


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')

vary_types = {"subtle": "Subtle", "strong": "Strong"}  # Типы для использования в дальнейшем

'''
# Проверка и активация промокодов
async def check_promocode(user_id, code, bot: Bot):

    promocode = await db.get_promocode_by_code(code)  # Получаем промокод по коду
    if promocode is None:
        return
    # Проверяем, использовал ли пользователь этот промокод ранее
    user_promocode = await db.get_user_promocode_by_promocode_id_and_user_id(promocode["promocode_id"], user_id)
    all_user_promocode = await db.get_all_user_promocode_by_promocode_id(promocode["promocode_id"])
    
    # Если пользователь не использовал промокод и есть свободные активации, применяем его
    if user_promocode is None and len(all_user_promocode) < promocode["uses_count"]:
        await db.create_user_promocode(promocode["promocode_id"], user_id)
        await db.add_balance(user_id, promocode['amount'], is_promo=True)  # Пополняем баланс на сумму промокода
        await bot.send_message(user_id, f"<b>Баланс пополнен на {promocode['amount']} рублей.</b>")
    else:
        # Уведомление, если промокод уже использован или исчерпаны активации
        if user_promocode is not None:
            await bot.send_message(user_id, "<b>Данная ссылка была активирована Вами ранее.</b>")
        elif len(all_user_promocode) >= promocode["uses_count"]:
            await bot.send_message(user_id, "<b>Ссылка исчерпала максимальное количество активаций.</b>")
'''


# Снижение баланса пользователя
async def remove_balance(bot: Bot, user_id):

    await db.remove_balance(user_id)
    user = await db.get_user(user_id)
    # Если баланс меньше 50, отправляем уведомление о необходимости пополнения
    if user["balance"] <= 50:
        await db.update_stock_time(user_id, int(datetime.now().timestamp()))
        await bot.send_message(user_id, """⚠️Заканчивается баланс!
Успей пополнить в течении 24 часов и получи на счёт +10% от суммы пополнения ⤵️""", 
                               reply_markup=user_kb.get_pay(user_id, 10))  # Кнопка пополнения баланса


# Функция для уведомления пользователя о недостатке средств
async def not_enough_balance(bot: Bot, user_id: int, ai_type: str):

    now = datetime.now()

    if ai_type == "chatgpt":
        user = await db.get_user(user_id)
        model = user["gpt_model"]

        logger.info(f"Токены для ChatGPT закончились. User: {user}, Model: {model}")

        model_map = {'4o-mini': 'ChatGPT',
                     '4o': 'GPT-4o',
                     'o1-preview': 'GPT-o1-preview',
                     'o1-mini': 'GPT-o1-mini'}

        user_data = await db.get_user_notified_gpt(user_id)

        if model == '4o-mini':
            keyboard=user_kb.get_chatgpt_models_noback()
        else:
            keyboard=user_kb.get_chatgpt_tokens_menu('normal', model)

        await bot.send_message(user_id, f"⚠️Токены для {model_map[model]} закончились!\n\nВыберите интересующий вас вариант⤵️", 
            reply_markup=keyboard)  # Отправляем уведомление с клавиатурой для пополнения токенов

    elif ai_type == "image":
        user_data = await db.get_user_notified_mj(user_id)

        if user_data and user_data['last_notification']:
            last_notification = user_data['last_notification']

            # Если уведомление было менее 24 часов назад, показываем меню со скидкой
            if now < last_notification + timedelta(hours=24):
                await bot.send_message(user_id, """
⚠️Запросы для Midjourney закончились!

Выберите интересующий вас вариант⤵️
                """,
                    reply_markup=user_kb.get_midjourney_discount_requests_menu()
                )
                return
        await bot.send_message(user_id, """
⚠️Запросы для Midjourney закончились!

Выберите интересующий вас вариант⤵️
        """, reply_markup=user_kb.get_midjourney_requests_menu())  # Отправляем уведомление с клавиатурой для пополнения запросов


# Генерация изображения через MidJourney
async def get_mj(prompt, user_id, bot: Bot):

    user = await db.get_user(user_id)

    # Проверяем наличие запросов и отправляем уведомление, если запросы исчерпаны
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(bot, user_id, "image")  # Отправляем уведомление о недостатке средств
        return

    await bot.send_message(user_id, "Ожидайте, генерирую изображение..🕙", reply_markup=user_kb.get_menu(user["default_ai"]))
    await bot.send_chat_action(user_id, ChatActions.UPLOAD_PHOTO)

    if '—' in prompt:
        prompt.replace('—', '--')

    res = await ai.get_mdjrny(prompt, user_id)  # Получаем изображение через API

    logger.info(f"MidJourney: {res}")

    if res is None:
        await bot.send_message(user_id, f"Произошла ошибка, повторите попытку позже")
        return
    elif ('Banned Prompt' in res):
        await bot.send_message(user_id, f"Запрещенное слово в запросе:\n\n{res}")
        return
    elif ('Invalid image prompt position' in res):
        await bot.send_message(user_id, f"Некорректная структура запроса:\n\n{res}")
        return
    elif ('status' in res) and (res['status'] == "failed"):
        await bot.send_message(user_id, f"Произошла ошибка, подробности ошибки:\n\n{res['message']}")
        return

    # Проверка на количество оставшихся запросов MidJourney
    now = datetime.now()
    user_notified = await db.get_user_notified_mj(user_id)
    user = await db.get_user(user_id)  # Получаем обновленные данные пользователя
    
    if 1 < user["mj"] <= 3:  # Если осталось 3 или меньше запросов
        if user_notified is None:
            await db.create_user_notification_mj(user_id)
            await notify_low_midjourney_requests(user_id, bot)  # Отправляем уведомление о низком количестве токенов
            # await db.set_user_notified(user_id)  # Помечаем, что уведомление отправлено
        else:
            last_notification = user_notified['last_notification']
            if last_notification is None or now > last_notification + timedelta(days=30):
                await db.update_user_notification_mj(user_id)
                await notify_low_midjourney_requests(user_id, bot)


def split_message(text: str, max_length: int) -> list:
    """Разбивает длинное сообщение на части, не превышающие max_length."""
    lines = text.split('\n')
    parts = []
    current_part = ""

    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            parts.append(current_part)
            current_part = ""
        current_part += line + '\n'

    if current_part:
        parts.append(current_part)

    return parts


def formatter(text):

    escape_chars = r'[]()~>#+-=|{}.!'
    text = ''.join(['\\' + char if char in escape_chars else char for char in text])

    text = text.replace("**", "*")
    
    return text


# Генерация ответа от ChatGPT
async def get_gpt(prompt, messages, user_id, bot: Bot, state: FSMContext):

    user = await db.get_user(user_id)
    lang_text = {"en": "compose an answer in English", "ru": "составь ответ на русском языке"}
    prompt += f"\n{lang_text[user['chat_gpt_lang']]}"
    model = user['gpt_model']
    model_dashed = model.replace("-", "_")
    messages.append({"role": "user", "content": prompt})

    logger.info(f"Текстовый запрос к ChatGPT. User: {user}, Model: {model}, tokens: {user[f'tokens_{model_dashed}']}")

    await bot.send_chat_action(user_id, ChatActions.TYPING)

    res = await ai.get_gpt(messages, model)  # Отправляем запрос в ChatGPTs

    if len(res["content"]) <= 4096:
        await bot.send_message(user_id, formatter(res["content"]), reply_markup=user_kb.get_clear_or_audio(), parse_mode="MarkdownV2")
    else:
        # Разделение сообщения на части
        parts = split_message(formatter(res["content"]), 4096)
        for part in parts:
            await bot.send_message(user_id, part, reply_markup=user_kb.get_clear_or_audio(), parse_mode="MarkdownV2")

    await state.update_data(content=res["content"])

    if not res["status"]:
        return
    messages.append({"role": "assistant", "content": res["content"]})

    # Списывание токенов    
    await db.remove_chatgpt(user_id, res["tokens"], model)  # Уменьшаем токены

    # Проверка на количество оставшихся токенов
    now = datetime.now()
    user_notified = await db.get_user_notified_gpt(user_id)
    user = await db.get_user(user_id)  # Получаем обновленные данные пользователя
    has_purchase = await db.has_matching_orders(user_id)
    
    if user[f"tokens_{model_dashed}"] <= 3000 and model_dashed != "4o_mini":  # Если осталось 3 тыс или меньше токенов

        logger.info(f"Осталось {user[f'tokens_{model_dashed}']} токенов, было уведомление: {user_notified}, совершал ли покупку: {has_purchase}")

        if user_notified is None and has_purchase is True:
            logger.info(f'Скидочное уведомление')
            await db.create_user_notification_gpt(user_id)
            await notify_low_chatgpt_tokens(user_id, bot)  # Отправляем уведомление о низком количестве токенов
            # await db.set_user_notified(user_id)  # Помечаем, что уведомление отправлено
        else:
            last_notification = user_notified['last_notification'] if user_notified is not None else None
            if (last_notification is None or now > last_notification + timedelta(days=30)) and has_purchase is True:
                await db.update_user_notification_gpt(user_id)
                await notify_low_chatgpt_tokens(user_id, bot)

    await db.add_action(user_id, model)  # Логируем действие пользователя
    return messages


''' Новые две функции - уведомления об заканчивающихся токенах '''

# Уведомение о низком количестве токенов GPT
async def notify_low_chatgpt_tokens(user_id, bot: Bot):

    logger.info('Внутри скидочного уведомления - выбираем модель')

    await bot.send_message(user_id, """
У вас заканчиваются запросы для 💬ChatGPT
Специально для вас мы подготовили <b>персональную скидку</b>!
Выберите интересующую Вас модель⤵️
    """, reply_markup=user_kb.get_chatgpt_models_noback('discount'))


# Уведомление о низком количестве запросов MidJourney
async def notify_low_midjourney_requests(user_id, bot: Bot):

    await bot.send_message(user_id, """
У вас заканчиваются запросы для 🎨Midjourney
Специально для вас мы подготовили <b>персональную скидку</b>!

Успейте приобрести запросы со скидкой, предложение актуально <b>24 часа</b>⤵️
    """, reply_markup=user_kb.get_midjourney_discount_notification())


@dp.errors_handler()
async def log_all_updates(update: Update, exception: Exception = None):
    logging.debug(f"Update received: {update.to_python()}")
    if exception:
        logging.error(f"Exception: {exception}")
    return True

'''
@dp.callback_query_handler()
async def all_callback_handler(call: CallbackQuery):
    logging.info(f"Received callback_data: {call.data}")
    await call.message.answer("Callback received")
'''

# Хэндлер команды /start
@dp.message_handler(state="*", commands='start')
async def start_message(message: Message, state: FSMContext):

    await state.finish()  # Завершаем любое текущее состояние

    # Обрабатываем параметры команды /start (например, реферальные коды)
    msg_args = message.get_args().split("_")
    inviter_id = 0
    code = None
    if msg_args != ['']:
        for msg_arg in msg_args:
            if msg_arg[0] == "r":
                try:
                    inviter_id = int(msg_arg[1:])
                except ValueError:
                    continue
            elif msg_arg[0] == "p":
                code = msg_arg[1:]

    user = await db.get_user(message.from_user.id)

    if user is None:
        await db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, int(inviter_id))
        default_ai = "chatgpt"
    else:
        default_ai = user["default_ai"]

    # Отправляем приветственное сообщение
    await message.answer("""<b>NeuronAgent</b>🤖 - <i>2 нейросети в одном месте!</i>
<b>ChatGPT или Midjourney?</b>""", reply_markup=user_kb.get_menu(default_ai))

    # Проверка промокода, если он был передан
    if code is not None:
        await check_promocode(message.from_user.id, code, message.bot)


# Хендлер настроек ChatGPT
@dp.callback_query_handler(text="settings")
async def settings(call: CallbackQuery):

    user = await db.get_user(call.from_user.id)
    user_lang = user["chat_gpt_lang"]

    await call.message.answer("""Здесь Вы можете изменить настройки 
ChatGPT⤵️""", reply_markup=user_kb.settings(user_lang, 'acc'))
    await call.answer()


# Хендлер для проверки подписки через callback-запрос
@dp.callback_query_handler(text="check_sub")
async def check_sub(call: CallbackQuery):

    user = await db.get_user(call.from_user.id)  # Получаем данные пользователя из базы
    if user is None:
        # Если пользователь новый, создаем запись
        await db.add_user(call.from_user.id, call.from_user.username, call.from_user.first_name, 0)
    await call.message.answer("""<b>NeuronAgent</b>🤖 - <i>2 нейросети в одном месте!</i>

<b>ChatGPT или Midjourney?</b>""", reply_markup=user_kb.get_menu(user["default_ai"]))  # Меню выбора AI
    await call.answer()


# Хендлер для удаления сообщения через callback-запрос
@dp.callback_query_handler(text="delete_msg")
async def delete_msg(call: CallbackQuery, state: FSMContext):

    await call.message.delete()  # Удаляем сообщение


# Хендлер для возврата к главному меню через callback-запрос
@dp.callback_query_handler(text="back_to_menu")
async def back_to_menu(call: CallbackQuery):

    user = await db.get_user(call.from_user.id)  # Получаем данные пользователя
    await call.message.answer("""NeuronAgent🤖 - 2 нейросети в одном месте!

ChatGPT или Midjourney?""", reply_markup=user_kb.get_menu(user["default_ai"]))  # Меню выбора AI
    await call.message.delete()  # Удаляем предыдущее сообщение

# Хендлер для партнерской программы
@dp.message_handler(state="*", text="🤝Партнерская программа")
@dp.message_handler(commands='partner')
async def ref_menu(message: Message):

    ref_data = await db.get_ref_stat(message.from_user.id)  # Получаем данные по рефералам
    if ref_data['all_income'] is None:
        all_income = 0
    else:
        all_income = ref_data['all_income']
    
    # Отправляем пользователю QR-код и информацию о партнерской программе
    await message.answer_photo(more_api.get_qr_photo(bot_url + '?start=' + str(message.from_user.id)),
                               caption=f'''<b>🤝 Партнёрская программа</b>

<i>Приводи друзей и зарабатывай 15% с их пополнений, пожизненно!</i>

<b>⬇️ Твоя реферальная ссылка:</b>
└ {bot_url}?start=r{message.from_user.id}

<b>🏅 Статистика:</b>
├ Лично приглашённых: <b>{ref_data["count_refs"]}</b>
├ Количество оплат: <b>{ref_data["orders_count"]}</b>
├ Всего заработано: <b>{int(all_income * 0.15)}</b> рублей
└ Доступно к выводу: <b>{ref_data["available_for_withdrawal"]}</b> рублей

Ваша реферальная ссылка: ''',
                               reply_markup=user_kb.get_ref_menu(f'{bot_url}?start=r{message.from_user.id}'))

# Хендлер для показа профиля пользователя (страница аккаунта)
@dp.message_handler(state="*", text="⚙Аккаунт")
@dp.message_handler(state="*", commands="account")
async def show_profile(message: Message, state: FSMContext):

    await state.finish()
    user_id = message.from_user.id
    user = await db.get_user(user_id)  # Получаем данные пользователя
    user_lang = user['chat_gpt_lang']

    mj = int(user['mj']) + int(user['free_image']) if int(user['mj']) + int(user['free_image']) >= 0 else 0
    gpt_4o_mini = int(user['tokens_4o_mini']) if int(user['tokens_4o_mini']) >= 0 else 0
    gpt_4o = int(user['tokens_4o']) if int(user['tokens_4o']) >= 0 else 0
    gpt_o1_preview = int(user['tokens_o1_preview']) if int(user['tokens_o1_preview']) >= 0 else 0
    gpt_o1_mini = int(user['tokens_o1_mini']) if int(user['tokens_o1_mini']) >= 0 else 0

    logger.info(f"Колиество токенов и запросов для {user_id}:mj: {mj}, gpt_4o: {gpt_4o}, gpt_4o_mini: {gpt_4o_mini}, gpt_o1_preview: {gpt_o1_preview}, gpt_o1_mini: {gpt_o1_mini}")

    # Формируем текст с количеством доступных генераций и токенов
    sub_text = f"""
Вам доступно⤵️

Генерации 🎨Midjourney:  {format(mj, ',').replace(',', ' ')}
Токены 💬GPT-4o:  {format(gpt_4o, ',').replace(',', ' ')}
Токены 💬GPT-4o-mini:  {format(gpt_4o_mini, ',').replace(',', ' ')}
Токены 💬GPT-o1-preview:  {format(gpt_o1_preview, ',').replace(',', ' ')}
Токены 💬GPT-o1-mini:  {format(gpt_o1_mini, ',').replace(',', ' ')}
        """
    
    # Отправляем сообщение с обновленными данными аккаунта
    await message.answer(f"""🆔: <code>{user_id}</code>
{sub_text}""", reply_markup=user_kb.get_account(user_lang, "account"))



# Хендлер для возврата к профилю пользователя через callback-запрос
@dp.callback_query_handler(Text(startswith="back_to_profile"), state="*")
async def back_to_profile(call: CallbackQuery, state: FSMContext):

    logger.info(f"Back To Profile {call.data}")

    src = call.data.split(":")[1]

    if src == "acc":
        await state.finish()
        user_id = call.from_user.id
        user = await db.get_user(user_id)  # Получаем данные пользователя
        user_lang = user['chat_gpt_lang']

        # Формируем текст с количеством доступных генераций и токенов
        mj = int(user['mj']) + int(user['free_image']) if int(user['mj']) + int(user['free_image']) >= 0 else 0
        gpt_4o_mini = int(user['tokens_4o_mini']) if int(user['tokens_4o_mini']) >= 0 else 0
        gpt_4o = int(user['tokens_4o']) if int(user['tokens_4o']) >= 0 else 0
        gpt_o1_preview = int(user['tokens_o1_preview']) if int(user['tokens_o1_preview']) >= 0 else 0
        gpt_o1_mini = int(user['tokens_o1_mini']) if int(user['tokens_o1_mini']) >= 0 else 0

        logger.info(f"Колиество токенов и запросов для {user_id}:mj: {mj}, gpt_4o: {gpt_4o}, gpt_4o_mini: {gpt_4o_mini}, gpt_o1_preview: {gpt_o1_preview}, gpt_o1_mini: {gpt_o1_mini}")

        keyboard = user_kb.get_account(user_lang, "account")

        # Формируем текст с количеством доступных генераций и токенов
        sub_text = f"""
Вам доступно⤵️

Генерации 🎨Midjourney:  {format(mj, ',').replace(',', ' ')}
Токены 💬GPT-4o:  {format(gpt_4o, ',').replace(',', ' ')}
Токены 💬GPT-4o-mini:  {format(gpt_4o_mini, ',').replace(',', ' ')}
Токены 💬GPT-o1-preview:  {format(gpt_o1_preview, ',').replace(',', ' ')}
Токены 💬GPT-o1-mini:  {format(gpt_o1_mini, ',').replace(',', ' ')}
            """
        
        # Отправляем сообщение с обновленными данными аккаунта
        await call.message.answer(f"""🆔: <code>{user_id}</code>
    {sub_text}""", reply_markup=keyboard)

    else:
        await state.finish()

        if src == "not_gpt":
        
            await call.message.edit_text("""
У вас заканчиваются токены для 💬ChatGPT
Специально для вас мы подготовили <b>персональную скидку</b>!

Успейте приобрести токены со скидкой, предложение актуально <b>24 часа</b>⤵️
            """, reply_markup=user_kb.get_chatgpt_tokens_menu('disount', user["gpt_model"]))

        if src == "not_mj":
            await call.message.edit_text("""
У вас заканчиваются запросы для 🎨Midjourney
Специально для вас мы подготовили <b>персональную скидку</b>!

Успейте приобрести запросы со скидкой, предложение актуально <b>24 часа</b>⤵️
            """, reply_markup=user_kb.get_midjourney_discount_notification())

    await call.answer()
    

# Хендлер для смены языка через callback-запрос
@dp.callback_query_handler(Text(startswith="change_lang:"))
async def change_lang(call: CallbackQuery):

    curr_lang = call.data.split(":")[1]  # Текущий язык
    from_msg = call.data.split(":")[2]  # Источник сообщения (откуда был вызван callback)
    new_lang = "en" if curr_lang == "ru" else "ru"  # Смена языка
    await db.change_chat_gpt_lang(call.from_user.id, new_lang)  # Обновляем язык в базе
    lang_text = {"ru": "русский", "en": "английский"}
    await call.answer(f"Язык изменён на {lang_text[new_lang]}")
    if from_msg == "acc":
        kb = user_kb.settings(new_lang, from_msg)  # Меню ChatGPT
    else:
        kb = user_kb.get_account(new_lang, from_msg)  # Меню аккаунта
    await call.message.edit_reply_markup(reply_markup=kb)  # Обновляем клавиатуру


# Хендлер для ChatGPT
@dp.message_handler(state="*", text="💬ChatGPT✅")
@dp.message_handler(state="*", text="💬ChatGPT")
@dp.message_handler(state="*", commands="chatgpt")
async def ask_question(message: Message, state: FSMContext):

    await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "chatgpt")  # Устанавливаем ChatGPT как основной AI
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)  # Получаем данные пользователя
    model = (user["gpt_model"]).replace("-", "_")

    logger.info(f'Выбранная модель {model}')

    if model == "4o_mini" and user["tokens_4o_mini"] <= 0:
        logger.info("Модель 4o-mini закончилась - переключаем")
        await db.set_model(user_id, "4o")
        model = "4o"
        await message.answer("✅Модель для ChatGPT изменена на GPT-4o")

    # Проверяем наличие токенов и подписки
    if user[f"tokens_{model}"] <= 0:
        return await not_enough_balance(message.bot, user_id, "chatgpt")  # Сообщаем об исчерпании лимита

    # Сообщение с запросом ввода
    await message.answer("""<b>Введите запрос</b>
Например: <code>Напиши сочинение на тему: Как я провёл это лето</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-ChatGPT-podrobnaya-instrukciya-06-04">Подробная инструкция.</a></u>""",
                         reply_markup=user_kb.get_menu("chatgpt"),
                         disable_web_page_preview=True)


# Хендлер для вывода информации о поддержке
@dp.message_handler(state="*", text="👨🏻‍💻Поддержка")
@dp.message_handler(state="*", commands="help")
async def support(message: Message, state: FSMContext):
    
    await state.finish()  # Завершаем текущее состояние
    await message.answer('Ответы на многие вопросы можно найти в нашем <a href="https://t.me/NeuronAgent">канале</a>.',
                         disable_web_page_preview=True, reply_markup=user_kb.about)  # Кнопка с инструкцией


# Хендлер для MidJourney
@dp.message_handler(state="*", text="🎨Midjourney✅")
@dp.message_handler(state="*", text="🎨Midjourney")
@dp.message_handler(state="*", commands="midjourney")
async def gen_img(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "image")  # Устанавливаем MidJourney как основной AI
    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя
    # Проверяем наличие токенов и подписки
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(message.bot, message.from_user.id, "image")  # Сообщаем об исчерпании лимита
        return


    # Сообщение с запросом ввода
    await message.answer("""<b>Введите запрос для генерации изображения</b>
<i>Например:</i> <code>Замерзшее бирюзовое озеро вокруг заснеженных горных вершин</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                         reply_markup=user_kb.get_menu("image"),
                         disable_web_page_preview=True)


# Хендлер для выбора суммы через callback-запрос
@dp.callback_query_handler(Text(startswith="select_amount"))
async def select_amount(call: CallbackQuery):

    amount = int(call.data.split(":")[1])  # Получаем сумму из callback
    # Генерация ссылок для пополнения
    urls = {
        "tinkoff": pay.get_pay_url_tinkoff(call.from_user.id, amount),
        "freekassa": pay.get_pay_url_freekassa(call.from_user.id, amount),
        "payok": pay.get_pay_url_payok(call.from_user.id, amount),
    }
    await call.message.answer(f"""💰 Сумма: <b>{amount} рублей

♻️ Средства зачислятся автоматически</b>""", reply_markup=user_kb.get_pay_urls(urls))  # Кнопки с ссылками на оплату
    await call.answer()


# Хендлер для отмены текущего состояния
@dp.message_handler(state="*", text="Отмена")
async def cancel(message: Message, state: FSMContext):

    await state.finish()  # Завершаем текущее состояние
    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя
    await message.answer("Ввод остановлен", reply_markup=user_kb.get_menu(user["default_ai"]))  # Возвращаем меню


# Хендлер для выбора изображения через callback
@dp.callback_query_handler(Text(startswith="choose_image:"))
async def choose_image(call: CallbackQuery):

    await call.answer()  # Закрываем callback уведомление
    user = await db.get_user(call.from_user.id)

    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(call.bot, call.from_user.id, "image")  # Проверка наличия баланса для MidJourney
        return
    action_id = call.data.split(":")[1]
    image_id = call.data.split(":")[2]
    task_id = (await db.get_task_by_action_id(int(action_id)))["external_task_id"]
    await call.message.answer("Ожидайте, сохраняю изображение в отличном качестве…⏳", 
                              reply_markup=user_kb.get_menu(user["default_ai"]))
    res = await ai.get_choose_mdjrny(task_id, image_id, call.from_user.id)  # Запрос к MidJourney API

    if res is not None and "success" not in res:
        if "message" in res and res["message"] == "repeat task":
            return await call.message.answer("Вы уже сохраняли это изображение!")  # Сообщение, если изображение уже сохранялось


# Хендлер для изменения изображения через callback
@dp.callback_query_handler(Text(startswith="change_image:"))
async def change_image(call: CallbackQuery):

    await call.answer()  # Закрываем callback уведомление
    user_id = call.from_user.id
    user_notified = await db.get_user_notified_mj(user_id)

    user = await db.get_user(user_id)
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(call.bot, user_id, "image")  # Проверка лимитов
        return
    action = call.data.split(":")[3]
    button_type = call.data.split(":")[1]
    value = call.data.split(":")[2]
    task_id = (await db.get_task_by_action_id(int(action)))["external_task_id"]
    await call.message.answer("Ожидайте, обрабатываю изображение⏳", 
                              reply_markup=user_kb.get_menu(user["default_ai"]))

    action_id = await db.add_action(user_id, "image", button_type)

    if 1 < user["mj"] <= 3:  # Если осталось 3 или меньше запросов
        now = datetime.now()

        if user_notified is None:
            await db.create_user_notification_mj(user_id)
            await notify_low_midjourney_requests(user_id, call.bot)  # Отправляем уведомление о низком количестве токенов
            # await db.set_user_notified(user_id)  # Помечаем, что уведомление отправлено
        else:
            last_notification = user_notified['last_notification']
            if last_notification is None or now > last_notification + timedelta(days=30):
                await db.update_user_notification_mj(user_id)
                await notify_low_midjourney_requests(user_id, call.bot)

    if button_type == "zoom":
        response = await mj_api.outpaint(task_id, value, action_id)  # Масштабирование изображения через API
    elif button_type == "vary":
        response = await mj_api.variation(task_id, value, action_id)  # Вариация изображения через API


# Хендлер для очистки контента через callback
@dp.callback_query_handler(text="clear_content")
async def clear_content(call: CallbackQuery, state: FSMContext):

    user = await db.get_user(call.from_user.id)
    await state.finish()  # Завершаем текущее состояние
    await call.message.answer("Диалог завершен", reply_markup=user_kb.get_menu(user["default_ai"]))  # Сообщение о завершении диалога
    try:
        await call.answer()  # Закрываем callback уведомление
    except:
        pass


# Хендлер для повторного ввода запроса через callback
@dp.callback_query_handler(Text(startswith="try_prompt"))
async def try_prompt(call: CallbackQuery, state: FSMContext):

    data = await state.get_data()

    if "prompt" not in data:
        await call.message.answer("Попробуйте заново ввести запрос")
        return await call.answer()  # Закрываем callback уведомление
        await state.finish()
    await call.answer()

    user = await db.get_user(call.from_user.id)
    if user["default_ai"] == "image":
        await get_mj(data['prompt'], call.from_user.id, call.bot)  # Генерация изображения


# Хендлер для настроек ChatGPT: ввод данных о пользователе через callback
@dp.callback_query_handler(text="chatgpt_about_me", state="*")
async def chatgpt_about_me(call: CallbackQuery, state: FSMContext):

    user = await db.get_user(call.from_user.id)
    await call.message.answer(
        '<b>Введите запрос</b>\n\nПоделитесь с ChatGPT любой информацией о себе, чтобы получить более качественные ответы⤵️\n\n<u><a href="https://telegra.ph/Tonkaya-nastrojka-ChatGPT-06-30">Инструкция.</a></u>',
        disable_web_page_preview=True,
        reply_markup=user_kb.clear_description())
    await state.set_state(states.ChangeChatGPTAboutMe.text)  # Устанавливаем состояние ввода данных
    await call.answer()


# Хендлер для сохранения введенной информации о пользователе в ChatGPT
@dp.message_handler(state=states.ChangeChatGPTAboutMe.text)
async def change_profile_info(message: Message, state: FSMContext):

    if len(message.text) > 256:
        return await message.answer("Максимальная длина 256 символов")
    await db.update_chatgpt_about_me(message.from_user.id, message.text)  # Обновляем данные в базе
    await message.answer("✅Описание обновлено!")
    await state.finish()


# Хэндлер ввода характерий ChatGPT
@dp.callback_query_handler(text="character_menu", state="*")
async def character_menu(call: CallbackQuery, state: FSMContext):

    user = await db.get_user(call.from_user.id)
    await call.message.answer(
        '<b>Введите запрос</b>\n\nНастройте ChatGPT как Вам удобно - тон, настроение, эмоциональный окрас сообщений⤵️\n\n<u><a href="https://telegra.ph/Tonkaya-nastrojka-ChatGPT-06-30">Инструкция.</a></u>',
        disable_web_page_preview=True,
        reply_markup=user_kb.clear_description())
    await state.set_state(states.ChangeChatGPTCharacter.text)


# Хендлер для сохранения характера ChatGPT
@dp.message_handler(state=states.ChangeChatGPTCharacter.text)
async def change_character(message: Message, state: FSMContext):

    if len(message.text) > 256:
        return await message.answer("Максимальная длина 256 символов")
    await db.update_chatgpt_character(message.from_user.id, message.text)  # Обновляем данные в базе
    await message.answer("✅Описание обновлено!")
    await state.finish()


# Хендлер для сброса настроек ChatGPT
@dp.callback_query_handler(text="reset_chatgpt_settings", state="*")
async def reset_chatgpt_settings(call: CallbackQuery, state: FSMContext):

    await db.update_chatgpt_character(call.from_user.id, "")
    await db.update_chatgpt_about_me(call.from_user.id, "")  # Сброс данных
    await call.answer("Описание удалено", show_alert=True)


# Хендлер для изменения настроек ChatGPT
@dp.callback_query_handler(text="chatgpt_settings", state="*")
async def chatgpt_setting(call: CallbackQuery, state: FSMContext):

    user = await db.get_user(call.from_user.id)
    await call.message.answer(
        '<b>Введите запрос</b>\n\nНастройте ChatGPT как вам удобно - тон, настроение, эмоциональный окрас сообщений ⤵️\n\n<u><a href="https://telegra.ph/Tonkaya-nastrojka-ChatGPT-06-30">Инструкция.</a></u>',
        disable_web_page_preview=True,
        reply_markup=user_kb.get_menu(user["default_ai"]))
    await state.set_state(states.ChangeChatGPTSettings.text)  # Устанавливаем состояние ввода настроек
    await call.answer()


# Хендлер для сохранения новых настроек ChatGPT
@dp.message_handler(state=states.ChangeChatGPTSettings.text)
async def change_profile_settings(message: Message, state: FSMContext):

    if len(message.text) > 256:
        return await message.answer("Максимальная длина 256 символов")
    await db.update_chatgpt_settings(message.from_user.id, message.text)  # Обновляем настройки в базе
    await message.answer("Описание обновлено!")
    await state.finish()


# Основной хендлер для обработки сообщений и генерации запросов
@dp.message_handler()
async def gen_prompt(message: Message, state: FSMContext):

    await state.update_data(prompt=message.text)  # Сохраняем запрос пользователя
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if user is None:
        await message.answer("Введите команду /start для перезагрузки бота")
        # return await message.bot.send_message(ADMINS_CODER, user_id)

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace("-", "_")

        logger.info(f'Текстовый запрос к GPT. User: {user}, Model: {model}, tokens: {user[f"tokens_{model}"]}')

        if model == "4o_mini" and user["tokens_4o_mini"] <= 0:
            logger.info("Модель 4o-mini закончилась - переключаем")
            await db.set_model(user_id, "4o")
            model = "4o"
            await message.answer("✅Модель для ChatGPT изменена на GPT-4o")

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, user_id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_character"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt=message.text, messages=messages, user_id=user_id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(message.text, user_id, message.bot)  # Генерация изображения через MidJourney


# Хэндлер для работы с голосовыми сообщениями
@dp.message_handler(content_types=['voice'])
async def handle_voice(message: Message, state: FSMContext):

    file_info = await message.bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    file = await message.bot.download_file(file_path)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_ogg_file:
        temp_ogg_file.write(file.getbuffer())
        temp_ogg_path = temp_ogg_file.name
    
    text = voice_to_text(temp_ogg_path)
    os.remove(temp_ogg_path)
    await state.update_data(prompt=text)  # Сохраняем запрос пользователя

    user = await db.get_user(message.from_user.id)

    if user is None:
        await message.answer("Введите команду /start для перезагрузки бота")
        return await message.bot.send_message(796644977, message.from_user.id)

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace("-", "_")

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, message.from_user.id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_settings"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt=text, messages=messages, user_id=message.from_user.id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(text, message.from_user.id, message.bot)  # Генерация изображения через MidJourney


# Перевод текста в Аудио
@dp.callback_query_handler(text="text_to_audio")
async def return_voice(call: CallbackQuery, state: FSMContext):

    user_id = call.from_user.id

    # Пытаемся получить текущий голос пользователя
    try:
        user_voice = await db.get_voice(user_id)
        if not user_voice:  # Если результат пустой
            raise ValueError("User voice not found")
    except (ValueError, Exception):  # Если строки нет или другая ошибка
        user_voice = await db.create_voice(user_id)  # Создаем запись

    # Получаем данные из состояния
    content_raw = await state.get_data()

    content = content_raw.get("content")
    if not content:
        await call.message.answer("Нет текста для озвучивания.")
        return

    # Генерация аудио из текста
    audio_response = text_to_speech(content, voice=user_voice)

    # Отправляем голосовое сообщение
    await call.message.answer_voice(voice=audio_response)

    # Закрываем callback уведомление
    try:
        await call.answer()
    except Exception as e:
        logger.error(f"Ошибка при закрытии callback уведомления: {e}")


# Хендлер для обработки фотографий
@dp.message_handler(is_media_group=False, content_types="photo")
async def photo_imagine(message: Message, state: FSMContext):

    user_id = message.from_user.id

    if message.caption is None:
        await message.answer("Добавьте описание к фотографии")
        return
    file = await message.photo[-1].get_file()
    photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
    ds_photo_url = await more_api.upload_photo_to_host(photo_url)  # Загрузка фото на внешний хостинг
    if ds_photo_url == "error":
        await message.answer("Генерация с фото недоступна, повторите попытку позже")
        await message.bot.send_message(bug_id, "Необходимо заменить API-ключ фотохостинга")
        return
    prompt = ds_photo_url + " " + message.caption  # Создаем запрос на основе фотографии и описания
    await state.update_data(prompt=prompt)

    user = await db.get_user(user_id)

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace('-', '_')

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, message.from_user.id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_settings"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt, messages=messages, user_id=message.from_user.id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(prompt, message.from_user.id, message.bot)


# Хендлер для обработки альбомов (групповых фото)
@dp.message_handler(is_media_group=True, content_types=ContentType.ANY)
async def handle_albums(message: Message, album: List[Message], state: FSMContext):
    
    if len(album) != 2 or not (album[0].photo and album[1].photo):
        return await message.answer("Пришлите два фото, чтобы их склеить")

    # Обработка первого фото
    file = await album[0].photo[-1].get_file()
    photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
    ds_photo_url1 = await more_api.upload_photo_to_host(photo_url)

    # Обработка второго фото
    file = await album[1].photo[-1].get_file()
    photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
    ds_photo_url2 = await more_api.upload_photo_to_host(photo_url)

    prompt = f"{ds_photo_url1} {ds_photo_url2}"  # Создаем запрос для двух фото
    await state.update_data(prompt=prompt)
    await get_mj(prompt, message.from_user.id, message.bot)  # Генерация изображения через MidJourney


# Вход в меню выбора модели GPT
@dp.callback_query_handler(text="model_menu")
async def model_menu(call: CallbackQuery):

    user_id = call.from_user.id
    user_model = await db.get_model(user_id)
    
    logger.info(f"User ID: {user_id}, текущая модель: {user_model}")

    # Динамическое создание клавиатуры с выбранным моделью
    keyboard = user_kb.model_keyboard(selected_model=user_model)
    
    await call.message.answer("Выберите модель GPT для диалогов⤵️:", reply_markup=keyboard)
    await call.answer()


# Выбор модели GPT
@dp.callback_query_handler(text_contains="select_model")
async def select_model(call: CallbackQuery):

    user_id = call.from_user.id
    selected_model = call.data.split(":")[1]  # Извлечение выбранной модели из данных 

    logger.info(f"User ID: {user_id}, выбранная модель: {selected_model}")

    try:
        # Записываем выбранную модель в базу данных
        await db.set_model(user_id, selected_model)

        # Получаем обновленную клавиатуру с выбранной моделью
        keyboard = user_kb.model_keyboard(selected_model=selected_model)

        await call.message.edit_text("Выберите модель GPT для диалогов⤵️:", reply_markup=keyboard)
        await call.message.answer(f"✅Модель для ChatGPT изменена на GPT-{selected_model}")   
    except Exception as e:
        logger.error(f"Ошибка при выборе модели GPT: {e}")
        await call.answer()


# Вход в меню выбора голоса
@dp.callback_query_handler(text="voice_menu")
async def voice_menu(call: CallbackQuery):

    user_id = call.from_user.id
    user_voice = await db.get_voice(user_id)
    
    # Динамическое создание клавиатуры с выбранным голосом
    keyboard = user_kb.voice_keyboard(selected_voice=user_voice)
    
    await call.message.answer("Выберите голос для ChatGPT⤵️:", reply_markup=keyboard)
    await call.answer()


# Выбор голоса
@dp.callback_query_handler(text_contains="select_voice")
async def select_voice(call: CallbackQuery):
    user_id = call.from_user.id
    selected_voice = call.data.split(":")[1]  # Извлечение выбранного голоса из данных

    try:
        # Записываем выбранный голос в базу данных
        await db.set_voice(user_id, selected_voice)

        # Получаем обновлённую клавиатуру с выбранным голосом
        updated_keyboard = user_kb.voice_keyboard(selected_voice=selected_voice)

        # Редактируем текущее сообщение с новой клавиатурой
        await call.message.edit_reply_markup(reply_markup=updated_keyboard)

        # Отправляем уведомление об успешном выборе
        await call.answer(f"Выбран голос: {selected_voice} ✅")
    except Exception as e:
        logger.error(f"Ошибка при выборе голоса: {e}")
        await call.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)


# Хэндлер для отправки всех голосов
@dp.callback_query_handler(text="check_voice")
async def check_voice(call: CallbackQuery):
    
    user_id = call.from_user.id
    user_lang = await db.get_chat_gpt_lang(user_id)

    # Путь к папке с файлами
    if user_lang == "ru":
        voices_path = "voices_ru"
    elif user_lang == "en":
        voices_path = "voices_en"

    # Проверяем, что папка существует
    if not os.path.exists(voices_path):
        await call.message.answer("⚠️ Папка с голосами не найдена.")
        return
    
    # Получаем список файлов .mp3
    voice_files = [f for f in os.listdir(voices_path) if f.endswith(".mp3")]
    
    # Если файлов нет, отправляем сообщение
    if not voice_files:
        await call.message.answer("⚠️ В папке 'voices' нет доступных файлов.")
        return
    
    # Создаем медиа-группу
    media_group = MediaGroup()
    for voice_file in voice_files:
        file_path = os.path.join(voices_path, voice_file)
        audio = InputFile(file_path)
        media_group.attach_audio(audio)
    
    # Отправляем файлы одним сообщением
    await call.message.answer(f"Ответы ChatGPT:{'RUS' if user_lang == 'ru' else 'ENG'}")
    await call.message.answer_media_group(media_group)
    await call.answer()



