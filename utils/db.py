from datetime import datetime, date, time, timedelta
import asyncpg
import logging
from zoneinfo import ZoneInfo
from typing import Dict, Any
from asyncpg import Connection
from config import DB_USER, DB_HOST, DB_DATABASE, DB_PASSWORD
import uuid


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Функция для установления соединения с базой данных
async def get_conn() -> Connection:

    return await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE, host=DB_HOST)


# Функция для создания необходимых таблиц в базе данных, если они еще не существуют
async def start():
    # Создание необходимых таблиц
    await create_tables()
    conn: Connection = await get_conn()
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "user_id BIGINT PRIMARY KEY,"
        "username VARCHAR(32),"
        "first_name VARCHAR(64),"
        "balance INT DEFAULT 0,"
        "reg_time INT,"
        "free_image SMALLINT DEFAULT 3,"
        "default_ai VARCHAR(10) DEFAULT 'empty',"
        "inviter_id BIGINT,"
        "ref_balance INT DEFAULT 0,"
        "task_id VARCHAR(1024) DEFAULT '0',"
        "chat_gpt_lang VARCHAR(2) DEFAULT 'ru',"
        "stock_time INT DEFAULT 0,"
        "new_stock_time INT DEFAULT 0,"
        "is_pay BOOLEAN DEFAULT FALSE,"
        "chatgpt_about_me VARCHAR(256) DEFAULT '',"
        "chatgpt_settings VARCHAR(256) DEFAULT '',"
        "sub_time TIMESTAMP DEFAULT NOW(),"
        "sub_type VARCHAR(12),"
        "tokens_4_1 INTEGER DEFAULT 5000,"
        "tokens_o1 INTEGER DEFAULT 5000,"
        "tokens_o3 INTEGER DEFAULT 5000,"
        "tokens_4o INTEGER DEFAULT 200000,"
        "tokens_4o_mini INTEGER DEFAULT 100000,"
        "tokens_o1_preview INTEGER DEFAULT 0,"
        "tokens_o1_mini INTEGER DEFAULT 1000,"
        "tokens_o3_mini INTEGER DEFAULT 200000,"
        "tokens_o4_mini INTEGER DEFAULT 200000,"
        "gpt_model VARCHAR(10) DEFAULT '5',"
        "voice VARCHAR(64) DEFAULT 'onyx',"
        "chatgpt_character VARCHAR(256) DEFAULT '',"
        "mj INTEGER DEFAULT 0,"
        "is_notified BOOLEAN DEFAULT FALSE,"
        "image_openai INTEGER DEFAULT 0,"
        "free_image_openai INTEGER DEFAULT 3,"
        "used_trial BOOLEAN DEFAULT FALSE,"
        "is_subscribed BOOLEAN DEFAULT FALSE,"
        "ref_notifications_enabled BOOLEAN DEFAULT TRUE,"
        "image_openai_settings JSONB DEFAULT '{\"size\": \"1024x1024\", \"quality\": \"medium\", \"background\": \"opaque\"}')"

    )

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS usage("
        "id SERIAL PRIMARY KEY,"  # Уникальный идентификатор действия
        "user_id BIGINT,"  # ID пользователя
        "ai_type VARCHAR(10),"  # Тип нейросети - midjourney, chatgpt
        "image_type VARCHAR(255),"  # Тип действия
        "use_time INT,"  
        "get_response BOOLEAN DEFAULT FALSE,"
        "create_time TIMESTAMP DEFAULT NOW(),"
        "external_task_id VARCHAR(1024))"
    )

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS withdraws(id SERIAL PRIMARY KEY, user_id BIGINT, amount INT, withdraw_time INT)")

    await conn.execute("CREATE TABLE IF NOT EXISTS config(config_key VARCHAR(32), config_value VARCHAR(256))")

    await conn.execute("CREATE TABLE IF NOT EXISTS promocode("
                       "promocode_id SMALLSERIAL,"  # Уникальный идентификатор промокода
                       "amount INTEGER,"  # Сумма, которая может быть получена по промокоду
                       "uses_count SMALLINT,"  # Количество использований промокода
                       "code VARCHAR(10) UNIQUE)")  # Сам код промокода

    await conn.execute("CREATE TABLE IF NOT EXISTS user_promocode("
                       "promocode_id SMALLINT,"  # ID промокода
                       "user_id BIGINT)")  # ID пользователя, связанного с промокодом

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        "id SERIAL PRIMARY KEY,"  # Уникальный идентификатор заказа
        "user_id BIGINT,"  # ID пользователя
        "amount INT,"  # Сумма покупки
        "order_type VARCHAR(10),"  # Тип заказа: 'chatgpt' или 'midjourney'
        "quantity INT,"  # Количество токенов или запросов
        "create_time TIMESTAMP DEFAULT NOW(),"  # Время создания заказа
        "pay_time TIMESTAMP,"  # Время оплаты заказа
        "order_id UUID UNIQUE,"  # Уникальный идентификатор заказа для платежной системы
        "payment_id TEXT"  # ID платежа в системе Tinkoff (изменили на TEXT)
        ")"
    )

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS discount_gpt ("
        "user_id BIGINT PRIMARY KEY,"           # Уникальный идентификатор пользователя
        "is_notified BOOLEAN DEFAULT FALSE,"    # Статус уведомления
        "last_notification TIMESTAMP,"           # Дата и время последнего уведомления
        "used BOOLEAN DEFAULT FALSE)"           # Статус использования скидки
    )

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS discount_mj ("
        "user_id BIGINT PRIMARY KEY,"           # Уникальный идентификатор пользователя
        "is_notified BOOLEAN DEFAULT FALSE,"    # Статус уведомления
        "last_notification TIMESTAMP,"           # Дата и время последнего уведомления
        "used BOOLEAN DEFAULT FALSE)"           # Статус использования скидки
    )

    # Создание таблицы stars
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS stars ("
        "id SERIAL PRIMARY KEY, "
        "user_id BIGINT, "
        "date DATE NOT NULL, "
        "amount INTEGER NOT NULL DEFAULT 1"
        ")"
    )



    # Проверяем наличие токена конфигурации, и если его нет - добавляем значение по умолчанию
    row = await conn.fetchrow("SELECT config_value FROM config WHERE config_key = 'iam_token'")
    if row is None:
        await conn.execute("INSERT INTO config VALUES('iam_token', '1')")
    await conn.close()


# Функция для получения всех пользователей
async def get_users():

    conn: Connection = await get_conn()
    rows = await conn.fetch("SELECT user_id FROM users")
    await conn.close()
    return rows

# Функция для начисления токенов
async def add_tokens(user_id: int, token_type, amount):
    conn = await get_conn()
    await conn.execute(
        f"UPDATE users SET {token_type} = {token_type} + $1 WHERE user_id = $2",
        amount, user_id
    )
    await conn.close()


# Функция для получения информации о пользователе по user_id
async def get_user(user_id):

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row

# Получение информации о выранном голосе
async def get_voice(user_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT voice FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row["voice"] if row else 'onyx'  # Возвращаем только значение или None


# Записываем выбранный голос в базу данных
async def set_voice(user_id, voice):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET voice = $2 WHERE user_id = $1", user_id, voice)
    await conn.close()
    

# Получаем информацию о выбранной модели GPT
async def get_model(user_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT gpt_model FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row["gpt_model"] or "5_mini"


# Записываем выбранную модель GPT в базу данных
async def set_model(user_id, gpt_model):
    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET gpt_model = $2 WHERE user_id = $1", user_id, gpt_model)
    await conn.close()


# Функция для добавления нового пользователя
async def add_user(user_id, username, first_name, inviter_id):
    """
    Регистрируем нового пользователя.
    ChatGPT бесплатный, но доступ выдаём на 14 дней (gpt_access_until).
    """
    conn: Connection = await get_conn()
    await conn.execute(
        """
        INSERT INTO users(
            user_id, username, first_name, reg_time, inviter_id,
            free_image,
            tokens_5, tokens_5_mini,
            gpt_model,
            is_subscribed, used_trial,
            gpt_access_until, gpt_expire_warned
        )
        VALUES (
            $1, $2, $3, $4, $5,
            0,
            200000, 200000,
            '5_mini',
            FALSE, FALSE,
            (NOW() AT TIME ZONE 'utc') + INTERVAL '14 days', FALSE
        )
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id, username, first_name, int(datetime.now().timestamp()), inviter_id
    )
    await conn.close()



# Функция для обновления task_id пользователя
async def update_task_id(user_id, task_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET task_id = $2 WHERE user_id = $1", user_id, task_id)
    await conn.close()


# Функция для обновления флага оплаты пользователя
async def update_is_pay(user_id, is_pay):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET is_pay = $2 WHERE user_id = $1", user_id, is_pay)
    await conn.close()


# Функция для обновления информации о пользователе для ChatGPT
async def update_chatgpt_about_me(user_id, text):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET chatgpt_about_me = $2 WHERE user_id = $1", user_id, text)
    await conn.close()


# Функция для обновления характера ChatGPT
async def update_chatgpt_character(user_id, text):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET chatgpt_character = $2 WHERE user_id = $1", user_id, text)
    await conn.close()


# Функция для обновления настроек ChatGPT пользователя
async def update_chatgpt_settings(user_id, text):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET chatgpt_settings = $2 WHERE user_id = $1", user_id, text)
    await conn.close()


# Функция для изменения AI по умолчанию для пользователя
async def change_default_ai(user_id, ai_type):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET default_ai = $2 WHERE user_id = $1", user_id, ai_type)
    await conn.close()


# Функция для уменьшения количества бесплатных токенов ChatGPT для пользователя
async def remove_free_chatgpt(user_id, tokens):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET tokens_5 = tokens_5 - $2 WHERE user_id = $1", user_id, tokens)
    await conn.close()


# Функция для уменьшения количества токенов ChatGPT у пользователя
async def remove_chatgpt(user_id, tokens, model):

    conn: Connection = await get_conn()
    dashed_model = model.replace("-", "_")
    column = f'tokens_{dashed_model}'

    if column not in {'tokens_5', 'tokens_5_mini'}:
        raise ValueError(f"Invalid model {column}")

    await conn.execute(
        f"""
        UPDATE users
        SET {column} = GREATEST({column} - $2, 0)
        WHERE user_id = $1
        """,
        user_id, tokens
    )
    await conn.close()


# Функция для уменьшения количества бесплатных изображений у пользователя
async def remove_free_image(user_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET free_image = free_image - 1 WHERE user_id = $1", user_id)
    await conn.close()


# Функция для уменьшения количества токенов MidJourney у пользователя
async def remove_image(user_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET mj = mj - 1 WHERE user_id = $1", user_id)
    await conn.close()


# Функция для обновления времени акций у пользователя
async def update_stock_time(user_id, stock_time):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET stock_time = $2 WHERE user_id = $1", user_id, stock_time)
    await conn.close()


# Функция для обновления нового времени акций у пользователя
async def update_new_stock_time(user_id, new_stock_time):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET new_stock_time = $2 WHERE user_id = $1", user_id, new_stock_time)
    await conn.close()


# Функция для уменьшения баланса пользователя на фиксированное значение (10)
async def remove_balance(user_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET balance = balance - 10 WHERE user_id = $1", user_id)
    await conn.close()


# Функция для добавления баланса пользователю администратором
async def add_balance_from_admin(user_id, amount):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET balance = balance + $2 WHERE user_id = $1", user_id, amount)
    await conn.close()


# Функция для добавления баланса пользователю и начисления реферального бонуса, если это не промоакция
async def add_balance(user_id, amount, is_promo=False):

    conn: Connection = await get_conn()
    ref_balance = int(float(amount) * 0.15)
    await conn.execute("UPDATE users SET balance = balance + $2 WHERE user_id = $1", user_id, amount)
    # Скрыто начисление 15% по рефералке при оплатах в db
    # if not is_promo:
    #     await conn.execute(
    #         "UPDATE users SET ref_balance = ref_balance + $2 WHERE user_id = (SELECT inviter_id FROM users WHERE user_id = $1)",
    #         user_id, ref_balance)
    await conn.close()

# Проверка наличия активного заказа со скидкой для пользователя
async def check_discount_order(user_id):

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM sub_orders WHERE user_id = $1 and with_discount = TRUE", user_id)
    await conn.close()
    return row


# Добавление баланса пользователю за счет реферального баланса
async def add_balance_from_ref(user_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET balance = balance + ref_balance, ref_balance = 0 WHERE user_id = $1",
                       user_id)
    await conn.close()

# Функция для получения заказа по payment_id
async def get_order_by_payment_id(payment_id):
    conn = await get_conn()
    row = await conn.fetchrow("SELECT * FROM orders WHERE payment_id = $1", payment_id)
    await conn.close()
    return row



# Изменение языка ChatGPT для пользователя
async def change_chat_gpt_lang(user_id, new_lang):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET chat_gpt_lang = $2 WHERE user_id = $1",
                       user_id, new_lang)
    await conn.close()


# Получение языка ChatGPT для пользователя
async def get_chat_gpt_lang(user_id):
    conn: Connection = await get_conn()
    
    try:
        # Выполняем запрос для получения языка
        result = await conn.fetchval(
            "SELECT chat_gpt_lang FROM users WHERE user_id = $1",
            user_id
        )
        return result  # Возвращаем язык
    except Exception as e:
        logger.error(f"Ошибка при получении языка пользователя {user_id}: {e}")
        raise e
    finally:
        await conn.close()


# Получение статистики по рефералам для пользователя
async def get_ref_stat(user_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow(
        "SELECT (SELECT CAST(SUM(amount) * 0.15 AS INT) FROM orders "
        "WHERE EXISTS(SELECT 1 FROM users WHERE inviter_id = $1 AND users.user_id = orders.user_id) "
        "AND pay_time IS NOT NULL) AS all_income,"
        "(SELECT ref_balance FROM users WHERE user_id = $1) AS available_for_withdrawal,"
        "(SELECT COUNT(user_id) FROM users WHERE inviter_id = $1) AS count_refs,"
        "(SELECT COUNT(id) FROM orders JOIN users u ON orders.user_id = u.user_id "
        "WHERE u.inviter_id = $1 AND orders.pay_time IS NOT NULL) AS orders_count",
        user_id
    )

    await conn.close()
    return row



# Получение всех пользователей, которые являются пригласившими
async def get_all_inviters():

    conn: Connection = await get_conn()
    rows = await conn.fetch('select distinct inviter_id from users where inviter_id != 0')
    await conn.close()
    return rows


# Добавление действия пользователя (использование AI)
async def add_action(user_id, ai_type, image_type=''):

    conn: Connection = await get_conn()
    action = await conn.fetchrow("INSERT INTO usage(user_id, ai_type, image_type) VALUES ($1, $2, $3) RETURNING id",
                                 user_id, ai_type, image_type)
    await conn.close()
    return action["id"]


# Получение информации о действии по его ID
async def get_action(action_id):

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM usage WHERE id = $1", action_id)
    await conn.close()
    return row


# Установка связи между task_id и action_id
async def update_action_with_task_id(request_id, task_id):
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE usage SET external_task_id = $1 WHERE id = $2",
        task_id, request_id
    )
    await conn.close()


# Получение информации о действии по task_id
async def get_action_by_task_id(task_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM usage WHERE external_task_id = $1", task_id)
    await conn.close()
    return row



# Получение информации о действии по action_id
async def get_task_by_action_id(action_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT external_task_id FROM usage WHERE id = $1", action_id)
    await conn.close()
    return row


# Установка флага, что ответ на действие пользователя был получен
async def set_action_get_response(usage_id):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE usage SET get_response = TRUE WHERE id = $1", usage_id)
    await conn.close()


# Получение IAM токена из таблицы конфигурации
async def get_iam_token():

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT config_value FROM config WHERE config_key = 'iam_token'")
    await conn.close()
    return row['config_value']


# Изменение IAM токена
async def change_iam_token(iam_token):

    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE config SET config_value = $1 WHERE config_key = 'iam_token'", iam_token)
    await conn.close()


# Добавление нового вывода средств
async def add_withdraw(user_id, amount):

    conn: Connection = await get_conn()
    await conn.execute("INSERT INTO withdraws(user_id, amount, withdraw_time) VALUES ($1, $2, $3)",
                       user_id, amount, int(datetime.now().timestamp()))
    await conn.close()


# Сброс реферального баланса пользователя
async def reset_ref_balance(user_id):

    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE users SET ref_balance = 0 WHERE user_id = $1", user_id)
    await conn.close()


# Создание нового промокода
async def create_promocode(amount, uses_count, code):

    conn: Connection = await get_conn()
    await conn.execute(
        "INSERT INTO promocode(amount, uses_count, code) VALUES ($1, $2, $3)", amount, uses_count, code)
    await conn.close()


# Получение промокода по его коду
async def get_promocode_by_code(code):

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM promocode WHERE code = $1", code)
    await conn.close()
    return row


# Создание промокода для пользователя
async def create_user_promocode(promocode_id, user_id):

    conn: Connection = await get_conn()
    await conn.execute(
        "INSERT INTO user_promocode(promocode_id, user_id) VALUES ($1, $2)", promocode_id, user_id)
    await conn.close()


# Получение пользовательского промокода по его ID и ID пользователя
async def get_user_promocode_by_promocode_id_and_user_id(promocode_id, user_id):

    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM user_promocode WHERE promocode_id = $1 and user_id = $2", promocode_id,
                              user_id)
    await conn.close()
    return row


# Получение всех промокодов пользователя по его ID
async def get_all_user_promocode_by_promocode_id(promocode_id):

    conn: Connection = await get_conn()
    rows = await conn.fetch("SELECT * FROM user_promocode WHERE promocode_id = $1", promocode_id)
    await conn.close()
    return rows


# Получение статистики по промокодам
async def get_promo_for_stat():

    conn: Connection = await get_conn()
    rows = await conn.fetch("""select code, amount, uses_count, count(up.user_id) as users_count
from promocode
         left join user_promocode up on promocode.promocode_id = up.promocode_id
group by promocode.promocode_id, amount, uses_count, code
having count(up.user_id) < uses_count""")
    await conn.close()
    return rows


""" НОВЫЕ ФУНКЦИИ ТОКЕНОВ И ЗАПРОСОВ """
""" Заказы токенов и запросов"""


# Добавление нового заказа на токены/запросы
async def add_order(user_id, amount, order_type, quantity):
    conn: Connection = await get_conn()

    order_id = str(uuid.uuid4())  # Генерируем UUID

    row = await conn.fetchrow(
        "INSERT INTO orders(order_id, user_id, amount, order_type, quantity, pay_time) "
        "VALUES ($1, $2, $3, $4, $5, NULL) RETURNING *",
        order_id, user_id, amount, order_type, quantity
    )

    await conn.close()
    return row["order_id"]  # Теперь возвращаем `order_id`


# Получение информации о заказе по ID
async def get_order(order_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM orders WHERE order_id = $1", order_id)
    await conn.close()
    return row



# Установка времени оплаты для заказа
async def set_order_pay(order_id):
    conn: Connection = await get_conn()
    await conn.execute("UPDATE orders SET pay_time = NOW() WHERE order_id = $1", order_id)
    await conn.close()



''' Токены и Запросы '''

# Обновление количества токенов у пользователя
async def update_tokens(user_id, new_tokens, model):

    conn: Connection = await get_conn()
    dashed_model = model.replace("-", "_")
    column = f'tokens_{dashed_model}'
    if column not in {'tokens_5', 'tokens_5_mini'}:
        raise ValueError(f"Invalid model {column}")

    await conn.execute(f"UPDATE users SET {column} = $2 WHERE user_id = $1", user_id, new_tokens)
    await conn.close()


# Обновление количества запросов MidJourney у пользователя
async def update_requests(user_id, new_requests):

    conn: Connection = await get_conn()
    await conn.execute("UPDATE users SET mj = $2 WHERE user_id = $1", user_id, new_requests)
    await conn.close()


"""Скидка ChatGPT"""

async def get_user_notified_gpt(user_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow(
        "SELECT is_notified, last_notification, used FROM discount_gpt WHERE user_id = $1", 
        user_id)
    await conn.close()
    return row

async def create_user_notification_gpt(user_id):
    """Создаем новую запись уведомления для пользователя."""
    conn: Connection = await get_conn()
    await conn.execute(
        """
        INSERT INTO discount_gpt (user_id, is_notified, last_notification) 
        VALUES ($1, TRUE, NOW()) 
        ON CONFLICT (user_id) 
        DO UPDATE SET is_notified = TRUE, last_notification = NOW()
        """,
        user_id
    )
    await conn.close()

async def update_user_notification_gpt(user_id):
    """Обновляем уведомление пользователя, если запись уже существует."""
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE discount_gpt SET is_notified = TRUE, last_notification = NOW() WHERE user_id = $1",
        user_id)
    await conn.close()

async def update_used_discount_gpt(user_id):
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE discount_gpt SET used = TRUE WHERE user_id = $1",
        user_id)
    await conn.close()

"""Скидка Midjourney"""

async def get_user_notified_mj(user_id):
    conn: Connection = await get_conn()
    row = await conn.fetchrow(
        "SELECT is_notified, last_notification, used FROM discount_mj WHERE user_id = $1", 
        user_id)
    await conn.close()
    return row

async def create_user_notification_mj(user_id):
    """Создаем новую запись уведомления для пользователя."""
    conn: Connection = await get_conn()
    await conn.execute(
        """
        INSERT INTO discount_mj (user_id, is_notified, last_notification) 
        VALUES ($1, TRUE, NOW()) 
        ON CONFLICT (user_id) 
        DO UPDATE SET is_notified = TRUE, last_notification = NOW()
        """,
        user_id
    )
    await conn.close()

async def update_user_notification_mj(user_id):
    """Обновляем уведомление пользователя, если запись уже существует."""
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE discount_mj SET is_notified = TRUE, last_notification = NOW() WHERE user_id = $1",
        user_id)
    await conn.close()

async def update_used_discount_mj(user_id):
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE discount_mj SET used = TRUE WHERE user_id = $1",
        user_id)
    await conn.close()


# Делал ли пользователь заказ в последние 29 дней по этой модели
async def has_matching_orders(user_id: int) -> bool:
    try:
        conn: Connection = await get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM orders
                    WHERE user_id = $1
                      AND pay_time IS NOT NULL
                      AND pay_time >= NOW() - INTERVAL '29 days'
                      AND order_type IN ('4_1', 'o1')
                ) AS exists
                """,
                user_id
            )
            return row['exists']
        finally:
            await conn.close()
    except Exception as e:
        # Логирование ошибки или другая обработка
        print(f"Ошибка при проверке заказов: {e}")
        return False


'''
СТАТИСТИКА ДЛЯ АДМИНА
'''

CHATGPT_ORDER_TYPES = ['5', '5-mini']
CHATGPT_QUANTITIES = [20000, 40000, 60000, 100000]
MIDJOURNEY_QUANTITIES = [10, 20, 50, 100]


def escape_markdown(text: Any) -> str:
    """
    Экранирует специальные символы MarkdownV2.
    """
    text = str(text)
    escape_chars = r'\`*_{}[]()#+-.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])


async def fetch_statistics() -> str:
    """
    Cобирает статистику из базы данных и возвращает отформатированную строку.
    """
    try:
        conn: asyncpg.Connection = await get_conn()
    except Exception as e:
        return f"Ошибка подключения к базе данных: {e}"

    try:
        # Получаем текущее время в Москве и начало текущего дня
        moscow_tz = ZoneInfo("Europe/Moscow")
        now_moscow = datetime.now(moscow_tz)
        start_of_day = now_moscow.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        logger.info(f"Сбор статистики с начала дня: {start_of_day.isoformat()}")

        # Запросы к базе данных с фильтрацией оплаченных заказов
        # Все оплаты за всё время
        all_time_orders = await conn.fetch("""
            SELECT order_type, quantity, COUNT(*) AS count, SUM(amount) AS total_amount
            FROM orders
            WHERE pay_time IS NOT NULL
            GROUP BY order_type, quantity
        """)
        logger.info(f"Получено {len(all_time_orders)} записей за всё время")

        # Оплаты с начала дня по московскому времени
        todays_orders = await conn.fetch("""
            SELECT order_type, quantity, COUNT(*) AS count, SUM(amount) AS total_amount
            FROM orders
            WHERE pay_time >= $1 AND pay_time IS NOT NULL
            GROUP BY order_type, quantity
        """, start_of_day)
        logger.info(f"Получено {len(todays_orders)} записей за сегодня")

        # Закрываем соединение
        await conn.close()
        logger.info("Соединение с базой данных закрыто")

        # Обработка данных
        statistics = {
            'all_time': process_orders(all_time_orders),
            'today': process_orders(todays_orders)
        }

        # Форматирование вывода
        formatted_statistics = format_statistics(statistics)
        return formatted_statistics

    except Exception as e:
        logger.error(f"Ошибка при выполнении запросов или обработке данных: {e}")
        return f"Ошибка при сборе статистики: {e}"

def process_orders(orders) -> Dict[str, Any]:
    """
    Обрабатывает записи заказов и структурирует данные для статистики.
    """
    # Инициализация статистики с нулевыми значениями
    chatgpt_stats = {
        order_type: {
            'quantities': {qty: 0 for qty in CHATGPT_QUANTITIES},
            'count': 0,
            'amount': 0
        } for order_type in CHATGPT_ORDER_TYPES
    }
    total_chatgpt_count = 0
    total_chatgpt_amount = 0
    midjourney_stats = {qty: 0 for qty in MIDJOURNEY_QUANTITIES}
    midjourney_totals = {'total_count': 0, 'total_amount': 0}

    for record in orders:
        order_type = record['order_type']
        quantity = record['quantity']
        count = record['count']
        amount = record['total_amount'] or 0  # Обработка возможных NULL значений

        if order_type in CHATGPT_ORDER_TYPES:
            if quantity in CHATGPT_QUANTITIES:
                chatgpt_stats[order_type]['quantities'][quantity] += count
                chatgpt_stats[order_type]['count'] += count
                chatgpt_stats[order_type]['amount'] += amount
                total_chatgpt_count += count
                total_chatgpt_amount += amount
            else:
                logger.warning(f"Неизвестное количество для ChatGPT: {quantity}")
        elif order_type == 'midjourney':
            if quantity in MIDJOURNEY_QUANTITIES:
                midjourney_stats[quantity] += count
                midjourney_totals['total_count'] += count
                midjourney_totals['total_amount'] += amount
            else:
                logger.warning(f"Неизвестное количество для Midjourney: {quantity}")
        else:
            logger.warning(f"Неизвестный тип заказа: {order_type}")

    return {
        'ChatGPT': {
            'details': chatgpt_stats,
            'total_count': total_chatgpt_count,
            'total_amount': total_chatgpt_amount
        },
        'Midjourney': {
            'details': midjourney_stats,
            'total_count': midjourney_totals['total_count'],
            'total_amount': midjourney_totals['total_amount']
        }
    }

def format_statistics(statistics: Dict[str, Any]) -> str:
    """
    Форматирует статистику в строку для отправки в Telegram.
    """
    def format_order(order_stats: Dict[str, Any], title: str) -> str:
        lines = [f"*{escape_markdown(title)}:*"]

        # Форматирование ChatGPT
        chatgpt = order_stats.get('ChatGPT', {})
        if chatgpt:
            for order_type, details in chatgpt['details'].items():

                lines.append(f"*{escape_markdown(order_type)}*")
                for qty in CHATGPT_QUANTITIES:
                    lines.append(f"{qty//1000}к токенов: {chatgpt['details'][order_type]['quantities'][qty]}")
                lines.append(f"*Всего {escape_markdown(order_type)}: {escape_markdown(chatgpt['details'][order_type]['count'])}*\n")

            # Общие суммы и разбивка
            total_chatgpt_count = chatgpt['total_count']
            total_chatgpt_amount = chatgpt['total_amount']
            lines.append(f"*Всего оплат ChatGPT: {escape_markdown(total_chatgpt_count)}* \(4_1 \+ o1\)\n")

        # Форматирование Midjourney
        midjourney = order_stats.get('Midjourney', {})
        if midjourney:
            lines.append("*Midjourney*")
            for qty in MIDJOURNEY_QUANTITIES:
                count = midjourney['details'].get(qty, 0)
                lines.append(f"{qty} запросов: {count}")
            total_midjourney = midjourney.get('total_count', 0)
            total_midjourney_amount = midjourney.get('total_amount', 0)
            lines.append(f"*Всего: {escape_markdown(total_midjourney)}*")

        return '\n'.join(lines)

    all_time = format_order(statistics['all_time'], "Оплат за все время")
    today = format_order(statistics['today'], "Оплат за 24 часа")
    return f"{all_time}\n\n{today}"



async def fetch_short_statistics() -> str:
    """
    Асинхронно собирает краткую статистику из базы данных и возвращает отформатированную строку.
    """
    try:
        conn: asyncpg.Connection = await get_conn()
    except Exception as e:
        return f"Ошибка подключения к базе данных: {e}"

    try:
        # Получаем текущее время в Москве и начало текущего дня
        moscow_tz = ZoneInfo("Europe/Moscow")
        now_moscow = datetime.now(moscow_tz)
        start_of_day = now_moscow.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        logger.info(f"Сбор краткой статистики с начала дня: {start_of_day.isoformat()}")

        # За все время
        users_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
        """)
        logger.info(f"Количество пользователей за всё время: {users_all_time}")

        total_requests_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
        """)
        logger.info(f"Количество запросов за всё время: {total_requests_all_time}")

        total_payments_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL
        """)
        logger.info(f"Количество оплат за всё время: {total_payments_all_time}")

        chatgpt_requests_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
            WHERE ai_type IN ('chatgpt', '4_1', '4o', 'o4-mini', 'o1')
        """)
        logger.info(f"ChatGPT запросов за всё время: {chatgpt_requests_all_time}")

        chatgpt_payments_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL AND order_type IN ('chatgpt', '4_1', '4o', 'o4-mini', 'o1')
        """)
        logger.info(f"ChatGPT оплат за всё время: {chatgpt_payments_all_time}")

        midjourney_requests_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
            WHERE ai_type = 'image'
        """)
        logger.info(f"Midjourney запросов за всё время: {midjourney_requests_all_time}")

        midjourney_payments_all_time = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL AND order_type = 'midjourney'
        """)
        logger.info(f"Midjourney оплат за всё время: {midjourney_payments_all_time}")

        # За 24 часа (с начала дня)
        users_today = await conn.fetchval("""
            SELECT COUNT(DISTINCT user_id)
            FROM users
            WHERE to_timestamp(reg_time) >= $1
        """, start_of_day)
        logger.info(f"Количество пользователей, зарегистрировавшихся сегодня: {users_today}")

        total_requests_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
            WHERE create_time >= $1
        """, start_of_day)
        logger.info(f"Количество запросов за сегодня: {total_requests_today}")

        total_payments_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL AND pay_time >= $1
        """, start_of_day)
        logger.info(f"Количество оплат за сегодня: {total_payments_today}")

        chatgpt_requests_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
            WHERE ai_type IN ('5', '5-mini', '5_mini') AND create_time >= $1
        """, start_of_day)
        logger.info(f"ChatGPT запросов за сегодня: {chatgpt_requests_today}")

        chatgpt_payments_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL AND pay_time >= $1 AND order_type IN ('chatgpt', '4_1', '4o', 'o4-mini', 'o1')
        """, start_of_day)
        logger.info(f"ChatGPT оплат за сегодня: {chatgpt_payments_today}")

        midjourney_requests_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM usage
            WHERE ai_type = 'image' AND create_time >= $1
        """, start_of_day)
        logger.info(f"Midjourney запросов за сегодня: {midjourney_requests_today}")

        midjourney_payments_today = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE pay_time IS NOT NULL AND pay_time >= $1 AND order_type = 'midjourney'
        """, start_of_day)
        logger.info(f"Midjourney оплат за сегодня: {midjourney_payments_today}")

        # --- СТАТИСТИКА ЗВЁЗД ---
        months = {
            1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
            5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
            9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
        }

        current_month_number = now_moscow.month
        current_month_name = months[current_month_number]

        prev_month_number = current_month_number - 1 if current_month_number > 1 else 12
        prev_month_name = months[prev_month_number]

        stars_today_count = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM stars WHERE DATE(date) = CURRENT_DATE AND paid = TRUE"
        )
        stars_current_month = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM stars
            WHERE EXTRACT(MONTH FROM date) = $1 AND EXTRACT(YEAR FROM date) = $2 AND paid = TRUE
            """,
            current_month_number, now_moscow.year
        )
        stars_prev_month = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM stars
            WHERE EXTRACT(MONTH FROM date) = $1 AND EXTRACT(YEAR FROM date) = $2 AND paid = TRUE
            """,
            prev_month_number,
            now_moscow.year if prev_month_number != 12 else now_moscow.year - 1
        )

        stars_users_today = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM stars WHERE DATE(date) = CURRENT_DATE AND paid = TRUE"
        )
        stars_users_current_month = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM stars
            WHERE EXTRACT(MONTH FROM date) = $1 AND EXTRACT(YEAR FROM date) = $2 AND paid = TRUE
            """,
            current_month_number, now_moscow.year
        )
        stars_users_prev_month = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM stars
            WHERE EXTRACT(MONTH FROM date) = $1 AND EXTRACT(YEAR FROM date) = $2 AND paid = TRUE
            """,
            prev_month_number,
            now_moscow.year if prev_month_number != 12 else now_moscow.year - 1
        )

        # --- СТАТИСТИКА РЕФЕРАЛОВ ---
        start_of_week = (now_moscow - timedelta(days=now_moscow.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).replace(tzinfo=None)
        start_of_month = now_moscow.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)

        referrals_total = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE inviter_id IS NOT NULL AND inviter_id <> 0
        """)

        referrals_day = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE inviter_id IS NOT NULL AND inviter_id <> 0
              AND to_timestamp(reg_time) >= $1
        """, start_of_day)

        referrals_week = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE inviter_id IS NOT NULL AND inviter_id <> 0
              AND to_timestamp(reg_time) >= $1
        """, start_of_week)

        referrals_month = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE inviter_id IS NOT NULL AND inviter_id <> 0
              AND to_timestamp(reg_time) >= $1
        """, start_of_month)

        # Закрываем соединение
        await conn.close()
        logger.info("Соединение с базой данных закрыто")

        # --- ФОРМИРОВАНИЕ ДАННЫХ ---
        all_time = {
            'users': users_all_time,
            'requests': total_requests_all_time,
            'payments': total_payments_all_time,
            'chatgpt_requests': chatgpt_requests_all_time,
            'chatgpt_payments': chatgpt_payments_all_time,
            'midjourney_requests': midjourney_requests_all_time,
            'midjourney_payments': midjourney_payments_all_time,
        }

        today = {
            'users': users_today,
            'requests': total_requests_today,
            'payments': total_payments_today,
            'chatgpt_requests': chatgpt_requests_today,
            'chatgpt_payments': chatgpt_payments_today,
            'midjourney_requests': midjourney_requests_today,
            'midjourney_payments': midjourney_payments_today,
        }

        stars_data = {
            'today': stars_today_count,
            'current_month': stars_current_month,
            'prev_month': stars_prev_month,
            'users_today': stars_users_today,
            'users_current_month': stars_users_current_month,
            'users_prev_month': stars_users_prev_month,
            'current_month_name': current_month_name,
            'prev_month_name': prev_month_name
        }

        referrals_data = {
            'total': int(referrals_total or 0),
            'day': int(referrals_day or 0),
            'week': int(referrals_week or 0),
            'month': int(referrals_month or 0),
        }

        short_statistics = format_short_statistics(
            all_time=all_time,
            today=today,
            stars=stars_data,
            referrals=referrals_data
        )

        return short_statistics

    except Exception as e:
        logger.error(f"Ошибка при выполнении запросов или обработке данных: {e}")
        return f"Ошибка при сборе статистики: {e}"


def format_short_statistics(all_time: Dict[str, Any], today: Dict[str, Any], stars: Dict[str, Any], referrals: Dict[str, Any]) -> str:
    """
    Форматирует краткую статистику в строку для отправки в Telegram.
    """

    def format_section(title: str, data: Dict[str, Any]) -> str:
        lines = [f"*{escape_markdown(title)}:*"]

        # Количество пользователей
        lines.append(f"**Количество пользователей:** {escape_markdown(str(data['users']))}")

        # Запросы и оплаты
        lines.append(f"Запросов \\| Оплат \\| {data['requests']} \\| {data['payments']}")

        # ChatGPT
        chatgpt_payments = data['chatgpt_payments'] if data['chatgpt_payments'] > 0 else "0"
        lines.append(f"ChatGPT \\| {data['chatgpt_requests']} \\| {chatgpt_payments}")

        # Midjourney
        midjourney_payments = data['midjourney_payments'] if data['midjourney_payments'] > 0 else "0"
        lines.append(f"Midjourney \\| {data['midjourney_requests']} \\| {midjourney_payments}")

        return '\n'.join(lines)

    all_time_section = format_section("За все время", all_time)
    today_section = format_section("За 24 часа", today)

    # --- Форматирование Stars ---
    stars_section = (
        "**Stars:**\n"
        f"За сегодня: {stars.get('users_today', 0)} \\({stars.get('today', 0)} руб\\)\n"
        f"За {stars['current_month_name']}: {stars.get('users_current_month', 0)} \\({stars.get('current_month', 0)} руб\\)\n"
        f"За {stars['prev_month_name']}: {stars.get('users_prev_month', 0)} \\({stars.get('prev_month', 0)} руб\\)"
    )

    # --- Форматирование рефералов ---
    referrals_section = (
        "**🤝 Реферальная программа:**\n"
        f"├ Всего: {referrals.get('total', 0)}\n"
        f"├ За день: {referrals.get('day', 0)}\n"
        f"├ За неделю: {referrals.get('week', 0)}\n"
        f"└ За месяц: {referrals.get('month', 0)}"
    )

    return f"{all_time_section}\n\n{today_section}\n\n{stars_section}\n\n{referrals_section}"



# Функция для установления соединения с базой данных
async def get_conn() -> Connection:
    return await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE, host=DB_HOST)


# Функция для создания необходимых таблиц в базе данных
async def create_tables():
    conn: Connection = await get_conn()

    # Создание таблицы chats
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id SERIAL PRIMARY KEY,            -- Уникальный идентификатор чата
            user_id BIGINT,                   -- ID пользователя, связанного с чатом
            name VARCHAR(255),                -- Название чата (например, тема)
            summary TEXT,                     -- Краткое описание чата (сводка)
            keywords TEXT[],                  -- Список ключевых слов
            created_at TIMESTAMP DEFAULT NOW(), -- Время создания чата
            updated_at TIMESTAMP DEFAULT NOW()  -- Время последнего обновления чата
        );
    """)

    # На случай, если таблица уже есть, добавляем колонку keywords отдельно
    await conn.execute("""
        ALTER TABLE chats
        ADD COLUMN IF NOT EXISTS keywords TEXT[];
    """)

    # Создание таблицы messages
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,                                -- Уникальный идентификатор сообщения
            chat_id INT REFERENCES chats(id) ON DELETE CASCADE,   -- ID чата (ссылается на таблицу `chats`)
            user_id BIGINT NULL,                                  -- ID пользователя, NULL если сообщение от бота
            text TEXT,                                            -- Текст сообщения
            created_at TIMESTAMP DEFAULT NOW()                    -- Время отправки сообщения
        );
    """)

    # Добавление current_chat_id в таблицу users
    await conn.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS current_chat_id INT;
    """)

    # Создание индекса на user_id в таблице chats
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id);
    """)

    # создание таблицы для звёзд:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS stars ("
        "id SERIAL PRIMARY KEY, "
        "user_id BIGINT, "
        "date TIMESTAMP NOT NULL DEFAULT now(), "
        "amount INTEGER NOT NULL DEFAULT 1, "
        "order_id TEXT, "
        "paid BOOLEAN DEFAULT FALSE"
        ")"
    )

    await conn.close()


# Функция для создания нового чата
async def create_chat(user_id: int, name: str, summary: str) -> int:
    conn: Connection = await get_conn()
    result = await conn.fetchrow("""
        INSERT INTO chats (user_id, name, summary, created_at, updated_at)
        VALUES ($1, $2, $3, NOW(), NOW())
        RETURNING id;
    """, user_id, name, summary)
    await conn.close()
    return result['id']  # Возвращаем ID созданного чата


# Функция для добавления сообщения в чат
async def add_message(chat_id: int, user_id: int, text: str):
    conn: Connection = await get_conn()
    await conn.execute("""
        INSERT INTO messages (chat_id, user_id, text, created_at)
        VALUES ($1, $2, $3, NOW());
    """, chat_id, user_id, text)
    # ВАЖНО: фиксируем активность чата
    await conn.execute("UPDATE chats SET updated_at = NOW() WHERE id = $1", chat_id)
    await conn.close()


# Функция для обновления активного чата пользователя
async def set_current_chat(user_id: int, chat_id: int):
    conn: Connection = await get_conn()
    await conn.execute("""
        UPDATE users SET current_chat_id = $2 WHERE user_id = $1;
    """, user_id, chat_id)
    await conn.close()

# Функция для получения чата по ID
async def get_chat_by_id(chat_id: int):
    conn: Connection = await get_conn()
    row = await conn.fetchrow("SELECT * FROM chats WHERE id = $1", chat_id)
    await conn.close()
    return row

async def update_chat_summary(chat_id: int, summary: str):
    conn = await get_conn()
    await conn.execute("""
        UPDATE chats SET summary = $2, updated_at = NOW() WHERE id = $1;
    """, chat_id, summary)
    await conn.close()

async def add_star(user_id: int, amount: int, order_id: str):
    """
    Добавляет запись в таблицу stars для отслеживания оплаты.

    Args:
    user_id (int): ID пользователя.
    amount (int): Сумма.
    order_id (str): Уникальный ID заказа.
    """
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO stars (user_id, amount, paid, order_id) VALUES ($1, $2, $3, $4)",
            user_id, amount, False, order_id
        )
    finally:
        await conn.close()


async def mark_star_paid(order_id: str):
    """
    Обновляет статус оплаты для записи в таблице stars по order_id.

    Args:
    order_id (str): Строковый ID заказа.
    """
    conn = await get_conn()
    try:
        await conn.execute(
            "UPDATE stars SET paid = TRUE WHERE order_id = $1",
            order_id
        )
    finally:
        await conn.close()


# Обновляем настройки изображений OpenAI (например, размер, качество и т.д.)
async def update_image_openai_settings(user_id, key_path, value):
    """
    Обновляет конкретное поле в JSONB-колонке image_openai_settings.

    Пример:
        await update_image_openai_settings(user_id, ['size'], '"1536x1024"')
    """
    conn: Connection = await get_conn()
    # Передаем путь как список, а не как строку
    await conn.execute(
        "UPDATE users SET image_openai_settings = jsonb_set(image_openai_settings, $2, $3) WHERE user_id = $1",
        user_id, key_path, value
    )
    await conn.close()


# уменьшать баланс image open AI
async def decrease_image_openai_balance(user_id):
    conn = await get_conn()
    try:
        # Обновляем баланс: сначала пробуем уменьшить free_image_openai
        result = await conn.execute(
            """
            UPDATE users
            SET free_image_openai = GREATEST(free_image_openai - 1, 0)
            WHERE user_id = $1 AND free_image_openai > 0
            RETURNING user_id, free_image_openai
            """,
            user_id
        )

        if result == "UPDATE 0":
            # Если нет свободных, уменьшаем платные
            await conn.execute(
                """
                UPDATE users
                SET image_openai = GREATEST(image_openai - 1, 0)
                WHERE user_id = $1 AND image_openai > 0
                """,
                user_id
            )
    finally:
        await conn.close()


async def has_image_openai_balance(user_id):
    conn = await get_conn()
    user = await conn.fetchrow("SELECT image_openai, free_image_openai FROM users WHERE user_id = $1", user_id)
    await conn.close()

    if user["image_openai"] > 0 or user["free_image_openai"] > 0:
        return True
    else:
        return False


# Отметка: пользователь использовал доступ без подписки
async def mark_used_trial(user_id):
    conn = await get_conn()
    try:
        result = await conn.fetchrow("SELECT used_trial FROM users WHERE user_id = $1", user_id)
        if result and not result["used_trial"]:
            await conn.execute("UPDATE users SET used_trial = TRUE WHERE user_id = $1", user_id)
    finally:
        await conn.close()

async def update_is_subscribed(user_id: int, value: bool):
    conn = await get_conn()
    await conn.execute("UPDATE users SET is_subscribed = $1 WHERE user_id = $2", value, user_id)
    await conn.close()

async def set_ref_notifications(user_id: int, enabled: bool):
    conn = await get_conn()
    await conn.execute("UPDATE users SET ref_notifications_enabled = $1 WHERE user_id = $2", enabled, user_id)
    await conn.close()


async def get_chat_last_activity(chat_id: int):
    conn = await get_conn()
    row = await conn.fetchrow("""
        SELECT GREATEST(
            c.updated_at,
            COALESCE(MAX(m.created_at), c.updated_at)
        ) AS last_activity
        FROM chats c
        LEFT JOIN messages m ON m.chat_id = c.id
        WHERE c.id = $1
        GROUP BY c.updated_at
    """, chat_id)
    await conn.close()
    return row["last_activity"] if row else None


# пользователи, у кого выбран активный чат
async def get_users_with_active_chat():
    conn = await get_conn()
    rows = await conn.fetch("""
        SELECT user_id, current_chat_id
        FROM users
        WHERE current_chat_id IS NOT NULL
    """)
    await conn.close()
    return rows


# последняя активность пользователя по ВСЕМ его чатам
async def get_user_last_activity(user_id: int):
    conn = await get_conn()
    row = await conn.fetchrow("""
        WITH t AS (
            SELECT MAX(c.updated_at) AS ts
            FROM chats c
            WHERE c.user_id = $1
            UNION ALL
            SELECT MAX(m.created_at) AS ts
            FROM messages m
            JOIN chats c2 ON c2.id = m.chat_id
            WHERE c2.user_id = $1
        )
        SELECT MAX(ts) AS last_activity FROM t
    """, user_id)
    await conn.close()
    return row["last_activity"] if row and row["last_activity"] else None

async def add_gpt_referral_days(user_id: int, days: int) -> None:
    """
    Учитываем, сколько дней ChatGPT пользователь заработал по рефералам (для статистики).
    """
    conn: Connection = await get_conn()
    await conn.execute(
        """
        UPDATE users
        SET gpt_referral_days_earned = COALESCE(gpt_referral_days_earned, 0) + $1
        WHERE user_id = $2
        """,
        int(days), int(user_id)
    )
    await conn.close()

async def extend_gpt_access(user_id: int, days: int = 14):
    """
    Продлеваем доступ к ChatGPT на N дней.
    Если срок уже истёк или NULL — начинаем отсчёт от текущего момента.
    Также сбрасываем флаг предупреждения за 3 дня (если уже стоял).
    """
    conn: Connection = await get_conn()
    await conn.execute(
        """
        UPDATE users
        SET gpt_access_until = CASE
            WHEN gpt_access_until IS NULL THEN (NOW() AT TIME ZONE 'utc') + ($2::int * INTERVAL '1 day')
            WHEN gpt_access_until < (NOW() AT TIME ZONE 'utc') THEN (NOW() AT TIME ZONE 'utc') + ($2::int * INTERVAL '1 day')
            ELSE gpt_access_until + ($2::int * INTERVAL '1 day')
        END,
        gpt_expire_warned = FALSE
        WHERE user_id = $1
        """,
        int(user_id), int(days)
    )
    await conn.close()

# Пользователи, у которых доступ к ChatGPT истекает в ближайшие N дней и которым ещё не отправляли предупреждение
async def get_users_gpt_expiring(days_left: int = 3):
    conn: Connection = await get_conn()
    rows = await conn.fetch(
        """
        SELECT user_id, gpt_access_until
        FROM users
        WHERE gpt_access_until IS NOT NULL
          AND gpt_expire_warned = FALSE
          AND gpt_access_until > (NOW() AT TIME ZONE 'utc')
          AND gpt_access_until <= (NOW() AT TIME ZONE 'utc') + ($1::int * INTERVAL '1 day')
        ORDER BY gpt_access_until ASC
        """,
        int(days_left)
    )
    await conn.close()
    return rows


# Помечаем, что предупреждение об окончании доступа уже отправляли (чтобы не спамить)
async def set_gpt_expire_warned(user_id: int, value: bool = True):
    conn: Connection = await get_conn()
    await conn.execute(
        "UPDATE users SET gpt_expire_warned = $2 WHERE user_id = $1",
        int(user_id), bool(value)
    )
    await conn.close()

async def fetch_gpt_access_admin_stats(days_left: int = 3, limit: int = 10):
    """
    Админ-статистика по доступу ChatGPT.
    Возвращает:
      - total_users: всего пользователей
      - active_users: у кого доступ активен (gpt_access_until > now)
      - expired_users: у кого доступ истёк или не задан (<= now или NULL)
      - expiring_users: у кого истекает в ближайшие N дней
      - warned_users: у кого уже стоит флаг предупреждения
      - expiring_list: список ближайших истечений (user_id, gpt_access_until)
    """
    conn: Connection = await get_conn()
    try:
        now_utc = "NOW() AT TIME ZONE 'utc'"

        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")

        active_users = await conn.fetchval(
            f"SELECT COUNT(*) FROM users WHERE gpt_access_until IS NOT NULL AND gpt_access_until > ({now_utc})"
        )

        expired_users = await conn.fetchval(
            f"SELECT COUNT(*) FROM users WHERE gpt_access_until IS NULL OR gpt_access_until <= ({now_utc})"
        )

        expiring_users = await conn.fetchval(
            f"""
            SELECT COUNT(*)
            FROM users
            WHERE gpt_access_until IS NOT NULL
              AND gpt_access_until > ({now_utc})
              AND gpt_access_until <= ({now_utc}) + ($1 || ' days')::interval
            """,
            int(days_left)
        )

        warned_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE gpt_expire_warned = TRUE"
        )

        expiring_list = await conn.fetch(
            f"""
            SELECT user_id, gpt_access_until
            FROM users
            WHERE gpt_access_until IS NOT NULL
              AND gpt_access_until > ({now_utc})
            ORDER BY gpt_access_until ASC
            LIMIT $1
            """,
            int(limit)
        )

        return {
            "total_users": int(total_users or 0),
            "active_users": int(active_users or 0),
            "expired_users": int(expired_users or 0),
            "expiring_users": int(expiring_users or 0),
            "warned_users": int(warned_users or 0),
            "expiring_list": expiring_list,
        }
    finally:
        await conn.close()
