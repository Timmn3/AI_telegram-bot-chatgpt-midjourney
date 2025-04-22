import hashlib
import requests
import asyncio

terminal_key = "1716210903613"
secret_key = "w7bi99oqxdjfqef9"
payment_ids = [6212816167, 6212795292]

def generate_token(data: dict) -> str:
    token_data = {
        "PaymentIdList": ",".join(map(str, data["PaymentIdList"])),
        "TerminalKey": data["TerminalKey"],
        "Password": secret_key
    }

    sorted_items = sorted(token_data.items())
    sign_str = "".join(str(value) for key, value in sorted_items)
    return hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

async def get_confirm_operation():
    url = "https://securepay.tinkoff.ru/v2/getConfirmOperation"

    payload = {
        "TerminalKey": terminal_key,
        "PaymentIdList": payment_ids
    }

    payload["Token"] = generate_token(payload)

    response = requests.post(url, json=payload)

    print("Request payload:", payload)  # можно временно печатать для отладки

    if response.status_code == 200:
        print("✅ Ответ:")
        print(response.json())
    else:
        print("❌ Ошибка:", response.status_code, response.text)

asyncio.run(get_confirm_operation())
