from io import BytesIO

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
from keyboards.user import image_openai_menu
from utils import db
from utils.ai import get_translate
from typing import Literal
import logging


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Инициализация клиента OpenAI
client = OpenAI(api_key=OPENAPI_TOKEN)

# FSM для управления состоянием генерации изображений
class ImageGenerationStates(StatesGroup):
    WAITING_FOR_PROMPT = State()
    WAITING_FOR_IMAGES = State()
    WAITING_FOR_MASK = State()

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


# Главное меню для генерации изображений от OpenAI
@dp.message_handler(state="*", text="🎨Image OpenAI✅")
@dp.message_handler(state="*", text="🎨Image OpenAI")
@dp.message_handler(state="*", commands="image_openai")
async def image_openai_menu_handler(message: types.Message, state: FSMContext):
    if state:
        await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "image_openai")  # Устанавливаем ChatGPT как основной AI
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} вызвал Главное меню для генерации изображений от OpenAI")


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
                         disable_web_page_preview=True)

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
        # result = client.images.generate(
        #     model="gpt-image-1",
        #     prompt=prompt,
        #     size=size,
        #     quality=quality,
        #     background=background
        # )
        #
        # image_base64 = result.data[0].b64_json
        # image_bytes = base64.b64decode(image_base64)
        #
        # # Отправляем изображение пользователю
        # await bot.send_photo(chat_id=user_id, photo=types.InputFile(BytesIO(image_bytes), filename="generated.png"))
        # Путь к файлу
        file_path = "photos/generated.png"
        # Отправка фото по пути
        await bot.send_photo(chat_id=user_id, photo=types.InputFile(file_path))

        # Уменьшаем баланс пользователя
        await db.decrease_image_openai_balance(user_id)

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
                                           disable_web_page_preview=True)

    await ImageGenerationStates.WAITING_FOR_IMAGES.set()


# Обработка загрузки изображений
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_IMAGES)
async def handle_images_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    images_paths = data.get("images_paths", [])
    temp_dirs = data.get("temp_dirs", [])

    if len(images_paths) >= 10:
        await message.answer("⚠️ Вы не можете загрузить больше 10 изображений.")
        return

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    temp_dir = tempfile.TemporaryDirectory()
    image_path = os.path.join(temp_dir.name, f"{user_id}_{len(images_paths)}.png")

    with open(image_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    images_paths.append(image_path)
    temp_dirs.append(temp_dir)

    await state.update_data(images_paths=images_paths, temp_dirs=temp_dirs)

    if len(images_paths) < 10:
        await message.answer(f"🖼️ Загружено {len(images_paths)} изображение(й). Продолжайте отправлять изображения (до 10 штук), затем напишите описание.")
    else:
        await message.answer("✅ Максимум изображений загружено. Теперь введите текстовое описание для объединения изображений.")
        await ImageGenerationStates.WAITING_FOR_PROMPT.set()


# @dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_IMAGES)
# async def handle_images_upload(message: types.Message, state: FSMContext):
#     user_id = message.from_user.id
#     photo = message.photo[-1]  # Самое большое изображение
#     file = await bot.get_file(photo.file_id)
#     downloaded_file = await bot.download_file(file.file_path)
#
#     temp_dir = tempfile.TemporaryDirectory()
#     image_path = os.path.join(temp_dir.name, f"{user_id}.png")
#
#     with open(image_path, 'wb') as new_file:
#         new_file.write(downloaded_file.getvalue())
#
#     await state.update_data(images_paths=[image_path], temp_dir=temp_dir)
#     await message.answer("""<b>✍️Теперь введите текстовое описание, как вы хотите изменить это изображение.
# Если несколько изображений, то можно создать новое изображение из них.</b>
#
# <i>Например:</i> <code>Создай подарочную корзину, содержащую предметы с изображений</code>
#
# <u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
#                                            disable_web_page_preview=True)
#
#     await ImageGenerationStates.WAITING_FOR_PROMPT.set()


# Обработка маски для inpainting
@dp.callback_query_handler(lambda c: c.data == "use_mask_for_edit")
async def use_mask_for_edit(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("🖼️ Загрузите маску. Закрашенные области будут изменены.")
    await ImageGenerationStates.WAITING_FOR_MASK.set()


# Обработка загрузки маски
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_MASK)
async def handle_mask_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    temp_dir = tempfile.TemporaryDirectory()
    mask_path = os.path.join(temp_dir.name, f"{user_id}_mask.png")

    with open(mask_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    await state.update_data(mask_path=mask_path, temp_dir=temp_dir)
    await message.answer("Теперь отправьте описание того, что вы хотите изменить.")
    await ImageGenerationStates.WAITING_FOR_PROMPT.set()


# Обработка запроса на редактирование
@dp.message_handler(state=ImageGenerationStates.WAITING_FOR_PROMPT)
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
    settings = user["image_openai_settings"]
    size = settings.get("size", "1024x1024")
    quality = settings.get("quality", "medium")
    background = settings.get("background", "opaque")

    try:
        if mask_path:
            result = client.images.edit(
                model="gpt-image-1",
                image=open(images_paths[0], "rb"),
                mask=open(mask_path, "rb"),
                prompt=prompt,
                size=size,
                quality=quality,
                background=background
            )
        else:
            result = client.images.edit(
                model="gpt-image-1",
                image=[open(p, "rb") for p in images_paths],
                prompt=prompt,
                size=size,
                quality=quality,
                background=background
            )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        await bot.send_photo(chat_id=user_id, photo=types.InputFile(BytesIO(image_bytes), filename="edited.png"))
        await db.decrease_image_openai_balance(user_id)
        await db.add_action(user_id, "image_openai", "edit")

        logger.info(f"Пользователь {user_id} отредактировал изображение: {prompt[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка при редактировании изображения для пользователя {user_id}: {e}", exc_info=True)
        await message.answer("Произошла ошибка при редактировании изображения. Попробуйте позже.")

    finally:
        await state.finish()
        data.get('temp_dir', None) and data['temp_dir'].cleanup()