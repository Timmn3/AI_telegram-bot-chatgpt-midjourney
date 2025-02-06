import asyncio
from typing import Union

from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware


class AlbumMiddleware(BaseMiddleware):
    """This middleware is for capturing media groups."""
    # album_data используется для временного хранения сообщений, относящихся к медиа-группе (альбому)
    album_data: dict = {}

    def __init__(self, latency: Union[int, float] = 0.5):
        """
        Latency - это задержка для того, чтобы убедиться, что все медиа из альбома
        пришли, особенно при высоких нагрузках.
        """
        self.latency = latency  # Задержка перед обработкой альбома
        super().__init__()

    # Метод вызывается при обработке каждого нового сообщения
    async def on_process_message(self, message: types.Message, data: dict):

        # Если у сообщения нет media_group_id, то это не альбом и дальнейшая обработка не требуется
        if not message.media_group_id:
            return

        try:
            # Если этот media_group_id уже есть, добавляем сообщение в альбом
            self.album_data[message.media_group_id].append(message)
            raise CancelHandler()  # Прерываем обработку других хэндлеров для этого сообщения
        except KeyError:
            # Если это первое сообщение с таким media_group_id, создаем новый альбом
            self.album_data[message.media_group_id] = [message]
            await asyncio.sleep(self.latency)  # Ожидаем поступления всех сообщений альбома

            # Отмечаем, что текущее сообщение — последнее в альбоме
            message.conf["is_last"] = True
            # Сохраняем альбом (все сообщения с media_group_id) в data, чтобы другие хэндлеры могли его использовать
            data["album"] = self.album_data[message.media_group_id]

    # Метод вызывается после обработки сообщения
    async def on_post_process_message(self, message: types.Message, result: dict, data: dict):
        
        """Clean up after handling our album."""
        # Если это последнее сообщение в альбоме, удаляем альбом из временного хранилища
        if message.media_group_id and message.conf.get("is_last"):
            del self.album_data[message.media_group_id]
