"""
Очистка старых сообщений пользователей от системного промпта.

Запуск (dry run — только показать, не менять):
    python utils/clean_messages.py

Запуск с применением изменений:
    python utils/clean_messages.py --apply
"""
import asyncio
import re
import sys
sys.path.insert(0, '.')

import asyncpg
import config

LANG_MARKERS = [
    "\nсоставь ответ на русском языке",
    "\ncompose an answer in English",
]

PREFIX_PATTERN = re.compile(
    r'^(Ключевые слова[^\n]+\n\n|Ранее в этом чате обсуждалось:.*?\n\n)+',
    re.DOTALL
)


def extract_user_text(raw: str) -> str:
    text = raw
    for marker in LANG_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            break
    text = PREFIX_PATTERN.sub('', text)
    return text.strip()


async def main(apply: bool):
    conn = await asyncpg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_DATABASE,
    )

    rows = await conn.fetch(
        "SELECT id, text FROM messages WHERE user_id IS NOT NULL"
    )

    dirty = [(r['id'], r['text']) for r in rows
             if any(m in r['text'] for m in LANG_MARKERS)]

    print(f"Всего user-сообщений: {len(rows)}")
    print(f"Загрязнённых (с промптом): {len(dirty)}")
    print()

    for msg_id, raw in dirty[:5]:
        cleaned = extract_user_text(raw)
        print(f"--- ID {msg_id} ---")
        print(f"  ДО  : {repr(raw[:120])}...")
        print(f"  ПОСЛЕ: {repr(cleaned[:120])}")
        print()

    if len(dirty) > 5:
        print(f"  ... и ещё {len(dirty) - 5} сообщений\n")

    if not apply:
        print("Dry run — изменения НЕ применены. Запусти с --apply чтобы применить.")
        await conn.close()
        return

    updated = 0
    for msg_id, raw in dirty:
        cleaned = extract_user_text(raw)
        if cleaned != raw:
            await conn.execute(
                "UPDATE messages SET text = $1 WHERE id = $2",
                cleaned, msg_id
            )
            updated += 1

    await conn.close()
    print(f"Обновлено {updated} сообщений.")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply))
