import base64
from io import BytesIO  # Модуль для работы с потоками данных
import aiohttp  # Для асинхронных HTTP-запросов
import requests  # Для синхронных HTTP-запросов
import hashlib  # Для создания хешей
from config import FKWallet, IMGBB_API_KEY  # Импорт данных кошелька и API-ключа для загрузки изображений


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


# Асинхронная функция для загрузки фотографии на фотохостинг IMGBB
async def upload_photo_to_host(photo):
    
    async with aiohttp.ClientSession() as session:
        payload = {"image": photo}  # Формируем данные для загрузки (фотография)
        # Отправляем запрос на загрузку фотографии на IMGBB
        async with session.post(
                f'https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}', data=payload) as resp:
            data = await resp.json()  # Получаем ответ в формате JSON
            if "data" not in data:  # Проверяем, есть ли данные в ответе
                return "error"  # Если данных нет, возвращаем ошибку
            return data["data"]["url"]  # Возвращаем URL загруженной фотографии
