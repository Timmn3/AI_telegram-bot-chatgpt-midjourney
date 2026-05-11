import logging
import openai
from openai import OpenAI
from aiogram import Bot  # Для работы с ботом
from aiogram.types.input_file import InputFile
from googletranslatepy import Translator  # Библиотека для перевода текста
import speech_recognition as sr  # Библиотека для распознавания речи
from pydub import AudioSegment  # Библиотека для работы с аудио
import tempfile
import os
from config import OPENAPI_TOKEN, midjourney_webhook_url, MJ_API_KEY, TNL_API_KEY, TOKEN, NOTIFY_URL, TNL_API_KEY1, \
    ADMINS_CODER, PROJECT_MANAGER  # Импорт конфигураций и токенов
from utils import db  # Работа с базой данных
from utils.mj_apis import (GoAPI, ApiFrame, MidJourneyAPI, _strip_user_flags,
                            _retry_state, MJ_MAX_RETRIES, MJ_WATCHDOG_TIMEOUT,
                            friendly_mj_error)
import asyncio

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Устанавливаем API-ключ для OpenAI
client = OpenAI(api_key=OPENAPI_TOKEN)

# Инициализация MidJourneyAPI
mj_api = MidJourneyAPI(primary_api="legnext")

# Функция для получения MidJourney токена в зависимости от индекса
def get_mj_token(index):
    if index == 0:
        return TNL_API_KEY
    elif index == 1:
        return TNL_API_KEY1


# Добавление действия пользователя в базу данных (например, создание изображения или запрос в AI)
async def add_mj_action(user_id, action_type):
    """
    Создаём запись действия и НЕ блокируем event loop при уведомлении внешнего сервиса:
    requests.post вынесен в отдельный поток через asyncio.to_thread.
    """
    action_id = await db.add_action(user_id, action_type)  # Сохраняем действие в базе
    try:
        # Отправляем уведомление о новом действии (в отдельном потоке)
        await asyncio.to_thread(requests.post, NOTIFY_URL + f"/action/{action_id}")
    except Exception:
        pass
    return action_id


my_bot = Bot(TOKEN)

# Функция для отправки сообщения об ошибке админу бота
async def send_error(text):
    await my_bot.send_message(ADMINS_CODER, text)


# Функция для перевода текста на английский язык
async def get_translate(text):
    # Заменяем длинное тире на два дефиса
    text = text.replace("—", "--")

    # Выделяем параметры
    special_tags = re.findall(r'--\w+(?: [\w:]+)?', text)
    clean_text = re.sub(r'--\w+(?: [\w:]+)?', '', text).strip()

    # Переводим
    translator = Translator(target="en")
    translated = translator.translate(clean_text)

    # Убираем пробел перед дефисами
    translated = re.sub(r'\s+-(\w)', r'-\1', translated)

    # Склеиваем всё
    result = f"{translated.strip()} {' '.join(special_tags)}"
    return result


import base64
import requests
import re


# Функция для конвертации изображения в base64
def image_url_to_base64(url: str, *, timeout: int = 15) -> str | None:
    """
    Преобразует URL изображения в data: URI (base64).

    - Если url уже data:image/...;base64,... — возвращаем как есть (не делаем requests.get).
    - Если схема не http/https — пропускаем, чтобы не валить весь запрос.
    """
    if not url:
        return None

    # Уже base64 data-uri
    if url.startswith("data:image"):
        return url

    # Неизвестная/неподдерживаемая схема
    if not (url.startswith("http://") or url.startswith("https://")):
        logger.warning(f"image_url_to_base64: unsupported url schema: {url!r}")
        return None

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        image_base64 = base64.b64encode(response.content).decode("utf-8")
        return f"data:image/jpeg;base64,{image_base64}"
    except Exception as e:
        logger.exception(f"image_url_to_base64: failed url={url!r} err={e}")
        return None



# Функция для отправки запроса в ChatGPT
async def get_gpt(messages, model):
    status = True
    tokens = 0
    content = ""

    try:
        model_map = {
            '5-mini': 'gpt-5-mini',
            '5': 'gpt-5.2',
        }

        # Проверка и обработка изображений в сообщении пользователя
        for message in messages:
            if message["role"] == "user":
                if isinstance(message["content"], list):  # Проверяем, является ли content списком
                    logger.info('message["content"] is list')
                    # Обрабатываем список контента
                    image_urls = [
                        item["image_url"]["url"]
                        for item in message["content"]
                        if item["type"] == "image_url"
                    ]
                    text_content = " ".join(
                        item["text"]
                        for item in message["content"]
                        if item["type"] == "text"
                    ).strip()
                else:
                    logger.info('message["content"] is string')
                    # Ищем ссылки на изображения в строке
                    image_urls = re.findall(r'(https?://\S+\.(?:jpg|jpeg|png|gif))', message["content"])
                    text_content = re.sub(r'(https?://\S+\.(?:jpg|jpeg|png|gif))', '', message["content"]).strip()

                # Преобразуем сообщение в формат с type: image_url
                new_content = []

                # Добавляем текст (если есть)
                if text_content:
                    new_content.append({"type": "text", "text": text_content})

                # Добавляем изображения в формате base64
                for url in image_urls:
                    base64_image = image_url_to_base64(url)
                    if base64_image:
                        new_content.append({
                            "type": "image_url",
                            "image_url": {"url": base64_image}
                        })

                # Заменяем оригинальное сообщение на преобразованное
                message["content"] = new_content

        logger.info(f'MESSAGES: {messages}')
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=f"{model_map[model]}",
                messages=messages[-10:]  # Последние 10 сообщений
            )
        except Exception as e:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=f"{model_map['5']}",
                messages=messages[-10:]  # Последние 10 сообщений
            )
            logging.error(f'ChatGPT Error model {model} \n {e}')

        content = response.choices[0].message.content  # Получаем ответ
        tokens = response.usage.total_tokens  # Получаем количество использованных токенов

    except openai.OpenAIError as e:
        status = False
        error_message = str(e)  # Преобразуем исключение в строку
        logging.error(f'ChatGPT Error {error_message}')
        if "insufficient_quota" in error_message:
            await my_bot.send_message(PROJECT_MANAGER, "⚠️ Внимание! Баланс ChatGPT исчерпан. Необходимо его пополнить! 💳")
        else:
            content = "Генерация текста временно недоступна, повторите запрос позднее."

    return {"status": status, "content": content, "tokens": tokens}  # Возвращаем результат


# Функция для отправки запроса в MidJourney
async def get_mdjrny(prompt, user_id):
    logger.info(f"[MJ] STEP 1 — исходный запрос пользователя: {prompt!r}")

    prompt = _strip_user_flags(prompt)
    logger.info(f"[MJ] STEP 1.1 — после очистки от пользовательских флагов: {prompt!r}")

    gpt_prompt = (
        f"Мне нужно сгенерировать изображение в Midjourney: {prompt}, "
        "составь для меня качественный промпт для Midjourney для этого изображения. "
        "НЕ УКАЗЫВАЙ В ПРОМТЕ ВЕРСИЮ. "
        "Верни ТОЛЬКО текст промпта на английском, без пояснений и вступительных фраз."
    )
    logger.info(f"[MJ] STEP 2 — отправляю в ChatGPT (gpt-5.2): {gpt_prompt!r}")

    gpt_messages = [{"role": "user", "content": gpt_prompt}]
    gpt_result = await get_gpt(gpt_messages, model='5')

    logger.info(f"[MJ] STEP 3 — ответ ChatGPT: status={gpt_result['status']}, content={gpt_result['content']!r}")

    if gpt_result["status"] and gpt_result["content"]:
        enhanced_prompt = gpt_result["content"]
        logger.info(f"[MJ] STEP 4 — улучшенный промпт идёт в Midjourney: {enhanced_prompt!r}")
    else:
        enhanced_prompt = await get_translate(prompt)
        logger.warning(f"[MJ] STEP 4 — ChatGPT недоступен, fallback-перевод: {enhanced_prompt!r}")

    request_id = await db.add_action(user_id, "image", "imagine")
    response = await mj_api.imagine(enhanced_prompt, request_id)
    logger.info(f"[MJ] STEP 5 — ответ Midjourney API: {response}")
    # Сохраняем промпт и запускаем watchdog: если за MJ_WATCHDOG_TIMEOUT не пришёл
    # webhook от Legnext (status=completed/failed обновляет get_response в БД) — повторяем запрос.
    _retry_state[request_id] = {'prompt': enhanced_prompt, 'count': 0, 'user_id': user_id}
    asyncio.create_task(_run_mj_watchdog(request_id))
    return response


async def _run_mj_watchdog(action_id: int):
    """Через MJ_WATCHDOG_TIMEOUT секунд проверяет, пришёл ли webhook от Legnext.
    Если нет — делает retry того же промпта (до MJ_MAX_RETRIES раз)."""
    try:
        await asyncio.sleep(MJ_WATCHDOG_TIMEOUT)

        action = await db.get_action(action_id)
        if action and action.get('get_response'):
            _retry_state.pop(action_id, None)
            return

        state = _retry_state.get(action_id)
        if not state:
            return

        if state['count'] >= MJ_MAX_RETRIES:
            logger.warning(f"[MJ watchdog] action {action_id}: лимит попыток исчерпан, показываю ошибку")
            try:
                await my_bot.send_message(state['user_id'], friendly_mj_error('timeout'))
            finally:
                _retry_state.pop(action_id, None)
            return

        state['count'] += 1
        # На retry упрощаем промпт — убираем все --флаги (GPT мог сгенерить кривые,
        # Legnext мог ломаться на парсинге). Бот сам добавит --v 8.1 в imagine().
        simplified_prompt = _strip_user_flags(state['prompt'])
        logger.info(f"[MJ watchdog] action {action_id}: webhook не пришёл за "
                    f"{MJ_WATCHDOG_TIMEOUT}s, retry {state['count']}/{MJ_MAX_RETRIES} "
                    f"(promt simplified: {simplified_prompt!r})")
        try:
            await my_bot.send_message(state['user_id'],
                                      "🔄 Сервис задержался, повторяю ...")
            await mj_api.imagine(simplified_prompt, action_id)
            # Обновляем state, чтобы при следующем retry (если будет) использовался уже упрощённый
            state['prompt'] = simplified_prompt
            asyncio.create_task(_run_mj_watchdog(action_id))
        except Exception as e:
            logger.exception(f"[MJ watchdog] retry call failed for action {action_id}: {e}")
            try:
                await my_bot.send_message(state['user_id'], friendly_mj_error('timeout'))
            finally:
                _retry_state.pop(action_id, None)
    except Exception as e:
        logger.exception(f"[MJ watchdog] unexpected error for action {action_id}: {e}")


# Функция для выбора и улучшения изображения в MidJourney
async def get_choose_mdjrny(task_id, image_id, user_id):
    """
    upscale через mj_api — корутина, не блокирует event loop.
    """
    action_id = await db.add_action(user_id, "image", "upscale")  # Сохраняем действие в базе данных
    response = await mj_api.upscale(task_id, image_id, action_id)  # Отправляем запрос на улучшение изображения
    return response


# Функция для нажатия кнопок MidJourney (вариации или улучшения)
async def press_mj_button(button, buttonMessageId, user_id, api_key_number):
    """
    Нажатие на кнопку MJ. Внешний вызов requests.post вынесен в отдельный поток,
    чтобы не блокировать обработку других апдейтов.
    """
    action_id = await db.add_action(user_id, "image", "imagine")  # Сохраняем действие в базе данных
    status = True
    api_key = get_mj_token(api_key_number)  # Получаем токен
    try:
        payload = {
            "button": button,
            "buttonMessageId": buttonMessageId,
            "ref": str(action_id),
            "webhookOverride": midjourney_webhook_url + "/button"
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        # Вынесли синхронный HTTP-запрос в отдельный поток
        res = await asyncio.to_thread(
            requests.post,
            "https://api.justimagineapi.org/v1/button",
            json=payload,
            headers=headers,
            timeout=30
        )
        res = res.json()
    except requests.exceptions.JSONDecodeError:
        status = False  # Ошибка при обработке JSON
    except Exception:
        status = False
    return status


"""Работа с голосовыми сообщениями"""
# Функция для преобразования голосового сообщения в текст
def voice_to_text(file_path):
    recognizer = sr.Recognizer()
    audio = AudioSegment.from_file(file_path)

    # Сохраняем аудио как временный wav-файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav_file:
        audio.export(temp_wav_file.name, format="wav")
        temp_wav_file_path = temp_wav_file.name

    with sr.AudioFile(temp_wav_file_path) as source:
        audio_data = recognizer.record(source)

    os.remove(temp_wav_file_path)  # Удаляем временный файл

    try:
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        return text
    except sr.UnknownValueError:
        return "Не удалось распознать речь"
    except sr.RequestError:
        return "Ошибка запроса к сервису распознавания"


def text_to_speech(text, model="tts-1", voice="onyx"):
    # Создаем временный файл для аудио
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
        temp_audio_path = temp_audio_file.name

    # Запрос к OpenAI для создания аудио
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text
    )

    # Сохраняем результат в файл
    response.stream_to_file(temp_audio_path)
    audio_file = InputFile(temp_audio_path)

    return audio_file
