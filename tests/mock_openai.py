# mock_openai.py

import base64
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

from openai.types.image import Image
from openai.types import ImagesResponse

class MockImages:
    def __init__(self, image_path: str = "photos/generated.png"):
        self.image_path = Path(image_path)
        if not self.image_path.exists():
            raise FileNotFoundError(f"Файл {image_path} не найден для эмуляции ответа")

        with open(self.image_path, "rb") as f:
            self.image_data = f.read()

    def generate(self, model: str, prompt: str, size: str, quality: str, background: str) -> ImagesResponse:
        b64_image = base64.b64encode(self.image_data).decode("utf-8")
        return ImagesResponse(data=[Image(b64_json=b64_image, url="")])

    def edit(self, model: str, image: Union[object, List[object]], prompt: str,
             mask: Optional[object] = None,
             size: str = "1024x1024", quality: str = "medium", background: str = "opaque") -> ImagesResponse:
        """
        Эмулирует client.images.edit(...), возвращает заготовленное изображение.
        """
        # Кодируем изображение в base64
        b64_image = base64.b64encode(self.image_data).decode("utf-8")

        # Возвращаем объект типа ImagesResponse с использованием настоящего класса Image
        return ImagesResponse(
            data=[Image(b64_json=b64_image, url="")]  # <-- Используем Image вместо ImageData
        )

class MockOpenAIClient:
    def __init__(self, image_path: str = "photos/generated.png"):
        self.images = MockImages(image_path)