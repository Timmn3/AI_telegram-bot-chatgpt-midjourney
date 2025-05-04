import asyncio
from utils.db import get_conn

# Пороговые значения токенов
TOKEN_LIMITS = {
    "tokens_4o": 100_000,
    "tokens_o4_mini": 200_000,
    "tokens_4_1": 5000,
    "tokens_o1": 5000
}


async def refill_tokens():
    """
    Проверяет баланс токенов у всех пользователей и пополняет их до лимита, если баланс ниже.
    """
    conn = await get_conn()
    for token_type, limit in TOKEN_LIMITS.items():
        await conn.execute(
            f"""
            UPDATE users
            SET {token_type} = $1
            WHERE {token_type} < $1
            """,
            limit
        )
    await conn.close()


if __name__ == "__main__":
    asyncio.run(refill_tokens())