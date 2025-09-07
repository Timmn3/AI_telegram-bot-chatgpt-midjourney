# AI Telegram Bot (ChatGPT + Midjourney)

> **Короткое описание:** Готовый к продакшену Telegram‑бот, который соединяет ChatGPT и Midjourney; поддерживает подписки, оплаты, реферальную механику и вебхуки на FastAPI.

## ✨ Возможности
- Запросы к **ChatGPT и Midjourney** прямо в Telegram (через внешние API).
- **Оплаты и подписки:** Tinkoff, FreeKassa, PayOK, крипто, Telegram Stars, промокоды/скидки.
- **Реферальная программа** и пополнение баланса с бонусами.
- **FastAPI**‑сервисы вебхуков для оплат и колбэков Midjourney.
- **PostgreSQL** для хранения данных, **APScheduler** для ежедневных задач.
- **Отдельный notify‑сервис** для отложенных уведомлений.

## 🧱 Архитектура (высокоуровнево)
- **Bot** — раннер [`aiogram` v2] в режиме long‑polling (`main.py`).
- **API server** — приложение `FastAPI` для вебхуков оплат и событий Midjourney (`api_server.py`).
- **Notify server** — приложение `FastAPI` для отложенных уведомлений (`notify_server.py`).
- **DB** — PostgreSQL.
- **Scheduler** — APScheduler (ежедневное пополнение токенов и другие cron‑задачи).

```
Telegram ⇄ Aiogram bot
        ↘                ↘
       FastAPI (webhooks)  Notify FastAPI (delayed jobs)
             ↘                ↘
             PostgreSQL  ←— APScheduler
```

## 🚀 Быстрый старт

### 1) Требования
- Python **3.12**
- PostgreSQL 13+
- (Опционально) Nginx / reverse proxy для вебхуков

### 2) Клонирование и установка
```bash
git clone <your-repo-url> ai-telegram-bot
cd ai-telegram-bot
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Настройка окружения
Создайте файл `.env` (рекомендуется) и **никогда не коммитьте секреты**.
Переменные можно экспортировать в оболочке или хранить в секрет‑менеджере.

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=

# OpenAI / LLM provider
OPENAI_API_KEY=

# Midjourney relay (если используется)
MIDJOURNEY_API_KEY=

# Платежи (заполняйте только нужные)
TINKOFF_TERMINAL_ID=
TINKOFF_API_TOKEN=
FREEKASSA_SHOP_ID=
FREEKASSA_SECRET=
PAYOK_SHOP_ID=
PAYOK_SECRET=
LAVA_API_KEY=
LAVA_SHOP_ID=
CRYPTO_ID=
CRYPTO_API_KEY=

# Приложение
ADMINS_CSV=123456789,987654321
LOG_LEVEL=INFO
NOTIFY_URL=http://127.0.0.1:8001

# Postgres
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/your_db
```

> **Подсказка:** Пробросьте эти переменные в слой конфигурации; не хардкодьте креденшелы.
> Если секреты раньше лежали в коде — **ротируйте ключи** перед продом.

### 4) База данных
Создайте БД и запустите начальные SQL/миграции (если есть). Пример:
```bash
createdb your_db
# Запустите миграции или init‑скрипты
```

### 5) Запуск сервисов

**Bot (long‑polling):**
```bash
python main.py
```

**API‑сервер (вебхуки оплат и Midjourney):**
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

**Notify‑сервер (отложенные уведомления):**
```bash
uvicorn notify_server:app --host 0.0.0.0 --port 8001
```

### 6) Проброс вебхуков
Через Nginx/Cloudflare/etc. прокиньте маршруты на API‑сервер, например:
- `POST /api/pay/tinkoff`
- `GET  /api/pay/freekassa`
- `POST /api/pay/lava`
- `POST /api/pay/payok`
- `POST /api/midjourney` и `POST /api/midjourney/{action_id}`
- `POST /api/midjourney/choose`, `POST /api/midjourney/button`
- `POST /api/pay/tinkoff/receipt`

## 🔁 Планировщик (APScheduler)
Ежедневное пополнение токенов и техобслуживание. Проверьте cron‑настройки в коде и при необходимости адаптируйте расписание.

## 🧪 Локальное тестирование
- Используйте `ngrok`/`cloudflared` для туннеля вебхуков в разработке.
- Держите отдельный **тестовый** набор API‑ключей и платежных аккаунтов.

## 🛡️ Чеклист безопасности
- [ ] Секреты — в env/хранилище, **не** в git
- [ ] Ротируйте любые засвеченные ключи
- [ ] Ограничьте IP вебхуков (если поддерживается) или добавьте подписи
- [ ] Включите HTTPS и HSTS на реверс‑прокси
- [ ] Ограничьте админ‑функции бота по ID/ролям

## 📦 Стек
- Aiogram 2 · FastAPI · APScheduler
- PostgreSQL (asyncpg/SQLAlchemy при необходимости)
- Внешние LLM/имидж‑API (ChatGPT, Midjourney)
- Платежные провайдеры (Tinkoff, FreeKassa, PayOK, крипто, Telegram Stars)


