import asyncpg
import asyncio

DB_USER = "postgres"
DB_PASSWORD = "Niksan03"
DB_DATABASE = "restored_db"
DB_HOST = "localhost"
DB_PORT = 5432  # Укажите порт, если он отличается

async def test_connection():
    try:
        conn = await asyncpg.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            host=DB_HOST,
            port=DB_PORT
        )
        print("✅ Подключение успешно!")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")

asyncio.run(test_connection())
