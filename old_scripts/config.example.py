TOKEN = "none"
OPENAPI_TOKEN = "none"
TNL_API_KEY = "none"
TNL_API_KEY1 = "none"
MJ_API_KEY = "none"
IMGBB_API_KEY = "none"
ya_token = "none"
ya_folder = "none"
bot_url = 'https://t.me/coin_gifter_bot'
midjourney_webhook_url = "none"
go_api_token = "none"
APIFRAME_API_KEY = "key"
log_on = False
ADMINS = ["5101525651"]
bug_id = "id"
channel_id = "https://t.me/NeuronAgent"

LAVA_API_KEY = "none"
LAVA_SHOP_ID = "none"
LAVA_WEBHOOK_KEY = "none"

NOTIFY_URL = "http://127.0.0.1:8001"

DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_DATABASE = "ai_bot"
DB_HOST = "db"

PHOTO_PATH = "/var/www/images/"
MJ_PHOTO_BASE_URL = "https://neuronbot.ru/files/images/"


class Tinkoff:
    terminal_id = "TinkoffBankTest"
    api_token = "none"


class FKWallet:
    wallet_id = 'F111721173'
    api_key = 'none'


class FreeKassa:
    shop_id = 28885
    secret1 = "none"


class PayOK:
    shop_id = 7598
    secret = "none"


sub_types = {
    "base": {
        "title": "Базовый",
        "prices": [
            {"days": 7, "price": 69, "text": "Неделя, 69₽"},
            {"days": 30, "price": 249, "text": "Месяц,  249₽"},
            {"days": 180, "price": 1299, "text": "6 месяцев, 1299₽ (-13%)"},
            {"days": 365, "price": 2389, "text": "Год, 2389₽ (-20%)"}
        ],
        "discount_prices": [
            {"days": 7, "price": 69, "text": "Неделя, 69₽"},
            {"days": 30, "price": 224, "text": "Месяц,  249₽ » 224₽ (-10%)"},
            {"days": 180, "price": 1039, "text": "6 месяцев, 1299₽ » 1039₽ (-20%)"},
            {"days": 365, "price": 1672, "text": "Год, 2389₽ » 1672₽ (-30%)"}
        ],
        "tokens": 1000000,
        "mj": 10,
        "stars": 100
    },
    "standard": {
        "title": "Стандарт",
        "prices": [
            {"days": 7, "price": 119, "text": "Неделя, 119₽"},
            {"days": 30, "price": 449, "text": "Месяц,  449₽"},
            {"days": 180, "price": 2339, "text": "6 месяцев, 2339₽ (-13%)"},
            {"days": 365, "price": 4299, "text": "Год, 4299₽ (-20%)"}
        ],
        "discount_prices": [
            {"days": 7, "price": 119, "text": "Неделя, 119₽"},
            {"days": 30, "price": 404, "text": "Месяц,  449₽ » 404₽ (-10%)"},
            {"days": 180, "price": 1871, "text": "6 месяцев, 2339₽ » 1871₽ (-20%)"},
            {"days": 365, "price": 2999, "text": "Год, 4299₽ » 2999₽ (-30%)"}
        ],
        "tokens": 2000000,
        "mj": 20,
        "stars": 200
    },
    "premium": {
        "title": "Премиум",
        "prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 999, "text": "Месяц,  999₽"},
            {"days": 180, "price": 5199, "text": "6 месяцев, 5199₽ (-13%)"},
            {"days": 365, "price": 9499, "text": "Год, 9499₽ (-20%)"}
        ],
        "discount_prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 899, "text": "Месяц,  999₽ » 899₽ (-10%)"},
            {"days": 180, "price": 4159, "text": "6 месяцев, 5199₽ » 4159₽ (-20%)"},
            {"days": 365, "price": 6649, "text": "Год, 9499₽ » 6649₽ (-30%)"}
        ],
        "tokens": 5000000,
        "mj": 40,
        "stars": 500
    },
    "illustrator": {
        "title": "Иллюстратор",
        "prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 999, "text": "Месяц,  999₽"},
            {"days": 180, "price": 5199, "text": "6 месяцев, 5199₽ (-13%)"},
            {"days": 365, "price": 9499, "text": "Год, 9499₽ (-20%)"}
        ],
        "discount_prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 899, "text": "Месяц,  999₽ » 899₽ (-10%)"},
            {"days": 180, "price": 4159, "text": "6 месяцев, 5199₽ » 4159₽ (-20%)"},
            {"days": 365, "price": 6649, "text": "Год, 9499₽ » 6649₽ (-30%)"}
        ],
        "tokens": 50000,
        "mj": 100,
        "stars": 500
    },
    "author": {
        "title": "Автор",
        "prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 999, "text": "Месяц,  999₽"},
            {"days": 180, "price": 5199, "text": "6 месяцев, 5199₽ (-13%)"},
            {"days": 365, "price": 9499, "text": "Год, 9499₽ (-20%)"}
        ],
        "discount_prices": [
            {"days": 7, "price": 289, "text": "Неделя, 289₽"},
            {"days": 30, "price": 899, "text": "Месяц,  999₽ » 899₽ (-10%)"},
            {"days": 180, "price": 4159, "text": "6 месяцев, 5199₽ » 4159₽ (-20%)"},
            {"days": 365, "price": 6649, "text": "Год, 9499₽ » 6649₽ (-30%)"}
        ],
        "tokens": 10000000,
        "mj": 5,
        "stars": 500
    }
}
