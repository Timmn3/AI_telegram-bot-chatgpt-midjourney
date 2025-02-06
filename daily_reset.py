import asyncio  # Модуль для работы с асинхронными операциями

import config  # Импорт конфигураций, включая информацию о подписках
from utils.db import get_conn  # Импорт функции для получения подключения к базе данных


# Основная асинхронная функция, которая выполняет сброс лимитов
async def main():
    
    # Подключаемся к базе данных
    conn = await get_conn()

    # Сбрасываем лимит бесплатных токенов для ChatGPT до 10,000 у всех пользователей
    await conn.execute("UPDATE users SET  = ")

    # Для всех подписок обновляем лимит запросов к MidJourney
    for sub in config.sub_types:
        # Обновляем количество запросов в MidJourney (mj) для пользователей, у которых активна подписка
        await conn.execute("UPDATE users SET mj = $1 WHERE sub_time > NOW() and sub_type = $2", config.sub_types[sub]["mj"], sub)

    # Закрываем соединение с базой данных
    await conn.close()


# Если файл запускается как скрипт, выполняем функцию main
if __name__ == "__main__":
    asyncio.run(main())
