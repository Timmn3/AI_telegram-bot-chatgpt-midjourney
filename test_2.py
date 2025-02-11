import requests

params = {
    "MERCHANT_ORDER_ID": "1482",
    "AMOUNT": "199"
}

response = requests.get("http://neuronbot.ru/api/pay/freekassa", params=params)
print(response.status_code, response.text)
