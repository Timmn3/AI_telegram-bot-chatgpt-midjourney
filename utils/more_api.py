import base64
from io import BytesIO  # Модуль для работы с потоками данных
import aiohttp  # Для асинхронных HTTP-запросов
import requests  # Для синхронных HTTP-запросов
import hashlib  # Для создания хешей
from config import FKWallet, IMGBB_API_KEY  # Импорт данных кошелька и API-ключа для загрузки изображений

import os

# Словарь, который сопоставляет валюты с их кодами для FKWallet (кошелек)
fkwallet_currencies = {'qiwi': 63, 'bank_card': 94}


# Функция для создания QR-кода на основе URL и возврата изображения в виде байтового потока
def get_qr_photo(url):

    response = requests.get(
        f'https://api.qrserver.com/v1/create-qr-code/?size=600x600&qzone=2&data={url}')  # Запрос на создание QR-кода
    return BytesIO(response.content)  # Возвращаем изображение QR-кода в формате потока байтов


# Функция для вывода реферального баланса (на кошелек или банковскую карту)
def withdraw_ref_balance(purse, amount, currency):

    # Создаем подпись для запроса на вывод средств
    sign = hashlib.md5(f'{FKWallet.wallet_id}{fkwallet_currencies[currency]}{amount}{purse}{FKWallet.api_key}'.encode())
    # Отправляем запрос на вывод средств через API FKWallet
    response = requests.post('https://fkwallet.com/api_v1.php', data={
        'wallet_id': FKWallet.wallet_id,
        'purse': purse,  # Номер кошелька или карты
        'amount': amount,  # Сумма
        'desc': 'Перевод',  # Описание транзакции
        'currency': fkwallet_currencies[currency],  # Код валюты
        'sign': sign.hexdigest(),  # Подпись для безопасности
        'action': 'cashout'  # Действие — вывод средств
    })
    print(response.json())  # Выводим ответ для отладки
    return response.json()  # Возвращаем JSON-ответ


UPLOAD_DIR = "/var/www/neuronbot/uploads"  # Папка для хранения фото
BASE_URL = "https://neuronbot.ru/uploads"  # Базовый URL для доступа к файлам

async def upload_photo_to_host(photo_url):
    async with aiohttp.ClientSession() as session:
        # Скачиваем изображение с Telegram
        async with session.get(photo_url) as resp:
            if resp.status != 200:
                return "error"

            photo_bytes = await resp.read()
            filename = os.path.basename(photo_url)  # Имя файла из URL
            file_path = os.path.join(UPLOAD_DIR, filename)

        # Сохраняем файл на сервере
        with open(file_path, "wb") as f:
            f.write(photo_bytes)

        return f"{BASE_URL}/{filename}"  # Возвращаем ссылку на загруженный файл
