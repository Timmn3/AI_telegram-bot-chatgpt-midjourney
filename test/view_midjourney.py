import requests
import time

API_KEY = "a8796714c850e8baddd125dacd8bf4db7b945992d3aa3e9f3c190c0ded7d918a"
API_URL = "https://api.goapi.ai/mj/v2/imagine"

prompt = "white"

data = {
    "process_mode": "fast",
    "prompt": prompt,
    "webhook_endpoint": "https://neuronbot.ru/api/midjourney/20595",
    "notify_progress": True
}

headers = {
    "Content-Type": "application/json",
    "X-API-KEY": API_KEY
}

response = requests.post(API_URL, json=data, headers=headers)

if response.status_code == 200:
    response_data = response.json()
    task_id = response_data.get("task_id")

    if task_id:
        print(f"Запрос принят. Task ID: {task_id}")

        status_url = f"https://api.goapi.ai/mj/v2/task/{task_id}"
        while True:
            status_response = requests.get(status_url, headers=headers)

            # Новый блок с отладочным выводом
            print(f"Статус-код запроса: {status_response.status_code}")
            print(f"Ответ сервера: {status_response.text}")

            if status_response.status_code == 200:
                status_data = status_response.json()
                task_status = status_data.get("status")

                if task_status == "completed":
                    image_url = status_data.get("image_url")
                    if image_url:
                        print(f"Изображение готово: {image_url}")

                        img_response = requests.get(image_url)
                        if img_response.status_code == 200:
                            filename = f"{prompt.replace(' ', '_')}.jpg"
                            with open(filename, "wb") as img_file:
                                img_file.write(img_response.content)
                            print(f"Изображение сохранено как '{filename}'")
                        break
                elif task_status in ["failed", "error"]:
                    print("Ошибка при генерации изображения.")
                    break
                else:
                    print(f"Ожидание... Текущий статус: {task_status}")
                    time.sleep(5)
            else:
                print(f"Ошибка при получении статуса задачи: {status_response.status_code}")
                break
    else:
        print("Не удалось получить Task ID.")
else:
    print(f"Ошибка при отправке запроса: {response.status_code}, {response.text}")
