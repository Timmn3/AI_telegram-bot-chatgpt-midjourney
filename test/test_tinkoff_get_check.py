
import hashlib
import requests
import asyncio

terminal_key = "1716210903613"
secret_key = "w7bi99oqxdjfqef9"

async def get_receipt_url(payment_id):
    # Отправляем запрос в Tinkoff API для получения чека по payment_id
    data = {
        "TerminalKey": terminal_key,
        "PaymentId": payment_id,
        "Token": generate_receipt_token(payment_id)  # Создаём токен для подписи
    }
    response = requests.post("https://securepay.tinkoff.ru/v2/CheckOrder", json=data)

    if response.status_code == 200:
        result = response.json()
        if result.get("Success"):
            # Если запрос успешен, возвращаем URL чека
            return result.get("ReceiptUrl")  # Это URL на изображение чека
    return None


def generate_receipt_token(payment_id):
    sign_str = f"{payment_id}{secret_key}{terminal_key}"  # Исправлено использование переменных
    return hashlib.sha256(sign_str.encode('utf-8')).hexdigest()


# Тестирование
async def test_get_receipt_url():
    payment_id = "6212920636"  # Укажи реальный PaymentId
    receipt_url = await get_receipt_url(payment_id)

    if receipt_url:
        print(f"Чек доступен по ссылке: {receipt_url}")
    else:
        print("Чек не найден или произошла ошибка")


# Запуск теста
asyncio.run(test_get_receipt_url())


