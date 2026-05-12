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
from fastapi.responses import JSONResponse, HTMLResponse
import html as html_lib
from pydantic import BaseModel  # Импорт базовой модели данных
from create_bot import bot  # Импорт бота
from io import BytesIO
from PIL import Image
from utils import db  # Импорт функций работы с базой данных
from utils.mj_apis import friendly_mj_error
import requests  # Для синхронных HTTP-запросов
import uvicorn  # Для запуска сервера FastAPI
from typing import Optional

import uuid

from utils.pay import get_receipt_url
from utils.history_token import verify_history_token

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
async def send_mj_photo(user_id, photo_url, kb, caption=None):

    try:
        response = requests.get(photo_url, timeout=5)
    except requests.exceptions.Timeout:
        img = photo_url
    except requests.exceptions.ConnectionError:
        img = photo_url
    else:
        img = BytesIO(response.content)
    await bot.send_photo(user_id, photo=img, caption=caption, reply_markup=kb)


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
            print(f"Чек доступен по ссылке: {receipt_url}")
        else:
            print("Чек не найден или произошла ошибка")

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


async def make_grid_from_urls(session: aiohttp.ClientSession, image_urls: list) -> bytes:
    images = []
    for url in image_urls[:4]:
        async with session.get(url) as resp:
            data = await resp.read()
            images.append(Image.open(BytesIO(data)).convert('RGB'))
    w, h = images[0].size
    grid = Image.new('RGB', (w * 2, h * 2))
    for i, img in enumerate(images):
        grid.paste(img, (i % 2 * w, i // 2 * h))
    buf = BytesIO()
    grid.save(buf, format='PNG')
    return buf.getvalue()


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
        # Legnext оборачивает payload в поле 'data'
        if 'data' in data and isinstance(data['data'], dict):
            data = data['data']
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

    # Атомарный лок: первый пришедший webhook резервирует action, все последующие
    # (дубль Legnext или второй webhook после v7+turbo retry) — early return.
    # Также закрывает race с watchdog: флаг ставится сразу, а не после save+send_photo.
    if not await db.try_lock_action_for_webhook(action_id):
        logger.info(f"[idempotent] action_id {action_id} уже обработан, дубликат пропущен")
        return JSONResponse(status_code=200, content={"status": "duplicate_ignored"})

    user_id = action["user_id"]
    user = await db.get_user(user_id)

    if data.get('status') != 'failed':
        logger.info(f"Полученные данные в webhook: {data}")
        # Извлекаем URL(ы) изображения
        image_url = None
        image_urls_list = None
        if 'task_result' in data:
            image_url = data["task_result"]["image_url"]
        elif 'output' in data and data.get('output', {}).get('image_url'):
            image_url = data["output"]["image_url"]
            urls = data["output"].get("image_urls")
            if urls and len(urls) >= 4:
                image_urls_list = urls[:4]
        elif 'original_image_url' in data:
            image_url = data["original_image_url"]
        elif 'image_url' in data:
            image_url = data["image_url"]
        elif data['status'] == 'processing' or data['status'] == 'starting':
            return 200

        if not image_url:
            logger.error("В ответе отсутствует image_url")
            raise HTTPException(status_code=400, detail="Missing image URL")

        image_path = f'photos/{action_id}.png'

        try:
            async with aiohttp.ClientSession() as session:
                if image_urls_list:
                    # Legnext: собираем коллаж 2x2 из 4 картинок
                    image_data = await make_grid_from_urls(session, image_urls_list)
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    logger.info(f"Коллаж 2x2 сохранён: {image_path}")
                    # Сохраняем каждую из 4 картинок отдельно для выбора без upscale
                    for idx, url in enumerate(image_urls_list, start=1):
                        async with session.get(url) as r:
                            if r.status == 200:
                                with open(f'photos/{action_id}_{idx}.png', 'wb') as f:
                                    f.write(await r.read())
                else:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            with open(image_path, "wb") as f:
                                f.write(await resp.read())
                            logger.info(f"Изображение сохранено: {image_path}")
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
                        caption="Выберите вариант изображения\nКнопки активны 15 минут",
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

        # get_response уже выставлен в try_lock_action_for_webhook на входе.
        return JSONResponse(status_code=200, content={"status": "ok"})

    else:
        # GoAPI: task_result.error_messages (список строк)
        # Legnext: error.message (строка внутри словаря)
        err = data.get('task_result', {}).get('error_messages')
        if err:
            error_messages = ''.join(err)
        else:
            raw = data.get('error', {})
            error_messages = raw.get('message', '') if isinstance(raw, dict) else str(raw)
        logger.error(f"MJ generation failed for user {user_id}, action {action_id}: {error_messages!r}")
        await bot.send_message(user_id, friendly_mj_error(error_messages))
        # get_response уже выставлен в try_lock_action_for_webhook на входе.
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
                        user_kb.get_try_prompt_or_choose(data["buttonMessageId"], action["api_key_number"]),
                        caption="Выберите вариант изображения\nКнопки активны 15 минут")
    user = await db.get_user(user_id)
    await db.set_action_get_response(action_id)
    if user["free_image"] > 0:
        await db.remove_free_image(user["user_id"])
    else:
        await db.remove_image(user["user_id"])


@app.get("/history/{chat_id}", response_class=HTMLResponse)
async def chat_history_page(chat_id: int, uid: int, token: str):
    if not verify_history_token(uid, chat_id, token):
        raise HTTPException(status_code=403, detail="Forbidden")

    chat = await db.get_chat_by_id(chat_id)
    if not chat or chat["user_id"] != uid:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = await db.get_chat_messages(chat_id, uid, offset=0, limit=25)
    if messages is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages_asc = list(reversed(messages))
    has_more = len(messages) == 25
    initial_offset = len(messages)

    chat_name = html_lib.escape(chat["name"] or "Диалог")
    created_at = chat["created_at"].strftime("%d.%m.%Y")

    msgs_html = ""
    for msg in messages_asc:
        is_user = msg["user_id"] is not None
        role_class = "user" if is_user else "bot"
        raw = msg["text"] or ""
        text = html_lib.escape(raw) if is_user else raw
        time_str = msg["created_at"].strftime("%H:%M")
        msgs_html += (
            f'<div class="msg-wrap {role_class}">'
            f'<div class="bubble">'
            f'<div class="text">{text}</div>'
            f'<div class="time">{time_str}</div>'
            f'</div></div>\n'
        )

    load_btn_display = "block" if has_more else "none"

    page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>История диалога</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--tg-theme-bg-color, #18222d);
  color: var(--tg-theme-text-color, #e0e0e0);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}}
.header {{
  position: sticky; top: 0;
  background: var(--tg-theme-secondary-bg-color, #1f2936);
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  z-index: 10;
}}
.header h2 {{
  font-size: 16px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.header .meta {{ font-size: 12px; opacity: 0.6; margin-top: 2px; }}
#load-more-wrap {{ text-align: center; padding: 10px; display: {load_btn_display}; }}
#load-more-btn {{
  background: var(--tg-theme-button-color, #2b5278);
  color: var(--tg-theme-button-text-color, #fff);
  border: none; border-radius: 20px;
  padding: 8px 20px; font-size: 14px; cursor: pointer;
}}
#messages {{
  flex: 1; padding: 12px 10px;
  display: flex; flex-direction: column; gap: 6px;
}}
.msg-wrap {{ display: flex; width: 100%; }}
.msg-wrap.user {{ justify-content: flex-end; }}
.msg-wrap.bot  {{ justify-content: flex-start; }}
.bubble {{
  max-width: 78%; padding: 8px 12px;
  border-radius: 16px; word-break: break-word;
}}
.msg-wrap.user .bubble {{
  background: var(--tg-theme-button-color, #2b5278);
  color: var(--tg-theme-button-text-color, #fff);
  border-bottom-right-radius: 4px;
}}
.msg-wrap.bot .bubble {{
  background: var(--tg-theme-secondary-bg-color, #1f2936);
  color: var(--tg-theme-text-color, #e0e0e0);
  border-bottom-left-radius: 4px;
}}
.text {{ font-size: 14px; line-height: 1.5; white-space: pre-wrap; }}
.time {{ font-size: 11px; opacity: 0.55; margin-top: 4px; text-align: right; }}
</style>
</head>
<body>
<div class="header">
  <h2>{chat_name}</h2>
  <div class="meta">Создан: {created_at}</div>
</div>
<div id="load-more-wrap">
  <button id="load-more-btn" onclick="loadMore()">&#11014; Загрузить ещё</button>
</div>
<div id="messages">
{msgs_html}</div>
<script>
let offset = {initial_offset};
const chatId = {chat_id};
const uid = {uid};
const token = "{token}";

function escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

async function loadMore() {{
  const btn = document.getElementById('load-more-btn');
  btn.disabled = true; btn.textContent = '...';
  const res = await fetch(`/api/history/${{chatId}}/messages?uid=${{uid}}&token=${{token}}&offset=${{offset}}`);
  if (!res.ok) {{ btn.disabled = false; btn.textContent = '&#11014; Загрузить ещё'; return; }}
  const data = await res.json();
  if (data.length === 0) {{
    document.getElementById('load-more-wrap').style.display = 'none';
    return;
  }}
  offset += data.length;
  const container = document.getElementById('messages');
  const frag = document.createDocumentFragment();
  data.reverse().forEach(msg => {{
    const wrap = document.createElement('div');
    wrap.className = 'msg-wrap ' + (msg.is_user ? 'user' : 'bot');
    const textContent = msg.is_user ? escHtml(msg.text) : msg.text;
    wrap.innerHTML = '<div class="bubble"><div class="text">' + textContent +
      '</div><div class="time">' + msg.time + '</div></div>';
    frag.appendChild(wrap);
  }});
  container.insertBefore(frag, container.firstChild);
  if (data.length < 25) {{
    document.getElementById('load-more-wrap').style.display = 'none';
  }} else {{
    btn.disabled = false; btn.textContent = '&#11014; Загрузить ещё';
  }}
}}

window.onload = () => {{ window.scrollTo(0, document.body.scrollHeight); }};
</script>
</body>
</html>"""
    return HTMLResponse(content=page)


@app.get("/api/history/{chat_id}/messages")
async def chat_history_messages(chat_id: int, uid: int, token: str, offset: int = 0):
    if not verify_history_token(uid, chat_id, token):
        raise HTTPException(status_code=403, detail="Forbidden")

    messages = await db.get_chat_messages(chat_id, uid, offset=offset, limit=25)
    if messages is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    return JSONResponse([{
        "is_user": msg["user_id"] is not None,
        "text": msg["text"] or "",
        "time": msg["created_at"].strftime("%H:%M"),
    } for msg in messages])


if __name__ == "__main__":
    import os
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")