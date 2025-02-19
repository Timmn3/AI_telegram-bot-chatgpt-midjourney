import requests

data = {
    "task_id": "328909fe-fa06-4bc6-9e86-fb3776543f6e",
    "status": "completed",
    "image_url": "https://png.pngtree.com/thumb_back/fw800/background/20230610/pngtree-picture-of-a-blue-bird-on-a-black-background-image_2937385.jpg"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post("https://neuronbot.ru/api/midjourney", json=data, headers=headers)
print(response.status_code, response.text)


# curl -X POST "https://neuronbot.ru/api/midjourney" \
#      -H "Content-Type: application/json" \
#      -d '{
#         "task_id": "328909fe-fa06-4bc6-9e86-fb3776543f6e",
#         "status": "completed",
#         "image_url": "https://png.pngtree.com/thumb_back/fw800/background/20230610/pngtree-picture-of-a-blue-bird-on-a-black-background-image_2937385.jpg"
#      }' -v
