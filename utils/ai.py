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
from utils.mj_apis import GoAPI, ApiFrame, MidJourneyAPI


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Устанавливаем API-ключ для OpenAI
client = OpenAI(api_key=OPENAPI_TOKEN)

# Инициализация MidJourneyAPI
mj_api = MidJourneyAPI(primary_api="goapi")  # Начнем с GoAPI

# Функция для получения MidJourney токена в зависимости от индекса
def get_mj_token(index):

    if index == 0:
        return TNL_API_KEY
    elif index == 1:
        return TNL_API_KEY1


# Добавление действия пользователя в базу данных (например, создание изображения или запрос в AI)
async def add_mj_action(user_id, action_type):

    action_id = await db.add_action(user_id, action_type)  # Сохраняем действие в базе
    try:
        requests.post(NOTIFY_URL + f"/action/{action_id}")  # Отправляем уведомление о новом действии
    except:
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
def image_url_to_base64(url):
    response = requests.get(url)
    if response.status_code == 200:
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        return f"data:image/jpeg;base64,{image_base64}"  # Используйте правильный MIME-тип (jpeg/png)
    return None


# Функция для отправки запроса в ChatGPT
async def get_gpt(messages, model):
    status = True
    tokens = 0
    content = ""

    try:
        model_map = {
            '4o-mini': 'gpt-4o-mini',
            '4_1': 'gpt-4.1',
            'o1': 'o1',
            'o3-mini': 'o3-mini'
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

        if model in {'o1'}:
            if messages and messages[0]["role"] == "system":
                messages[0] = {"role": "user", "content": "You are a helpful assistant."}

        logger.info(f'MESSAGES: {messages}')

        response = client.chat.completions.create(
            model=f"{model_map[model]}",
            messages=messages[-10:]  # Последние 10 сообщений
        )

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

    translated_prompt = await get_translate(prompt)  # Переводим запрос на английский
    request_id = await db.add_action(user_id, "image", "imagine")  # Сохраняем действие в базе данных
    response = await mj_api.imagine(translated_prompt, request_id)  # Отправляем запрос в Midjourney

    return response


# Функция для выбора и улучшения изображения в MidJourney
async def get_choose_mdjrny(task_id, image_id, user_id):

    action_id = await db.add_action(user_id, "image", "upscale")  # Сохраняем действие в базе данных

    response = await mj_api.upscale(task_id, image_id, action_id)  # Отправляем запрос на улучшение изображения
    return response


# Функция для нажатия кнопок MidJourney (вариации или улучшения)
async def press_mj_button(button, buttonMessageId, user_id, api_key_number):
    
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
        res = requests.post("https://api.justimagineapi.org/v1" + "/button", json=payload, headers=headers)  # Отправляем запрос
        res = res.json()
    except requests.exceptions.JSONDecodeError:
        status = False  # Ошибка при обработке JSON
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


