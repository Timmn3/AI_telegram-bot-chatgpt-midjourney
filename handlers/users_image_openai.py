from io import BytesIO

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from openai import OpenAI
import base64
import tempfile
import os

from config import OPENAPI_TOKEN
from create_bot import dp, bot, logger
from handlers.users import not_enough_balance
from utils import db
from utils.ai import get_translate


# Инициализация клиента OpenAI
client = OpenAI(api_key=OPENAPI_TOKEN)

# FSM для управления состоянием генерации изображений
class ImageGenerationStates(StatesGroup):
    WAITING_FOR_PROMPT = State()
    WAITING_FOR_IMAGES = State()
    WAITING_FOR_MASK = State()


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
    print("🎨Image OpenAI✅")
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

    await callback_query.message.answer("✍️ Введите текстовое описание для генерации изображения.")
    await ImageGenerationStates.WAITING_FOR_PROMPT.set()


# Генерация изображения на основе промпта
@dp.message_handler(state=ImageGenerationStates.WAITING_FOR_PROMPT)
async def generate_image_from_prompt(message: types.Message, state: FSMContext):
    prompt = message.text.strip()
    prompt = await get_translate(prompt)  # Переводим запрос на английский
    user_id = message.from_user.id

    if not prompt:
        await message.answer("❌ Описание не может быть пустым. Попробуйте снова.")
        return

    user = await db.get_user(user_id)
    settings = user["image_openai_settings"]
    size = settings.get("size", "1024x1024")
    quality = settings.get("quality", "medium")
    background = settings.get("background", "opaque")

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            background=background
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)

        # Отправляем изображение пользователю
        await bot.send_photo(chat_id=user_id, photo=types.InputFile(BytesIO(image_bytes), filename="generated.png"))

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

    await callback_query.message.answer("📸 Пришлите изображения, которые хотите использовать как основу для редактирования.")
    await ImageGenerationStates.WAITING_FOR_IMAGES.set()


# Обработка загрузки изображений
@dp.message_handler(content_types=['photo'], state=ImageGenerationStates.WAITING_FOR_IMAGES)
async def handle_images_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    photo = message.photo[-1]  # Самое большое изображение
    file = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file.file_path)

    temp_dir = tempfile.TemporaryDirectory()
    image_path = os.path.join(temp_dir.name, f"{user_id}.png")

    with open(image_path, 'wb') as new_file:
        new_file.write(downloaded_file.getvalue())

    await state.update_data(images_paths=[image_path], temp_dir=temp_dir)
    await message.answer("✍️ Теперь введите текстовое описание, как вы хотите изменить это изображение.")
    await ImageGenerationStates.WAITING_FOR_PROMPT.set()


# Обработка маски для inpainting
@dp.callback_query_handler(lambda c: c.data == "use_mask_for_edit")
async def use_mask_for_edit(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("🖼️ Загрузите маску (PNG с альфа-каналом). Прозрачные области будут изменены.")
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