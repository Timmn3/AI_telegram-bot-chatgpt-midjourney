import requests

data = {
    "OrderId": "00ac03ee-538a-4db1-b81d-1eb4001a89b7",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, allow_redirects=False)

print(response.status_code, response.headers)
