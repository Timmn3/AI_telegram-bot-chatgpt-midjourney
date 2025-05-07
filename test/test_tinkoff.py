import requests

data = {
    "OrderId": "5b0b6eb3-742e-4331-b40e-e364133cc131",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, allow_redirects=False)

print(response.status_code, response.headers)
