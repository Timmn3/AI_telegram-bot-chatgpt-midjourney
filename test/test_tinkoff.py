import requests

data = {
    "OrderId": "58fc851e-6c41-42f0-b8e8-d75388b58d82",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, allow_redirects=False)

print(response.status_code, response.headers)
