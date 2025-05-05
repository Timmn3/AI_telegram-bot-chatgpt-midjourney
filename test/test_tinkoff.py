import requests

data = {
    "OrderId": "a1041298-a606-43ca-bb91-6ef0c3b82e3a",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, allow_redirects=False)

print(response.status_code, response.headers)
