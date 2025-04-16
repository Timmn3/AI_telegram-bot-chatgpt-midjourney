import requests
import json
import hashlib
import urllib3

# Отключаем предупреждения об SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настраиваем данные запроса
terminal_key = "1716210903613"
callback_url = "https://neuronbot.ru/api/pay/tinkoff/receipt"
payment_ids = [6212816167, 6212795292]
api_token = "w7bi99oqxdjfqef9"         # <-- Замени на реальный API токен
tinkoff_terminal_id = "1716210903613" # <-- Обычно совпадает с TerminalKey

# Генерация токена
sign_str = f"{callback_url}{','.join(map(str, payment_ids))}{api_token}{tinkoff_terminal_id}"
token = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

# Собираем тело запроса
data = {
    "TerminalKey": terminal_key,
    "CallbackUrl": callback_url,
    "PaymentIdList": payment_ids,
    "Token": token
}

# URL (IP-адрес, но с отключенной проверкой SSL)
url = "https://neuronbot.ru/api/pay/tinkoff/receipt"

# Отправляем запрос (verify=False отключает проверку SSL)
response = requests.post(url, json=data)

# Выводим ответ
print(f"Response Status Code: {response.status_code}")
print(f"Response Text: {response.text}")
