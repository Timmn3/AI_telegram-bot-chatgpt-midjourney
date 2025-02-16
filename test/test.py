import requests

data = {
    "OrderId": "1482",
    "Amount": 199,
    "Status": "CONFIRMED"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/pay/tinkoff", json=data, headers=headers, verify=False, allow_redirects=False)

print(response.status_code, response.headers)
