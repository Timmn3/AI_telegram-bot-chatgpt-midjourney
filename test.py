import requests

params = {
    "MERCHANT_ORDER_ID": "1482",
    "AMOUNT": "199"
}

response = requests.get("http://127.0.0.1:8000/api/pay/freekassa", params=params)
print(response.status_code, response.text)
