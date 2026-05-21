from io import BytesIO
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from openai import OpenAI
import base64
import tempfile
import os
import json
from config import OPENAPI_TOKEN
from create_bot import dp, bot
from handlers.users import not_enough_balance
from keyboards.user import image_openai_menu, image_settings_menu, size_menu, quality_menu, background_menu, \
    cancel_keyboard

from utils import db
from utils.ai import get_translate
from typing import Literal
import logging

from utils.db import update_image_openai_settings

PERSISTENT_TEMP_DIR = "persistent_temp"
os.makedirs(PERSISTENT_TEMP_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Инициализация клиента OpenAI
# client = OpenAI(api_key=OPENAPI_TOKEN)
from tests.mock_openai import MockOpenAIClient
client = MockOpenAIClient(image_path="photo_test/generated.png")

# FSM для управления состоянием генерации изображений
class ImageGenerationStates(StatesGroup):
    WAITING_FOR_PROMPT = State()
    WAITING_FOR_IMAGES = State()
    WAITING_FOR_MASK = State()
    WAITING_FOR_PROMPT_MASK = State()
    WAITING_FOR_PROMPT_EDIT_IMAGE = State()
    WAITING_FOR_IMAGE_FIRST = State()

# Допустимые значения
ALLOWED_SIZES = {
    "auto",
    "1024x1024", "1536x1024", "1024x1536",
    "256x256", "512x512",
    "1792x1024", "1024x1792"
}

ALLOWED_QUALITY = {
    "standard", "hd", "low", "medium", "high", "auto"
}

ALLOWED_BACKGROUND = {
    "transparent", "opaque", "auto"
}

# Типы для строгой типизации
SizeType = Literal[
    "auto",
    "1024x1024", "1536x1024", "1024x1536",
    "256x256", "512x512",
    "1792x1024", "1024x1792"
]
QualityType = Literal["standard", "hd", "low", "medium", "high", "auto"]
BackgroundType = Literal["transparent", "opaque", "auto"]


# Словарь стоимости токенов в зависимости от размера и качества
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
        ("1024x1536", "high"): 6240,
    }
    return cost_map.get((size, quality), 1056)




# Начало генерации изображения по тексту
@dp.callback_query_handler(lambda c: c.data == "generate_image_prompt")
async def start_generate_image(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    if not await db.has_image_openai_balance(user_id):
        logger.info(f'У пользователя {user_id} нет генераций изображений от OpenAI, передаем меню с покупкой генераций')
        await not_enough_balance(callback_query.bot, user_id, "image_openai")
        return

    await callback_query.message.edit_text("""<b>✍️ Введите текстовое описание для генерации изображения.</b>
<i>Например:</i> <code>Уютный домик на краю пропасти, окружённый цветущими садами и озёрами с отражающимся небом</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                         disable_web_page_preview=True, reply_markup=cancel_keyboard)

    await ImageGenerationStates.WAITING_FOR_PROMPT.set()


def parse_image_settings(settings_str: str) -> dict[str, str]:
    try:
        data = json.loads(settings_str)
    except json.JSONDecodeError:
        data = {}

    size = data.get("size", "1024x1024")
    if size not in ALLOWED_SIZES:
        size = "1024x1024"

    quality = data.get("quality", "medium")
    if quality not in ALLOWED_QUALITY:
        quality = "medium"

    background = data.get("background", "opaque")
    if background not in ALLOWED_BACKGROUND:
        background = "opaque"

    return {
        "size": size,
        "quality": quality,
        "background": background
    }


# Генерация изображения на основе промпта
@dp.message_handler(state=ImageGenerationStates.WAITING_FOR_PROMPT)
async def generate_image_from_prompt(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    prompt = message.text.strip()
    logger.info(f'Генерация изображения OpenAI, Пользователь {user_id}, prompt: {prompt} ')
    prompt = await get_translate(prompt)  # Переводим запрос на английский

    if not prompt:
        await message.answer("❌ Описание не может быть пустым. Попробуйте снова.")
        return

    user = await db.get_user(user_id)

    settings = parse_image_settings(user["image_openai_settings"])
    size: SizeType = settings["size"]
    quality: QualityType = settings["quality"]
    background: BackgroundType = settings["background"]

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            background=background,
            user=str(user_id)
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        # Отправляем изображение пользователю
        await bot.send_photo(chat_id=user_id, photo=types.InputFile(BytesIO(image_bytes), filename="generated.png"))

        # Уменьшаем баланс пользователя
        await db.decrease_image_openai_balance(user_id)
        await db.mark_used_trial(user_id)

        # Сохраняем действие в базе данных
        await db.add_action(user_id, "image_openai", "generate")
        # Логируем действие
        logger.info(f"Пользователь {user_id} сгенерировал изображение: {prompt[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка при генерации изображения для пользователя {user_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при генерации изображения. Попробуйте позже.")

    finally:
        await state.finish()


# Начало редактирования изображения
@dp.callback_query_handler(lambda c: c.data == "edit_image")
async def start_edit_image(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    if not await db.has_image_openai_balance(user_id):
        await not_enough_balance(callback_query.bot, user_id, "image_openai")
        return

    await callback_query.message.edit_text("""<b>📸 Пришлите изображения, которые хотите использовать как основу для редактирования.</b>"
<i>Вы можете:
- Редактировать существующие изображения
- Создавайте новые изображения, используя другие изображения в качестве справочных материалов.</i>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                                           disable_web_page_preview=True, reply_markup=cancel_keyboard)

    await ImageGenerationStates.WAITING_FOR_IMAGES.set()


# Обработка загрузки изображений
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_IMAGES)
async def handle_images_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    images_paths = data.get("images_paths", [])

    if len(images_paths) >= 10:
        await message.answer("⚠️ Вы не можете загрузить больше 10 изображений.")
        return

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    # Сохраняем изображение в постоянной временной папке
    image_filename = f"{user_id}_{len(images_paths)}.png"
    image_path = os.path.join(PERSISTENT_TEMP_DIR, image_filename)

    with open(image_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    images_paths.append(image_path)
    await state.update_data(images_paths=images_paths)

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Завершить загрузку", callback_data="finish_image_upload"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_action"),
    )

    if len(images_paths) == 1:
        await message.answer("🖼️ Изображение загружено. Хотите добавить еще?", reply_markup=keyboard)
    else:
        await message.answer(f"🖼️ Загружено {len(images_paths)} изображений.", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == "finish_image_upload", state=ImageGenerationStates.WAITING_FOR_IMAGES)
async def finish_image_upload(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.edit_text("""<b>✍️Теперь введите текстовое описание, как вы хотите изменить это изображение.
Если несколько изображений, то можно создать новое изображение из них.</b>

<i>Например:</i> <code>Создай подарочную корзину, содержащую предметы с изображений</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                                           disable_web_page_preview=True, reply_markup=cancel_keyboard)
    await ImageGenerationStates.WAITING_FOR_PROMPT_EDIT_IMAGE.set()



@dp.message_handler(state=ImageGenerationStates.WAITING_FOR_PROMPT_EDIT_IMAGE)
async def handle_edit_prompt(message: types.Message, state: FSMContext):
    prompt = message.text.strip()
    user_id = message.from_user.id
    data = await state.get_data()
    images_paths = data.get('images_paths', [])
    mask_path = data.get('mask_path')

    if not images_paths:
        await message.answer("❌ Не найдено изображение для редактирования.")
        return

    user = await db.get_user(user_id)
    settings = parse_image_settings(user["image_openai_settings"])
    size: SizeType = settings["size"]
    quality: QualityType = settings["quality"]
    background: BackgroundType = settings["background"]

    image_file = None
    image_files = []
    mask_file = None

    try:
        # Проверяем наличие всех файлов
        for path in images_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Файл не найден: {path}")
        if mask_path and not os.path.exists(mask_path):
            raise FileNotFoundError(f"Маска не найдена: {mask_path}")

        if mask_path:
            # Редактирование с маской: используем только первое изображение
            image_file = open(images_paths[0], "rb")
            mask_file = open(mask_path, "rb")

            result = client.images.edit(
                model="gpt-image-1",
                image=image_file,
                mask=mask_file,
                prompt=prompt,
                size=size,
                quality=quality,
                background=background
            )
        else:
            # Редактирование с несколькими изображениями
            image_files = [open(p, "rb") for p in images_paths]

            result = client.images.edit(
                model="gpt-image-1",
                image=image_files,
                prompt=prompt,
                size=size,
                quality=quality,
                background=background
            )

        # Получаем результат
        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        # Отправляем изображение пользователю
        await bot.send_photo(
            chat_id=user_id,
            photo=types.InputFile(BytesIO(image_bytes), filename="edited.png")
        )

        # Обновляем статистику
        await db.decrease_image_openai_balance(user_id)
        await db.add_action(user_id, "image_openai", "edit")
        logger.info(f"Пользователь {user_id} отредактировал изображение: {prompt[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка при редактировании изображения для пользователя {user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при редактировании изображения. Попробуйте позже.")

    finally:
        await state.finish()

        # Закрываем все открытые файлы
        if image_file:
            image_file.close()
        if mask_file:
            mask_file.close()
        for f in image_files:
            f.close()

        # Удаляем временные файлы
        for path in images_paths:
            if os.path.exists(path):
                os.remove(path)
        if mask_path and os.path.exists(mask_path):
            os.remove(mask_path)


# Обработка маски для inpainting
@dp.callback_query_handler(lambda c: c.data == "use_mask_for_edit")
async def use_mask_for_edit(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.edit_text("""<b>Вы можете редактировать части изображения, загрузив изображение и маску, указывающую, какие области следует заменить.

🖼️ Сначала загрузите основное изображение.</b>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                                           disable_web_page_preview=True, reply_markup=cancel_keyboard)
    await ImageGenerationStates.WAITING_FOR_IMAGE_FIRST.set()

#  Обработка загрузки основного изображения
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_IMAGE_FIRST)
async def handle_base_image_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    temp_dir = tempfile.TemporaryDirectory()
    image_path = os.path.join(temp_dir.name, f"{user_id}_base.png")

    with open(image_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    await state.update_data(base_image=image_path, temp_dir=temp_dir)
    await message.answer("🖼️ Теперь загрузите маску. Закрашенные области будут изменены.", reply_markup=cancel_keyboard)
    await ImageGenerationStates.WAITING_FOR_MASK.set()

# Обработка загрузки маски
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_MASK)
async def handle_mask_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    base_image_path = data.get("base_image")

    if not base_image_path:
        await message.answer("❌ Основное изображение не найдено. Попробуйте снова.", reply_markup=cancel_keyboard)
        return

    user_id = message.from_user.id
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    mask_path = os.path.join(os.path.dirname(base_image_path), f"{user_id}_mask.png")

    with open(mask_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    await state.update_data(mask_path=mask_path)
    await message.answer("✍️ Теперь отправьте описание того, что вы хотите изменить.", reply_markup=cancel_keyboard)
    await ImageGenerationStates.WAITING_FOR_PROMPT.set()



@dp.callback_query_handler(lambda c: c.data == "cancel_action", state="*")
async def cancel_action_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    current_state = await state.get_state()
    if current_state:
        await state.finish()

    await callback_query.message.edit_text("Выберите действие:", reply_markup=image_openai_menu)

# Обработчик вызова настроек
@dp.callback_query_handler(lambda c: c.data == "image_settings")
async def image_settings_handler(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    settings = parse_image_settings(user["image_openai_settings"])

    size = settings["size"]
    quality = settings["quality"]
    background = settings["background"]

    text = f"⚙️ Текущие настройки изображения:\n\n"
    text += f"📐 Размер: <b>{size}</b>\n"
    text += f"🖼️ Качество: <b>{quality}</b>\n"
    text += f"🎨 Фон: <b>{background}</b>\n\n"
    text += "Выберите, что вы хотите изменить."

    await callback_query.message.edit_text(text, reply_markup=image_settings_menu, parse_mode="HTML")

# Обработчики подменю
@dp.callback_query_handler(lambda c: c.data.startswith("change_"))
async def show_settings_submenu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data_map = {
        "change_size": ("📐 Выберите размер:", size_menu),
        "change_quality": ("🖼️ Выберите качество:", quality_menu),
        "change_background": ("🎨 Выберите фон:", background_menu),
    }

    msg, menu = data_map.get(callback_query.data, ("Неизвестная настройка", None))

    if menu:
        await callback_query.message.edit_text(msg, reply_markup=menu)
    else:
        await callback_query.message.edit_text("❌ Неизвестная настройка.")

#  Обработка выбора параметров
@dp.callback_query_handler(lambda c: c.data.startswith("set_"))
async def update_setting(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data

    key_map = {
        "size": ["set_size_", "$1"],
        "quality": ["set_quality_", "$2"],
        "background": ["set_background_", "$3"],
    }

    for key, [prefix, path] in key_map.items():
        if data.startswith(prefix):
            value = data.replace(prefix, "").replace("_", " ")
            value = value.replace("png", "").strip()

            # Если прозрачность, то значение transparent
            if key == "background" and value == "transparent":
                value = "transparent"
            elif key == "background":
                value = "opaque"

            # Форматируем значение в JSON строку
            json_value = f'"{value}"'

            await update_image_openai_settings(user_id, [key], json_value)

            await image_settings_handler(callback_query)  # Показываем обновлённые настройки
            break

@dp.callback_query_handler(lambda c: c.data == "back_to_settings")
async def back_to_settings(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await image_settings_handler(callback_query)