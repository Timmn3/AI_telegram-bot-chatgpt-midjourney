import asyncio
from datetime import datetime, timedelta
from time import sleep
from typing import Annotated

import config
import logging
import utils
import aiohttp
from config import NOTIFY_URL, bug_id, ADMINS_CODER, Tinkoff
from keyboards import user as user_kb
from fastapi import FastAPI, Request, HTTPException, Form  # Импорт необходимых классов для работы с FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel  # Импорт базовой модели данных
from create_bot import bot  # Импорт бота
from io import BytesIO  # Для работы с потоками байтов
from utils import db  # Импорт функций работы с базой данных
import requests  # Для синхронных HTTP-запросов
import uvicorn  # Для запуска сервера FastAPI
from typing import Optional

import uuid

from utils.pay import get_receipt_url

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')


# Инициализация FastAPI приложения
app = FastAPI()


# Класс для обработки вебхуков от системы платежей Lava
class LavaWebhook(BaseModel):

    order_id: str  # Идентификатор заказа
    status: str  # Статус платежа
    amount: float  # Сумма платежа


# Класс для обработки вебхуков от системы PayOK
class PayOKWebhook(BaseModel):

    payment_id: str  # Идентификатор платежа
    amount: float  # Сумма платежа


# Функция для отправки фотографии, сгенерированной MidJourney
async def send_mj_photo(user_id, photo_url, kb):

    try:
        response = requests.get(photo_url, timeout=5)  # Загружаем изображение по URL
    except requests.exceptions.Timeout:
        img = photo_url  # В случае таймаута просто используем URL как картинку
    except requests.exceptions.ConnectionError:
        img = photo_url  # В случае ошибки соединения также используем URL
    else:
        img = BytesIO(response.content)  # Преобразуем изображение в байтовый поток
    await bot.send_photo(user_id, photo=img, reply_markup=kb)  # Отправляем изображение пользователю


# Функция для обработки платежей
async def process_pay(order_id, amount):

    order = await db.get_order(order_id)

    if order is None:
        logger.info(f'Order {order_id} not found')
        return
    else:
        user_id = order["user_id"]

        # Если покупка была со скидкой:
        discounts_gpt = [139, 224, 381]
        discounts_mj = [246, 550, 989]

        if amount in discounts_gpt:
            await db.update_used_discount_gpt(user_id)
        elif amount in discounts_mj:
            await db.update_used_discount_mj(user_id)

        await utils.pay.process_purchase(bot, order_id) # Обрабатываем покупку токенов или запросов


# Обработка платежей от FreeKassa
@app.get('/api/pay/freekassa')
async def check_pay_freekassa(MERCHANT_ORDER_ID, AMOUNT):

    await process_pay(MERCHANT_ORDER_ID, int(AMOUNT))  # Обрабатываем платеж
    return 'YES'


# Обработка платежей от Lava
@app.post('/api/pay/lava')
async def check_pay_lava(data: LavaWebhook):

    if data.status != "success":
        raise HTTPException(200)  # Если статус не успешный, возвращаем HTTP 200
    await process_pay(data.order_id, int(data.amount))  # Обрабатываем платеж
    raise HTTPException(200)


# Обработка платежей от Tinkoff
@app.post('/api/pay/tinkoff')
async def check_pay_tinkoff(request: Request):

    data = await request.json()  # Получаем данные из запроса
    logging.debug(f"Received Tinkoff payment data: {data}")

    if data["Status"] != "CONFIRMED":  # Если статус не подтвержден, игнорируем
        return "OK"

    order_id = data["OrderId"]

    # Проверка, является ли OrderId валидным UUID
    try:
        order_id = str(uuid.UUID(order_id))
    except ValueError:
        logging.error(f"Invalid OrderId received: {order_id}")
        return JSONResponse(content={"error": "Invalid OrderId"}, status_code=400)

    await process_pay(order_id, int(data["Amount"] / 100))  # Обрабатываем платеж
    return "OK"

import hashlib

import requests
from fastapi import Request, HTTPException

@app.post('/api/pay/tinkoff/receipt')
async def receipt_handler(request: Request):
    data = await request.json()
    logger.info(f"📨 Receipt request received: {data}")

    # Проверка обязательных полей
    required_fields = ["TerminalKey", "CallbackUrl", "PaymentIdList", "Token"]
    if not all(k in data for k in required_fields):
        raise HTTPException(status_code=400, detail="Missing fields")

    # Проверка подписи
    sign_str = f"{data['CallbackUrl']}{','.join(map(str, data['PaymentIdList']))}{Tinkoff.api_token}{Tinkoff.terminal_id}"
    expected_token = hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

    if data["Token"] != expected_token:
        logger.warning("❌ Invalid token in receipt request")
        raise HTTPException(status_code=403, detail="Invalid token")

    # Обработка каждого PaymentId из списка
    for payment_id in data["PaymentIdList"]:
        order = await db.get_order_by_payment_id(str(payment_id))        # Получаем заказ по payment_id

        if order is None:
            logger.info(f"Order with PaymentId {payment_id} not found")
            continue

        # Получаем ссылку на чек от Tinkoff
        receipt_url = await get_receipt_url(payment_id)

        if receipt_url:
            user_id = order["user_id"]

            # Отправляем картинку чека пользователю
            try:
                # Загружаем картинку с URL
                response = requests.get(receipt_url)
                if response.status_code == 200:
                    img = BytesIO(response.content)
                    await bot.send_photo(user_id, photo=img, caption="💳 Ваш чек:")
                else:
                    logger.error(f"Failed to download receipt image for PaymentId {payment_id}")
            except Exception as e:
                logger.error(f"Error while sending receipt: {str(e)}")
        else:
            logger.warning(f"No receipt URL found for PaymentId {payment_id}")

    return {"Success": True}


# Обработка платежей от PayOK
@app.post('/api/pay/payok')
async def check_pay_payok(payment_id: Annotated[str, Form()], amount: Annotated[str, Form()]):

    await process_pay(payment_id, int(amount))  # Обрабатываем платеж
    raise HTTPException(200)


@app.post('/api/midjourney/{action_id}')
async def get_midjourney_with_id(action_id: int, request: Request):
    return await handle_midjourney_webhook(action_id=action_id, request=request)

@app.post('/api/midjourney')
async def get_midjourney_without_id(request: Request):
    body = await request.body()
    logger.info(f"RAW Webhook request: {body.decode()}")
    return await handle_midjourney_webhook(action_id=None, request=request)

async def handle_midjourney_webhook(action_id: Optional[int], request: Request):

    logger.info(f"Получен webhook от MidJourney с action_id: {action_id}, request: {request}")

    try:
        data = await request.json()
        logger.info(f"Получен webhook: {data}")
    except Exception as e:
        logger.error(f"Не удалось разобрать JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if action_id:
        action = await db.get_action(action_id)
    else:
        # Извлекаем task_id из тела запроса
        task_id = data.get('task_id') or data.get('external_task_id')
        if not task_id:
            logger.error("В запросе отсутствует task_id")
            raise HTTPException(status_code=400, detail="Missing task_id")
        action = await db.get_action_by_task_id(task_id)
        action_id = action['id']

    if not action:
        task_id = data.get('task_id') or data.get('external_task_id')
        logger.error(f"Action not found для action_id: {action_id} или task_id: {task_id}")
        raise HTTPException(status_code=404, detail="Action not found")

    user_id = action["user_id"]
    user = await db.get_user(user_id)

    if data.get('status') != 'failed':
        logger.info(f"Полученные данные в webhook: {data}")
        # Извлекаем правильный URL изображения
        if 'task_result' in data:
            image_url = data["task_result"]["image_url"]
        elif 'original_image_url' in data:
            image_url = data["original_image_url"]
        elif 'image_url' in data:
            image_url = data["image_url"]
        elif data['status'] == 'processing' or data['status'] == 'starting':
            return 200

        if not image_url:
            logger.error("В ответе отсутствует image_url или original_image_url")
            raise HTTPException(status_code=400, detail="Missing image URL")

        image_path = f'photos/{action_id}.png'

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        with open(image_path, "wb") as f:
                            f.write(await resp.read())
                        logger.info(f"Изображение сохранено по пути: {image_path}")
                    else:
                        logger.error(f"Не удалось загрузить изображение: статус {resp.status}")
                        await bot.send_message(user_id, "Не удалось загрузить изображение.")
                        return JSONResponse(status_code=500, content={"status": "error"})
        except Exception as e:
            logger.error(f"Ошибка при загрузке изображения: {e}")
            await bot.send_message(user_id, "Произошла ошибка при загрузке изображения.")
            return JSONResponse(status_code=500, content={"status": "error"})

        # Отправка изображения пользователю
        try:
            with open(image_path, "rb") as photo:
                if action["image_type"] in ("imagine", "vary", "zoom"):
                    await bot.send_photo(
                        user_id, photo,
                        reply_markup=user_kb.get_try_prompt_or_choose(action_id, include_try=True)
                    )
                    if user["free_image"] > 0:
                        await db.remove_free_image(user_id)
                    else:
                        await db.remove_image(user_id)
                elif action["image_type"] == "upscale":
                    await bot.send_photo(
                        user_id, photo,
                        reply_markup=user_kb.get_choose(action_id)
                    )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            await bot.send_message(user_id, "Произошла ошибка при отправке изображения.")
            return JSONResponse(status_code=500, content={"status": "error"})

        return JSONResponse(status_code=200, content={"status": "ok"})

    else:
        error_messages = ''.join(data['task_result'].get('error_messages', []))
        await bot.send_message(user_id, f"Произошла ошибка, подробности ошибки:\n\n{error_messages}")
        return JSONResponse(status_code=200, content={"status": "error"})


@app.post('/api/midjourney/choose')
async def get_midjourney_choose(request: Request):
    data = await request.json()
    action_id = int(data["ref"])
    action = await db.get_action(action_id)
    user_id = action["user_id"]
    photo_url = data["imageUrl"]
    logger.info(f'data: {data}')
    await send_mj_photo(user_id, photo_url, user_kb.get_choose(data["buttonMessageId"], action["api_key_number"]))
    await db.set_action_get_response(action_id)
    await db.remove_image(user_id)


@app.post('/api/midjourney/button')
async def get_midjourney_button(request: Request):
    await asyncio.sleep(1)
    data = await request.json()
    action_id = int(data["ref"])
    action = await db.get_action(action_id)
    user_id = action["user_id"]
    photo_url = data["imageUrl"]
    await send_mj_photo(user_id, photo_url,
                        user_kb.get_try_prompt_or_choose(data["buttonMessageId"], action["api_key_number"]))
    user = await db.get_user(user_id)
    await db.set_action_get_response(action_id)
    if user["free_image"] > 0:
        await db.remove_free_image(user["user_id"])
    else:
        await db.remove_image(user["user_id"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")