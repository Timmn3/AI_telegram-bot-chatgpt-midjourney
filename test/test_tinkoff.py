import requests

data = {
    "OrderId": "8bede768-dc71-4ff2-8347-5ddbdef0b94d",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, allow_redirects=False)

print(response.status_code, response.headers)
