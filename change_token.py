import asyncio  # Модуль для работы с асинхронными операциями

import requests  # Библиотека для выполнения HTTP-запросов

from config import ya_token  # Импорт OAuth токена Yandex из конфигурационного файла
from utils import db  # Импорт модуля для работы с базой данных


# Основная асинхронная функция для обновления IAM-токена
async def main():
    
    # Отправляем POST-запрос для получения нового IAM-токена от Yandex Cloud
    response = requests.post('https://iam.api.cloud.yandex.net/iam/v1/tokens',
                             headers={'Content-Type': 'application/json'},  # Заголовки запроса
                             json={
                                 "yandexPassportOauthToken": ya_token  # Отправляем OAuth-токен для получения IAM-токена
                             })
    # Сохраняем новый IAM-токен в базе данных
    await db.change_iam_token(response.json()['iamToken'])


# Если файл запускается как скрипт, выполняем функцию main
if __name__ == "__main__":
    asyncio.run(main())
