import base64
import logging
from datetime import datetime, timedelta
from typing import List
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ChatActions, ContentType, MediaGroup, Update, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext
import re
import tempfile
import os

from six import BytesIO

from handlers.users import not_enough_balance
from states.user import EnterChatName, EnterChatRename
from utils import db, ai, more_api, pay  # Импорт утилит для взаимодействия с БД и внешними API
from states import user as states  # Состояния FSM для пользователя
import keyboards.user as user_kb  # Клавиатуры для взаимодействия с пользователями
from config import bot_url, TOKEN, NOTIFY_URL, bug_id, PHOTO_PATH, MJ_PHOTO_BASE_URL, ADMINS_CODER
from create_bot import dp  # Диспетчер из create_bot.py
from utils.ai import mj_api, text_to_speech, voice_to_text, client
from aiogram.utils.exceptions import CantParseEntities
import html
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from create_bot import dp, bot

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


def calculate_token_cost(size, quality):
    cost_map = {
        ("1024x1024", "low"): 272,
        ("1024x1024", "medium"): 1056,
        ("1024x1024", "high"): 4160,
        ("1536x1024", "low"): 400,
        ("1536x1024", "medium"): 1568,
        ("1536x1024", "high"): 6208,
        ("1024x1536", "low"): 408,
        ("1024x1536", "medium"): 1584,
        ("1024x1536", "high"): 6240
    }
    return cost_map.get((size, quality), 1056)  # default to medium


# Inline-меню для "Изображения от OpenAI"
image_openai_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Генерации изображения", callback_data="generate_image_prompt"),
            InlineKeyboardButton(text="Редактировать изображение", callback_data="edit_image"),
        ],
        [
            InlineKeyboardButton(text="Настройки", callback_data="image_settings"),
        ],
    ]
)

# Inline-меню для настроек
settings_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="/size — Выбрать размер", callback_data="set_size"),
            InlineKeyboardButton(text="/quality — Выбрать качество", callback_data="set_quality"),
        ],
        [
            InlineKeyboardButton(text="/background — Выбрать фон", callback_data="set_background"),
        ],
        [
            InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu"),
        ],
    ]
)

# Inline-клавиатура для выбора размера
size_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="1024x1024", callback_data="size_1024x1024"),
            InlineKeyboardButton(text="1536x1024", callback_data="size_1536x1024"),
            InlineKeyboardButton(text="1024x1536", callback_data="size_1024x1536"),
        ],
        [
            InlineKeyboardButton(text="Назад", callback_data="back_to_settings"),
        ]
    ]
)

@dp.callback_query_handler(lambda c: c.data.startswith("set_size"))
async def handle_set_size(callback_query: CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="Выберите размер изображения:",
        reply_markup=size_keyboard
    )

class ImageGenerationStates(StatesGroup):
    WAITING_FOR_PROMPT = State()

@dp.callback_query_handler(lambda c: c.data == "generate_image_prompt")
async def handle_generate_image_prompt(callback_query: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        """<b>Введите запрос для генерации изображения</b>
<i>Например:</i> <code>Замерзшее бирюзовое озеро вокруг заснеженных горных вершин</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16 ">Подробная инструкция.</a></u>""",
        disable_web_page_preview=True,
    )
    await ImageGenerationStates.WAITING_FOR_PROMPT.set()


@dp.callback_query_handler(lambda c: c.data == "image_settings")
async def handle_image_settings(callback_query: CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите параметры для настройки:",
        reply_markup=settings_keyboard,
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_main_menu")
async def back_to_main_menu(callback_query: CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="Выберите действие:",
        reply_markup=image_openai_menu
    )


# Inline-клавиатура для выбора качества
quality_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Low", callback_data="quality_low"),
         InlineKeyboardButton(text="Medium", callback_data="quality_medium"),
         InlineKeyboardButton(text="High", callback_data="quality_high")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_settings")]
    ]
)


@dp.callback_query_handler(lambda c: c.data.startswith("set_quality"))
async def handle_set_quality(callback_query: CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="Выберите качество изображения:",
        reply_markup=quality_keyboard
    )


@dp.callback_query_handler(lambda c: c.data.startswith("quality_"))
async def handle_quality_selection(callback_query: CallbackQuery, state: FSMContext):
    selected_quality = callback_query.data.replace("quality_", "")
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал качество: {selected_quality}")

    async with state.proxy() as data:
        data['quality'] = selected_quality

    await bot.answer_callback_query(callback_query.id, text=f"Выбрано качество: {selected_quality}")
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="Выберите параметры для настройки:",
        reply_markup=settings_keyboard
    )


@dp.message_handler(state="*", text="🖼️Изображения от OpenAI✅")
@dp.message_handler(state="*", text="🖼️Изображения от OpenAI")
@dp.message_handler(state="*", commands="image_openai")
async def gen_image_openai(message: Message, state: FSMContext):
    await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "image_openai")  # Устанавливаем Изображения от OpenAI как основной AI
    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя

    # Проверяем наличие токенов и подписки
    if user["image_openai"] <= 0 and user["free_image_openai"] <= 0:
        await not_enough_balance(message.bot, message.from_user.id, "image_openai")  # Сообщаем об исчерпании лимита
        return

    # Отправляем Inline-меню
    await message.answer("Выберите действие:", reply_markup=image_openai_menu)


@dp.message_handler(state=ImageGenerationStates.WAITING_FOR_PROMPT)
async def process_image_prompt(message: Message, state: FSMContext):
    user_id = message.from_user.id

    user = await db.get_user(user_id)

    if user["image_openai"] <= 0 and user["free_image_openai"] <= 0:
        await not_enough_balance(message.bot, user_id, "image_openai")
        return

    prompt = message.text.strip()

    logger.info(f"Получен промпт для генерации изображения от пользователя {user_id}: {prompt}")

    settings = user["image_openai_settings"]
    size = settings.get("size", "1024x1024")
    quality = settings.get("quality", "medium")
    background = settings.get("background", "opaque")

    try:
        # Генерируем изображение
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            format="png",
            background=background,
        )

        image_base64 = response.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        logger.info(f"Изображение успешно сгенерировано для пользователя {user_id}")

        # Отправляем изображение
        await message.bot.send_photo(
            chat_id=user_id,
            photo=InputFile(BytesIO(image_bytes), filename="image.png")
        )

        image_type = size, quality, background

        # Здесь можно сохранить в БД информацию о генерации
        await db.add_action(user_id, "image_openai", image_type)

        # Уменьшаем количество доступных токенов/лимитов
        await db.decrease_image_openai_balance(user_id)

    except Exception as e:
        logger.error(f"Ошибка при генерации изображения для пользователя {user_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при генерации изображения. Попробуйте позже.")

    finally:
        await state.finish()