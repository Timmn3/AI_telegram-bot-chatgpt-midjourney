import logging
from datetime import datetime, timedelta
from typing import List
import requests
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ChatActions, ContentType, MediaGroup, Update, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext

import matplotlib.pyplot as plt
import io
import re
import tempfile
import os
import config
from states.user import EnterChatName, EnterChatRename
from utils import db, ai, more_api, pay  # Импорт утилит для взаимодействия с БД и внешними API
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
                     'o3-mini': 'GPT-o3-mini'}  # поменять

        user_data = await db.get_user_notified_gpt(user_id)

        if not model == '4o-mini':
            await db.set_model(user_id, "4o-mini")
            await bot.send_message(user_id, "✅Модель для ChatGPT изменена на GPT-4o-mini")

        if model == '4o-mini':
            keyboard = user_kb.get_chatgpt_models_noback()
        else:
            keyboard = user_kb.get_chatgpt_tokens_menu('normal', model)

        await bot.send_message(user_id,
                               f"⚠️Токены для {model_map[model]} закончились!\n\nВыберите интересующий вас вариант⤵️",
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
        """,
                               reply_markup=user_kb.get_midjourney_requests_menu())  # Отправляем уведомление с клавиатурой для пополнения запросов


# Генерация изображения через MidJourney
async def get_mj(prompt, user_id, bot: Bot):
    user = await db.get_user(user_id)

    # Проверяем наличие запросов и отправляем уведомление, если запросы исчерпаны
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(bot, user_id, "image")  # Отправляем уведомление о недостатке средств
        return

    await bot.send_message(user_id, "Ожидайте, генерирую изображение..🕙",
                           reply_markup=user_kb.get_menu(user["default_ai"]))
    # await bot.send_message(user_id, "В настоящее время генерация не доступна, попробуйте позже!")
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


def process_formula(match):
    formula = match.group(1)

    # Замены для наиболее популярных команд
    formula = re.sub(r"\\frac\{(.*?)\}\{(.*?)\}", r"\1 / \2", formula)  # \frac{a}{b} → a / b
    formula = re.sub(r"\\text\{(.*?)\}", r"\1", formula)  # \text{...} → текст без LaTeX
    formula = formula.replace(r"\times", "×").replace(r"\cdot", "·")  # Умножение: \times → ×, \cdot → ·
    formula = formula.replace(r"\implies", "⇒").replace(r"\approx", "≈")  # Логические и математические символы
    formula = re.sub(r"\\sqrt\{(.*?)\}", r"√(\1)", formula)  # Квадратный корень: \sqrt{a} → √(a)

    # Обработка системы уравнений (например, \begin{cases} ... \end{cases})
    formula = re.sub(r"\\begin{cases}(.*?)\\end{cases}", r"\n{\1}\n", formula, flags=re.DOTALL)
    formula = re.sub(r"\\\\", r"\n", formula)  # Заменяем \\\\ на новую строку

    # Степени (например, x^2 → x²)
    formula = re.sub(r"([a-zA-Z])\^([0-9]+)", lambda m: f"{m.group(1)}{chr(8304 + int(m.group(2)))}", formula)

    # Индексы: t_1 → t₁
    formula = re.sub(r"([a-zA-Z])_([0-9]+)", lambda m: f"{m.group(1)}{chr(8320 + int(m.group(2)))}", formula)

    # Убираем лишние символы LaTeX (например, \)
    formula = formula.replace("\\", "")

    return f"<pre>{formula.strip()}</pre>"


def format_math_in_text(text: str) -> str:
    # Обработка формул внутри \[ ... \] или \( ... \)
    text = re.sub(r"\\\[(.*?)\\\]", process_formula, text)  # Обработка формул внутри \[...\]
    text = re.sub(r"\\\((.*?)\\\)", process_formula, text)  # Обработка формул внутри \(...\)
    return text


# Генерация ответа от ChatGPT
async def get_gpt(prompt, messages, user_id, bot: Bot, state: FSMContext):
    user = await db.get_user(user_id)
    lang_text = {"en": "compose an answer in English", "ru": "составь ответ на русском языке"}
    model = user['gpt_model']
    model_dashed = model.replace("-", "_")

    current_chat = await db.get_chat_by_id(user["current_chat_id"])
    summary = current_chat["summary"] if current_chat else ""
    if summary:
        prompt = f"Ранее в этом чате обсуждалось: {summary.strip()}\n\n" + prompt
    prompt += f"\n{lang_text[user['chat_gpt_lang']]}"

    message_user = prompt

    if messages is None:
        messages = []
    messages.append({"role": "user", "content": prompt})

    logger.info(f"Текстовый запрос к ChatGPT. User: {user}, Model: {model}, tokens: {user[f'tokens_{model_dashed}']}")

    await bot.send_chat_action(user_id, ChatActions.TYPING)

    res = await ai.get_gpt(messages, model)

    # Шаг 1: форматируем математические формулы внутри \( \)
    html_content = format_math_in_text(res["content"])

    # Шаг 2: если нужно, можно ещё как-то обрабатывать, но второй раз экранировать HTML — нельзя!

    # Отправка пользователю
    if len(html_content) <= 4096:
        await bot.send_message(
            user_id,
            html_content,
            reply_markup=user_kb.get_clear_or_audio(),
            parse_mode="HTML"
        )
    else:
        parts = split_message(html_content, 4096)
        for part in parts:
            await bot.send_message(
                user_id,
                part,
                reply_markup=user_kb.get_clear_or_audio(),
                parse_mode="HTML"
            )

    await state.update_data(content=res["content"])

    if not res["status"]:
        return

    message_gpt = res["content"]
    messages.append({"role": "assistant", "content": message_gpt})

    if not current_chat:
        generated_name = await generate_chat_name(message_user, model, message_gpt)
        new_chat_id = await db.create_chat(user_id, name=generated_name, summary="")
        await db.set_current_chat(user_id, new_chat_id)
        chat_id = new_chat_id
    else:
        chat_id = current_chat["id"]

    await db.add_message(chat_id, user_id, message_user)
    await db.add_message(chat_id, None, message_gpt)

    old_summary = current_chat["summary"] if current_chat else ""
    new_summary = await update_chat_summary(chat_id, message_user, message_gpt, model, old_summary)
    await db.update_chat_summary(chat_id, new_summary)

    await db.remove_chatgpt(user_id, res["tokens"], model)

    now = datetime.now()
    user_notified = await db.get_user_notified_gpt(user_id)
    user = await db.get_user(user_id)
    has_purchase = await db.has_matching_orders(user_id)

    if user[f"tokens_{model_dashed}"] <= 1000 and model_dashed != "4o_mini":
        logger.info(
            f"Осталось {user[f'tokens_{model_dashed}']} токенов, уведомление: {user_notified}, покупка: {has_purchase}")
        if user_notified is None and has_purchase:
            await db.create_user_notification_gpt(user_id)
            await notify_low_chatgpt_tokens(user_id, bot)
        else:
            last_notification = user_notified['last_notification'] if user_notified else None
            if (last_notification is None or now > last_notification + timedelta(days=30)) and has_purchase:
                await db.update_user_notification_gpt(user_id)
                await notify_low_chatgpt_tokens(user_id, bot)

    await db.add_action(user_id, model)
    return messages


async def update_chat_summary(chat_id: int, message_user: str, message_gpt: str, model: str,
                              old_summary: str = "") -> str:
    summary_prompt = (
        f"Вот краткое описание предыдущей беседы: {old_summary}\n\n"
        f"Добавь к нему краткое описание следующей части диалога:\n"
        f"Пользователь: {message_user}\n"
        f"Ассистент: {message_gpt}\n\n"
        f"Обновлённая краткая сводка (максимум 3000 символов):"
    )

    response = await ai.get_gpt(
        messages=[
            {"role": "system",
             "content": "Ты ассистент, умеющий сжимать диалоги в краткое описание. Пиши коротко и по делу."},
            {"role": "user", "content": summary_prompt}
        ],
        model=model
    )

    return response["content"].strip()


async def generate_chat_name(message_user: str, model: str, message_gpt: str) -> str:
    prompt = (
        f"Пользователь задал вопрос: \"{message_user}\"\n"
        f"Ассистент ответил: \"{message_gpt}\"\n\n"
        f"На основе этого диалога придумай короткое, осмысленное название чата (до 50 символов):"
    )

    response = await ai.get_gpt(
        messages=[
            {"role": "system", "content": "Ты генерируешь короткие и содержательные заголовки диалогов."},
            {"role": "user", "content": prompt}
        ],
        model=model
    )

    return response["content"].strip().strip('"')[:50]


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


# @dp.errors_handler()
# async def log_all_updates(update: Update, exception: Exception = None):
#     logging.debug(f"Update received: {update.to_python()}")
#     if exception:
#         logging.error(f"Exception: {exception}")
#     return True

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
        await db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name,
                          int(inviter_id))
        default_ai = "chatgpt"
    else:
        default_ai = user["default_ai"]

    # Отправляем приветственное сообщение
    await message.answer("""<b>NeuronAgent</b>🤖 - <i>2 нейросети в одном месте!</i>
<b>ChatGPT или Midjourney?</b>""", reply_markup=user_kb.get_menu(default_ai))

    # Проверка промокода, если он был передан
    # if code is not None:
    #     await check_promocode(message.from_user.id, code, message.bot)


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
├ Всего заработано: <b>{all_income}</b> рублей
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
    gpt_o3_mini = int(user['tokens_o3_mini']) if int(user['tokens_o3_mini']) >= 0 else 0

    logger.info(
        f"Количество токенов и запросов для {user_id}:mj: {mj}, gpt_4o: {gpt_4o}, gpt_4o_mini: {gpt_4o_mini}, gpt_o3_mini: {gpt_o3_mini}")

    # Формируем текст с количеством доступных генераций и токенов
    sub_text = f"""
Вам доступно⤵️

Генерации 🎨Midjourney:  {format(mj, ',').replace(',', ' ')}
Токены 💬GPT-4o:  {format(gpt_4o, ',').replace(',', ' ')}
Токены 💬GPT-4o-mini:  ♾️
Токены 💬GPT-o3-mini:  {format(gpt_o3_mini, ',').replace(',', ' ')}
        """

    # Отправляем сообщение с обновленными данными аккаунта
    await message.answer(f"""🆔: <code>{user_id}</code>
{sub_text}""", reply_markup=user_kb.get_account(user_lang, "account"))


# Хендлер для возврата к профилю пользователя через callback-запрос
@dp.callback_query_handler(Text(startswith="back_to_profile"), state="*")
async def back_to_profile(call: CallbackQuery, state: FSMContext):
    logger.info(f"Back To Profile {call.data}")

    src = call.data.split(":")[1]
    user_id = call.from_user.id
    user = await db.get_user(user_id)  # Получаем данные пользователя

    if src == "acc":
        # Удаляем старое сообщение с текстом и клавиатурой
        await call.message.delete()

        await state.finish()
        user_lang = user['chat_gpt_lang']

        # Формируем текст с количеством доступных генераций и токенов
        mj = int(user['mj']) + int(user['free_image']) if int(user['mj']) + int(user['free_image']) >= 0 else 0
        gpt_4o_mini = int(user['tokens_4o_mini']) if int(user['tokens_4o_mini']) >= 0 else 0
        gpt_4o = int(user['tokens_4o']) if int(user['tokens_4o']) >= 0 else 0
        gpt_o3_mini = int(user['tokens_o3_mini']) if int(user['tokens_o3_mini']) >= 0 else 0

        logger.info(
            f"Колиество токенов и запросов для {user_id}:mj: {mj}, gpt_4o: {gpt_4o}, gpt_4o_mini: {gpt_4o_mini}, gpt_o3_mini: {gpt_o3_mini}")

        keyboard = user_kb.get_account(user_lang, "account")

        # Формируем текст с количеством доступных генераций и токенов
        sub_text = f"""
Вам доступно⤵️

Генерации 🎨Midjourney:  {format(mj, ',').replace(',', ' ')}
Токены 💬GPT-4o:  {format(gpt_4o, ',').replace(',', ' ')}
Токены 💬GPT-4o-mini:  ♾️
Токены 💬GPT-o3-mini:  {format(gpt_o3_mini, ',').replace(',', ' ')}
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
    if state:
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
    # Получаем текущий активный чат
    current_chat = await db.get_chat_by_id(user["current_chat_id"])

    # Отправляем пользователю имя текущего чата (если есть)
    if current_chat and current_chat["name"]:
        await message.answer(f"💬 Активный чат: *{current_chat['name']}*", parse_mode="Markdown")


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
            return await call.message.answer(
                "Вы уже сохраняли это изображение!")  # Сообщение, если изображение уже сохранялось


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
            await notify_low_midjourney_requests(user_id,
                                                 call.bot)  # Отправляем уведомление о низком количестве токенов
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
    await call.message.answer("Диалог завершен",
                              reply_markup=user_kb.get_menu(user["default_ai"]))  # Сообщение о завершении диалога
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
    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

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

    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

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


from aiogram.utils.exceptions import CantParseEntities


async def safe_send_message(bot, user_id, text, **kwargs):
    try:
        await bot.send_message(user_id, text, **kwargs)
    except CantParseEntities as e:
        logger.error(f"Невозможно обработать сущности в сообщении для пользователя {user_id}: {e}")

        # Отправим запрос в GPT на исправление форматирования
        prompt = f"Исправь форматирование этого текста для Telegram, чтобы он был корректным: {text}"

        # Получим ответ от GPT
        corrected_text_response = await ai.get_gpt(
            messages=[{"role": "user", "content": prompt}],
            model="4o-mini"  # Или используйте нужную модель
        )

        # Извлекаем исправленный текст от GPT
        corrected_text = corrected_text_response["content"]

        # Отправляем исправленный текст пользователю
        await bot.send_message(user_id, corrected_text, **kwargs)


# Основной хендлер для обработки сообщений и генерации запросов
@dp.message_handler()
async def gen_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)  # Сохраняем запрос пользователя
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if user is None:
        await safe_send_message(message.bot, user_id, "Введите команду /start для перезагрузки бота")

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace("-", "_")

        logger.info(f'Текстовый запрос к GPT. User: {user}, Model: {model}, tokens: {user[f"tokens_{model}"]}')

        if model == "4o_mini" and user["tokens_4o_mini"] <= 0:
            logger.info("Модель 4o-mini закончилась - переключаем")
            await db.set_model(user_id, "4o")
            model = "4o"
            await safe_send_message(message.bot, user_id, "✅Модель для ChatGPT изменена на GPT-4o")

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, user_id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_character"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt=message.text, messages=messages, user_id=user_id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT

        # Отправка сообщения через безопасную функцию
        await state.update_data(messages=update_messages)
        await safe_send_message(message.bot, user_id, update_messages[-1]['content'], parse_mode="HTML")

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
        temp_ogg_path = temp_ogg_file.nameF

    text = voice_to_text(temp_ogg_path)
    os.remove(temp_ogg_path)
    await state.update_data(prompt=text)  # Сохраняем запрос пользователя

    user = await db.get_user(message.from_user.id)

    if user is None:
        await message.answer("Введите команду /start для перезагрузки бота")

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
    processing_message = await call.message.answer("⏳Идёт запись голосового, ожидайте")
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
    # Удаляем сообщение "⏳Идёт запись голосового, ожидайте"
    await processing_message.delete()
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

    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

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

    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

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


@dp.callback_query_handler(text="my_chats")
async def show_my_chats(call: CallbackQuery, page: int = 0):
    """
    Обработчик команды "my_chats", который отображает список чатов пользователя
    с пагинацией и предоставляет возможность управления чатами.

    :param call: Объект CallbackQuery, содержащий данные вызова.
    :param page: Номер страницы для отображения чатов.
    """
    user_id = call.from_user.id

    # Получаем данные пользователя
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Конфигурация пагинации
    chats_per_page = 4  # Количество чатов на одной странице
    offset = page * chats_per_page

    # Получаем список чатов пользователя с учетом пагинации
    conn = await db.get_conn()
    chats = await conn.fetch(
        "SELECT id, name FROM chats WHERE user_id = $1 ORDER BY created_at LIMIT $2 OFFSET $3",
        user["user_id"], chats_per_page, offset
    )
    await conn.close()

    current_chat_id = user["current_chat_id"]

    # Формируем текст сообщения
    text = (
        "🗂 *Меню чатов позволяет:*\n"
        "- Создавать новые чаты\n"
        "- Переключаться между чатами\n"
        "- Изменять настройки и названия чатов\n\n"
        "*Выберите необходимый чат ⤵️*"
    )

    # Формируем клавиатуру с кнопками
    kb = InlineKeyboardMarkup(row_width=2)

    # Кнопки: удалить все и создать новый
    kb.add(
        InlineKeyboardButton("❌Удалить все чаты", callback_data="delete_all_chats"),
        InlineKeyboardButton("➕Новый чат", callback_data="create_chat")
    )

    # Кнопки чатов
    for chat in chats:
        chat_name = chat["name"]
        chat_id = chat["id"]
        # Отметка активного чата
        if chat_id == current_chat_id:
            chat_button_text = f"✅ {chat_name}"
        else:
            chat_button_text = chat_name
        kb.add(InlineKeyboardButton(chat_button_text, callback_data=f"select_chat:{chat_id}"))

    # Пагинация
    kb.row(
        InlineKeyboardButton("⏮", callback_data=f"page:first:{page}"),
        InlineKeyboardButton("◀", callback_data=f"page:prev:{page}"),
        InlineKeyboardButton("▶", callback_data=f"page:next:{page}"),
        InlineKeyboardButton("⏭", callback_data=f"page:last:{page}")
    )

    # Назад
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="settings"))

    # Отправляем обновленное сообщение с чатиками и кнопками
    await call.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('page:'))
async def paginate_chats(call: CallbackQuery):
    """
    Обработчик пагинации чатов. Позволяет пользователю переходить между страницами
    списка чатов (первая, предыдущая, следующая, последняя).

    :param call: Объект CallbackQuery, содержащий данные вызова.
    """
    # Получаем данные из callback_data
    page_data = call.data.split(":")
    action = page_data[1]  # first, prev, next, last
    current_page = int(page_data[2])  # Текущая страница

    # Получаем данные пользователя
    user_id = call.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем количество чатов пользователя
    conn = await db.get_conn()
    total_chats = await conn.fetchval(
        "SELECT COUNT(*) FROM chats WHERE user_id = $1", user_id
    )
    await conn.close()

    # Количество чатов на одной странице
    chats_per_page = 4
    total_pages = (total_chats // chats_per_page) + (1 if total_chats % chats_per_page > 0 else 0) - 1

    # Определяем номер новой страницы
    if action == 'first':
        new_page = 0
    elif action == 'prev' and current_page > 0:
        new_page = current_page - 1
    elif action == 'next' and current_page < total_pages:
        new_page = current_page + 1
    elif action == 'last':
        new_page = total_pages
    else:
        new_page = current_page  # если страниц нет, остаёмся на текущей

    # Получаем чаты для новой страницы
    offset = new_page * chats_per_page
    conn = await db.get_conn()
    chats = await conn.fetch(
        "SELECT id, name FROM chats WHERE user_id = $1 ORDER BY created_at LIMIT $2 OFFSET $3",
        user_id, chats_per_page, offset
    )
    await conn.close()

    current_chat_id = user["current_chat_id"]

    # Формируем текст для обновленного списка чатов
    text = (
        "🗂 *Меню чатов позволяет:*\n"
        "- Создавать новые чаты\n"
        "- Переключаться между чатами\n"
        "- Изменять настройки и названия чатов\n\n"
        "*Выберите необходимый чат ⤵️*"
    )

    # Формируем клавиатуру с кнопками
    kb = InlineKeyboardMarkup(row_width=2)

    # Кнопки: удалить все и создать новый
    kb.add(
        InlineKeyboardButton("❌Удалить все чаты", callback_data="delete_all_chats"),
        InlineKeyboardButton("➕Новый чат", callback_data="create_chat")
    )

    # Кнопки чатов
    for chat in chats:
        chat_name = chat["name"]
        chat_id = chat["id"]
        if chat_id == current_chat_id:
            chat_button_text = f"✅ {chat_name}"
        else:
            chat_button_text = chat_name
        kb.add(InlineKeyboardButton(chat_button_text, callback_data=f"select_chat:{chat_id}"))

    # Пагинация
    kb.row(
        InlineKeyboardButton("⏮", callback_data=f"page:first:{new_page}"),
        InlineKeyboardButton("◀", callback_data=f"page:prev:{new_page}"),
        InlineKeyboardButton("▶", callback_data=f"page:next:{new_page}"),
        InlineKeyboardButton("⏭", callback_data=f"page:last:{new_page}")
    )

    # Назад
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="settings"))

    # Отправляем обновленное сообщение с чатиками и кнопками
    try:
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        pass

    # Закрытие всплывающего окна
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('select_chat:'))
async def select_chat(call: CallbackQuery):
    """
    Обработчик выбора чата. Позволяет пользователю выбрать чат для переключения
    и отображения дополнительных настроек чата.

    :param call: Объект CallbackQuery, содержащий данные вызова.
    """
    # Получаем ID выбранного чата
    chat_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    # Получаем данные пользователя
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем информацию о выбранном чате
    chat = await db.get_chat_by_id(chat_id)
    chat_name = chat["name"]

    # Текст для выбранного чата
    text = f'Управление чатом\n"*{chat_name}*"'

    # Формируем кнопки для управления выбранным чатом
    select_button_text = "✅ Выбран" if chat_id == user["current_chat_id"] else "▶️ Выбрать этот чат"
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(select_button_text, callback_data=f"select_active_chat:{chat_id}"),
        InlineKeyboardButton("✏️ Переименовать чат", callback_data=f"rename_chat:{chat_id}"),
        InlineKeyboardButton("🗑 Удалить чат", callback_data=f"delete_selected_chat:{chat_id}"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Обновляем сообщение с новым текстом и кнопками
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('select_active_chat:'))
async def select_active_chat(call: CallbackQuery):
    """
    Обрабатывает выбор активного чата пользователем.

    При получении callback-запроса с выбранным чатом обновляется текущий активный чат
    пользователя и отправляется сообщение о том, что чат успешно загружен.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID выбранного чата
    user_id = call.from_user.id  # Получаем ID пользователя
    user = await db.get_user(user_id)  # Получаем данные пользователя из базы данных

    if not user:
        # Если пользователь не найден, показываем ошибку
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Обновляем текущий активный чат для пользователя в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE users SET current_chat_id = $1 WHERE user_id = $2", chat_id, user["user_id"]
    )
    await conn.close()

    # Отправляем сообщение о том, что чат успешно загружен
    await call.message.edit_text("Чат успешно загружен. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('rename_chat:'))
async def rename_chat(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает запрос на переименование чата.

    При получении callback-запроса с ID чата сохраняет его в состоянии для дальнейшего использования,
    затем запрашивает новое имя чата у пользователя.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Сохраняем chat_id в состояние FSM для дальнейшего использования
    await state.update_data(chat_id=chat_id)

    # Запрашиваем новое имя чата у пользователя
    await call.message.answer("Введите новое имя для чата:")

    # Переходим в состояние ожидания нового имени чата
    await EnterChatRename.chat_name.set()


@dp.callback_query_handler(lambda c: c.data.startswith('delete_selected_chat:'))
async def delete_selected_chat(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление выбранного чата.

    При получении callback-запроса с ID чата удаляет соответствующий чат из базы данных и
    обновляет список чатов, показывая пользователю уведомление об успешном удалении.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Удаляем выбранный чат из базы данных
    conn = await db.get_conn()
    await conn.execute("DELETE FROM chats WHERE id = $1", chat_id)
    await conn.close()

    # Отправляем сообщение об успешном удалении
    await call.message.edit_text("Чат успешно удалён. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(lambda c: c.data.startswith('select_chat:'))
async def select_chat(call: CallbackQuery):
    """
    Обрабатывает выбор чата пользователем.

    При получении callback-запроса с ID выбранного чата обновляется текущий активный чат
    пользователя и отображается обновлённый список чатов.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        # Если пользователь не найден, показываем ошибку
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Обновляем текущий активный чат пользователя в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE users SET current_chat_id = $1 WHERE user_id = $2", chat_id, user["user_id"]
    )
    await conn.close()

    # Обновляем список чатов
    await show_my_chats(call)


@dp.callback_query_handler(text="delete_all_chats")
async def confirm_delete_all_chats(call: CallbackQuery):
    """
    Запрашивает подтверждение на удаление всех чатов.

    При получении callback-запроса с текстом подтверждения, отправляется сообщение с запросом
    на подтверждение удаления всех чатов. Если пользователь подтверждает, чаты будут удалены.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Формируем текст для подтверждения удаления
    confirmation_text = "Вы действительно хотите удалить все чаты?"
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("❌ Удалить все чаты", callback_data="confirm_delete_all_chats"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Отправляем сообщение с кнопками подтверждения
    await call.message.edit_text(confirmation_text, reply_markup=kb)
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(text="confirm_delete_all_chats")
async def delete_all_chats(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление всех чатов пользователя.

    При получении callback-запроса с подтверждением, удаляет все чаты пользователя из базы данных,
    обновляет список чатов и отправляет уведомление об успешном удалении.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Удаляем все чаты пользователя из базы данных
    conn = await db.get_conn()
    await conn.execute("DELETE FROM chats WHERE user_id = $1", user_id)
    await conn.close()

    # Обновляем список чатов
    await show_my_chats(call)

    # Отправляем сообщение об успешном удалении
    await call.message.edit_text("Все чаты успешно удалены. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()


@dp.callback_query_handler(text="create_chat")
async def create_chat(call: CallbackQuery):
    """
    Запрашивает у пользователя название для нового чата.

    При получении callback-запроса с командой создания чата, запрашивает у пользователя название для нового чата
    и переходит в состояние ожидания ввода.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Запрашиваем название нового чата
    await call.message.answer("Введите название чата:")

    # Переходим в состояние ожидания ввода названия нового чата
    await EnterChatName.chat_name.set()


@dp.message_handler(state=EnterChatName.chat_name)
async def process_new_chat_name(message: Message, state: FSMContext):
    """
    Обрабатывает введённое пользователем название нового чата.

    При получении нового имени чата, проверяет его на пустоту, затем создает новый чат в базе данных,
    обновляет текущий чат пользователя и отправляет уведомление об успешном создании чата.
    """
    user_id = message.from_user.id  # Получаем ID пользователя
    chat_name = message.text.strip()  # Получаем название чата

    if not chat_name:
        # Если название пустое, запрашиваем ввод заново
        await message.answer("Название чата не может быть пустым. Пожалуйста, введите название.")
        return

    # Создаем новый чат в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "INSERT INTO chats (user_id, name, created_at, updated_at) VALUES ($1, $2, NOW(), NOW())",
        user_id, chat_name
    )
    await conn.close()

    # Получаем ID нового чата
    conn = await db.get_conn()
    new_chat_id = await conn.fetchval(
        "SELECT id FROM chats WHERE user_id = $1 AND name = $2 LIMIT 1", user_id, chat_name
    )
    await conn.close()

    # Устанавливаем новый чат как активный
    await db.set_current_chat(user_id, new_chat_id)

    # Подтверждаем создание чата
    await message.answer(f'Чат "_{chat_name}_" успешно создан!\n\n*Введите запрос ⤵️*', parse_mode="Markdown")

    # Завершаем состояние
    await state.finish()


@dp.message_handler(state=EnterChatRename.chat_name)
async def process_rename_chat_name(message: Message, state: FSMContext):
    """
    Обрабатывает запрос на переименование чата.

    При получении нового имени для чата, проверяет его на пустоту, затем обновляет имя чата в базе данных
    и отправляет уведомление о том, что переименование успешно завершено.
    """
    user_id = message.from_user.id  # Получаем ID пользователя
    chat_name = message.text.strip()  # Получаем новое имя чата

    if not chat_name:
        # Если название пустое, запрашиваем ввод заново
        await message.answer("Название чата не может быть пустым. Пожалуйста, введите название.")
        return

    # Получаем данные из состояния (chat_id)
    data = await state.get_data()
    chat_id = data["chat_id"]  # Получаем ID чата из состояния

    # Обновляем имя чата в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE chats SET name = $1, updated_at = NOW() WHERE id = $2 AND user_id = $3",
        chat_name, chat_id, user_id
    )
    await conn.close()

    # Подтверждаем успешное переименование чата
    await message.answer(f'Чат успешно переименован в "_{chat_name}_".\n\n*Введите запрос ⤵️*', parse_mode="Markdown")

    # Завершаем состояние
    await state.finish()


@dp.callback_query_handler(text="delete_chat")
async def delete_chat(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление текущего чата пользователя.

    При получении запроса, запрашивает у пользователя подтверждение на удаление чата.
    Если пользователь подтверждает удаление, удаляет чат из базы данных.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем имя текущего чата пользователя
    conn = await db.get_conn()
    chat = await conn.fetchrow("SELECT name FROM chats WHERE id = $1", user["current_chat_id"])
    await conn.close()

    if not chat:
        # Если чатов нет, сообщаем пользователю
        await call.message.edit_text("Активных чатов нет. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
        return

    chat_name = chat["name"]  # Извлекаем название чата

    # Запрашиваем у пользователя подтверждение удаления
    confirmation_text = f'Вы действительно хотите удалить чат: "*{chat_name}*?"'
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Удалить чат", callback_data="confirm_delete_chat"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Отправляем сообщение с запросом подтверждения удаления
    await call.message.edit_text(confirmation_text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(text="confirm_delete_chat")
async def confirm_delete_chat(call: CallbackQuery):
    """
    Подтверждает удаление чата пользователя.

    При получении запроса на подтверждение удаления, удаляет текущий чат пользователя из базы данных
    и отправляет уведомление об успешном удалении.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Удаляем текущий чат пользователя из базы данных
    conn = await db.get_conn()
    await conn.execute(
        "DELETE FROM chats WHERE id = $1", user["current_chat_id"]

    )
    await conn.close()

    # Подтверждаем успешное удаление чата
    await call.message.edit_text("Чат успешно удален. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()




