import string
import random
import logging
from datetime import datetime, timedelta

from aiogram.dispatcher import FSMContext
from aiogram.types import ParseMode, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, Message, CallbackQuery

import config
import keyboards.admin as admin_kb  # Клавиатуры для админских команд
from config import bot_url, ADMINS, ADMINS_CODER
from states.admin import TokenAdding
from utils.ai import mj_api
from create_bot import dp  # Диспетчер для регистрации хендлеров
from tabulate import tabulate  # Модуль для форматирования данных в таблицы
import states.admin as states  # Состояния для административных задач
from utils import db  # Модуль для работы с базой данных
import asyncio

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Фильтрация данных из статистики
def format_statistics(stats):
    result = ""
    for order_type, details in stats.items():
        # Определяем единицу измерения в зависимости от типа заказа
        unit = "запросов" if order_type == "midjourney" else "токенов"

        quantity_map = {
            "100000": "100к",
            "200000": "200к",
            "500000": "500к"
        }

        order_type = "ChatGPT" if order_type == "chatgpt" else "MidJourney"
        result += f"*{order_type}:*\n"
        total_requests = 0
        total_sum = 0

        for quantity, data in details.items():

            total_sum += data['total_amount']
            total_requests += data['count']

            if str(quantity) in quantity_map:
                quantity = quantity_map[str(quantity)]
            result += f"{quantity} {unit}: {data['count']}, на сумму {data['total_amount']}₽\n"
        result += f"*Всего: {total_requests}, на сумму {total_sum}₽*\n"
        result += "\n"
    return result


# Хендлер для переключения основного API
@dp.message_handler(lambda message: message.from_user.id in ADMINS,
                    text=["#switch_to_goapi", "#switch_to_apiframe"]
                    )
async def switch_api_handler(message: Message):
    user_id = message.from_user.id
    if message.text == "#switch_to_goapi":
        try:
            mj_api.set_primary_api("goapi")
            await message.reply("Основной API переключен на **GoAPI**.")
            logging.info(f"API переключено на GoAPI по команде пользователя {user_id}.")
        except ValueError as e:
            await message.reply(f"Ошибка: {e}")
            logging.error(f"Ошибка при переключении на GoAPI: {e}")
    elif message.text == "#switch_to_apiframe":
        try:
            mj_api.set_primary_api("apiframe")
            await message.reply("Основной API переключен на **ApiFrame**.")
            logging.info(f"API переключено на ApiFrame по команде пользователя {user_id}.")
        except ValueError as e:
            await message.reply(f"Ошибка: {e}")
            logging.error(f"Ошибка при переключении на ApiFrame: {e}")


# Хендлер для отображения краткой статистики по пользователям и запросам
@dp.message_handler(lambda message: message.from_user.id in ADMINS,
                    commands="stats"
                    )
async def show_stats(message: Message):
    statistics = (await db.fetch_short_statistics()).replace('None', '0')

    logger.info(statistics)

    await message.answer(statistics, reply_markup=admin_kb.more_stats_kb(), parse_mode=ParseMode.MARKDOWN_V2)


@dp.callback_query_handler(lambda callback: callback.from_user.id in ADMINS,
                           text="stats"
                           )
async def show_stats(callback: CallbackQuery):
    statistics = (await db.fetch_short_statistics()).replace('None', '0')

    logger.info(statistics)

    await callback.message.edit_text(statistics, reply_markup=admin_kb.more_stats_kb(),
                                     parse_mode=ParseMode.MARKDOWN_V2)


# Хендлер для отображения полной статистики по пользователям и запросам
@dp.callback_query_handler(lambda callback: callback.from_user.id in ADMINS,
                           text="more_stats"
                           )
async def show_stats(callback: CallbackQuery):
    statistics = (await db.fetch_statistics()).replace('None', '0')

    logger.info(statistics)

    await callback.message.edit_text(statistics, reply_markup=admin_kb.less_stats_kb(),
                                     parse_mode=ParseMode.MARKDOWN_V2)


# Хендлер для отображения реферальной статистики
@dp.callback_query_handler(is_admin=True, text='admin_ref_menu')
async def admin_ref_menu(call: CallbackQuery):
    inviters_id = await db.get_all_inviters()  # Получаем всех пользователей, у которых есть рефералы
    inviters = []
    for inviter_id in inviters_id:
        inviter = await db.get_ref_stat(inviter_id['inviter_id'])  # Статистика по реферальным ссылкам
        if inviter['all_income'] is None:
            all_income = 0
        else:
            all_income = inviter['all_income']

        # Сохраняем данные по каждому рефералу
        inviters.append(
            {'user_id': inviter_id['inviter_id'], 'refs_count': inviter['count_refs'],
             'orders_count': inviter['orders_count'],
             'all_income': all_income, 'available_for_withdrawal': inviter['available_for_withdrawal']})

    # Сортируем рефералов по заработанным средствам
    sort_inviters = sorted(inviters, key=lambda d: d['all_income'], reverse=True)
    await call.message.answer(
        f'<b>Партнерская статистика</b>\n\n<pre>{tabulate(sort_inviters, tablefmt="jira", numalign="left")}</pre>')  # Таблица с данными
    await call.answer()


# Хендлер для выдачи подписки пользователю через команду
@dp.message_handler(commands="sub", is_admin=True)
async def add_balance(message: Message):
    try:
        # Парсим аргументы команды: ID пользователя и тип подписки
        user_id, sub_type = message.get_args().split(" ")
        if sub_type not in config.sub_types.keys():
            raise ValueError
        user_id = int(user_id)
    except ValueError:
        await message.answer("Команда введена неверно. Используйте /sub {id пользователя} {тип подписки}")
        return

    user = await db.get_user(user_id)  # Получаем пользователя из базы
    if not user:
        return await message.answer("Пользователь не найден")

    # Определяем дату окончания подписки (если текущая подписка уже истекла — начинаем с текущей даты)
    if user["sub_time"] < datetime.now():
        base_sub_time = datetime.now()
    else:
        base_sub_time = user["sub_time"]
    sub_time = base_sub_time + timedelta(days=30)  # Добавляем 30 дней подписки
    tokens = config.sub_types[sub_type]["tokens"]  # Получаем количество токенов для выбранного типа подписки
    mj = config.sub_types[sub_type]["mj"]  # Количество запросов для MidJourney
    await db.update_sub_info(user_id, sub_time, sub_type, tokens, mj)  # Обновляем данные в базе
    await message.answer('Подписка выдана')  # Подтверждение админу


# Хендлер для изменения баланса пользователя через команду
@dp.message_handler(commands="balance", is_admin=True)
async def add_balance(message: Message):
    try:
        # Парсим аргументы команды: ID пользователя и сумму изменения баланса
        user_id, value = message.get_args().split(" ")
        value = int(value)
        user_id = int(user_id)
    except ValueError:
        await message.answer("Команда введена неверно. Используйте /balance {id пользователя} {баланс}")
        return
    await db.add_balance_from_admin(user_id, value)  # Изменение баланса в базе
    await message.answer('Баланс изменён')  # Подтверждение админу


# Хендлер для запуска рассылки сообщений
@dp.message_handler(commands="send")
async def enter_text(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await message.answer("Введите текст рассылки", reply_markup=admin_kb.cancel)  # Запрос текста для рассылки
        await state.set_state(states.Mailing.enter_text)  # Устанавливаем состояние для ввода текста


# Хендлер для ввода текста рассылки и запроса подтверждения
@dp.message_handler(state=states.Mailing.enter_text)
async def start_send(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Отменено")
        await state.finish()  # Завершаем состояние
        return

    await message.answer("Собираю данные пользователей...")

    users = await db.get_users()  # Получаем всех пользователей
    users_list = [{"user_id": user["user_id"]} for user in users]  # Преобразуем в JSON-совместимый формат

    # Сохраняем пользователей в FSMContext
    await state.update_data(users=users_list, text=message.text)  # Сохраняем текст рассылки и пользователей

    total_minutes, total_hours = await calculate_time(len(users), 0.25)

    if total_hours < 1:
        await message.answer(f"Количество пользователей: {len(users)}\n"
                             f"Приблизительное время отправки сообщений {total_minutes} минут ")
    else:
        await message.answer(f"Количество пользователей: {len(users)}\n"
                             f"Приблизительное время отправки сообщений {total_hours} часов")

    # Создание кнопок для согласия
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Да"), KeyboardButton("Нет"))

    # Запрашиваем подтверждение
    await message.answer("Вы хотите продолжить рассылку?", reply_markup=markup)
    await state.set_state(states.Mailing.confirm)  # Переходим в состояние подтверждения


# Хендлер для получения согласия и рассылки сообщений
@dp.message_handler(state=states.Mailing.confirm, text=["Да", "Нет"], is_admin=True)
async def confirm_send(message: Message, state: FSMContext):
    if message.text == "Нет":
        await message.answer("Рассылка отменена.", reply_markup=ReplyKeyboardRemove())
        await state.finish()
        return

    # Извлекаем данные из состояния
    user_data = await state.get_data()
    users = user_data["users"]
    text = user_data["text"]  # Берём сохранённый текст рассылки

    await message.answer("Начал рассылку...", reply_markup=ReplyKeyboardRemove())

    count = 0
    block_count = 0
    await message.bot.send_message(ADMINS_CODER, text)
    await state.finish()  # Завершаем состояние

    # Выполняем рассылку
    for user in users:
        try:
            await message.bot.send_message(user["user_id"], text)  # Используем сохранённый текст
            count += 1
        except:
            block_count += 1  # Считаем пользователей, заблокировавших бота
        await asyncio.sleep(0.1)  # Делаем небольшую паузу между отправками

    # Итог рассылки
    await message.answer(
        f"Количество получивших сообщение: {count}. Пользователей, заблокировавших бота: {block_count}"
    )


async def calculate_time(N, time_per_task):
    """
    Функция для расчета времени выполнения задачи.

    :param N: Количество задач (например, пользователей)
    :param time_per_task: Время на одну задачу (в секундах)
    :return: Время в секундах, минутах и часах
    """
    total_seconds = N * time_per_task
    total_minutes = total_seconds / 60
    total_hours = total_minutes / 60
    return round(total_minutes, 2), round(total_hours, 2)


# Хендлер для создания промокода через команду
@dp.message_handler(commands="freemoney", is_admin=True)
async def create_promocode(message: Message):
    try:
        # Парсим аргументы команды: сумму и количество активаций промокода
        amount, uses_count = message.get_args().split(" ")
        amount = int(amount)
        uses_count = int(uses_count)
    except ValueError:
        return await message.answer("Команда введена неверно. Используйте /freemoney {сумма} {кол-во активаций}")

    # Генерируем случайный промокод
    code = ''.join(random.sample(string.ascii_uppercase, 10))
    await db.create_promocode(amount, uses_count, code)  # Создаем промокод в базе
    promocode_url = f"{bot_url}?start=p{code}"  # Формируем ссылку с промокодом
    await message.answer(f"Промокод создан, ссылка: {promocode_url}")  # Отправляем ссылку админу


# Хендлер для отображения статистики по промокодам через callback
@dp.callback_query_handler(is_admin=True, text='admin_promo_menu')
async def admin_promo_menu(call: CallbackQuery):
    promocodes = await db.get_promo_for_stat()  # Получаем статистику по промокодам
    # Формируем таблицу с промокодами
    await call.message.answer(
        f'<b>Бонус ссылки</b>\n\n<pre>{tabulate(promocodes, tablefmt="jira", numalign="left")}</pre>')
    await call.answer()

# Клавиатура для выбора типа токенов
token_type_kb = ReplyKeyboardMarkup(resize_keyboard=True)
token_type_kb.add(KeyboardButton("tokens_4o"))
token_type_kb.add(KeyboardButton("tokens_4o_mini"))
token_type_kb.add(KeyboardButton("tokens_o1_preview"))
token_type_kb.add(KeyboardButton("tokens_o1_mini"))
token_type_kb.add(KeyboardButton("free_image"))
token_type_kb.add(KeyboardButton("Отмена"))

# Хэндлер для запуска начисления токенов
@dp.message_handler(commands="add_tokens")
async def start_token_adding(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await message.answer("Введите ID пользователя", reply_markup=admin_kb.cancel)
        await TokenAdding.enter_user_id.set()

# Хэндлер для ввода user_id
@dp.message_handler(state=TokenAdding.enter_user_id, is_admin=True)
async def process_user_id(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Отменено")
        await state.finish()
        return

    user_id = message.text.strip()
    user = await db.get_user(int(user_id))

    if not user:
        await message.answer("Пользователь не найден. Введите корректный user_id или напишите 'Отмена'")
        return

    balance_info = (f"Текущий баланс пользователя {user_id}\n"
                    f"tokens_4o: {user['tokens_4o']}\n"
                    f"tokens_4o_mini: {user['tokens_4o_mini']}\n"
                    f"tokens_o1_preview: {user['tokens_o1_preview']}\n"
                    f"tokens_o1_mini: {user['tokens_o1_mini']}\n"
                    f"Генерации 🎨Midjourney: {user['free_image']}")

    await message.answer(balance_info)
    await message.answer("Выберите тип токенов для пополнения:", reply_markup=token_type_kb)
    await state.update_data(user_id=user_id)
    await TokenAdding.choose_token_type.set()

# Хэндлер для выбора типа токенов
@dp.message_handler(state=TokenAdding.choose_token_type, is_admin=True)
async def choose_token_type(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Отменено")
        await state.finish()
        return

    token_type = message.text.strip()
    if token_type not in ["tokens_4o", "tokens_4o_mini", "tokens_o1_preview", "tokens_o1_mini", "free_image"]:
        await message.answer("Выберите тип токенов из предложенных вариантов или напишите 'Отмена'")
        return

    await state.update_data(token_type=token_type)
    await message.answer("Введите количество токенов для начисления:", reply_markup=admin_kb.cancel)
    await TokenAdding.enter_amount.set()

# Хэндлер для ввода количества токенов
@dp.message_handler(state=TokenAdding.enter_amount, is_admin=True)
async def process_amount(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Отменено")
        await state.finish()
        return

    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректное положительное число или напишите 'Отмена'")
        return

    data = await state.get_data()
    user_id = data['user_id']
    token_type = data['token_type']

    await db.add_tokens(int(user_id), token_type, amount)

    user = await db.get_user(int(user_id))
    balance_info = (f"Теперь баланс пользователя {user_id}\n"
                    f"tokens_4o: {user['tokens_4o']}\n"
                    f"tokens_4o_mini: {user['tokens_4o_mini']}\n"
                    f"tokens_o1_preview: {user['tokens_o1_preview']}\n"
                    f"tokens_o1_mini: {user['tokens_o1_mini']}\n"
                    f"Генерации 🎨Midjourney: {user['free_image']}")

    await message.answer(balance_info)

    await state.finish()