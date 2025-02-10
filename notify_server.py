from keyboards import user as user_kb  # Импорт пользовательских клавиатур
from fastapi import FastAPI  # Импорт FastAPI для создания веб-сервера
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # Импорт асинхронного планировщика задач
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError  # Обработка ошибок планировщика
from datetime import datetime, timedelta  # Работа с датами и временем

from pydantic import BaseModel  # Базовая модель данных для валидации входящих данных
from create_bot import bot  # Импорт бота
from utils import db  # Импорт базы данных
import uvicorn  # Сервер для запуска FastAPI


# Инициализация FastAPI приложения
app = FastAPI()

# Инициализация асинхронного планировщика задач
scheduler = AsyncIOScheduler()


# Модель для обработки webhook от системы Lava (платежная система)
class LavaWebhook(BaseModel):

    order_id: str  # Идентификатор заказа
    status: str  # Статус платежа
    amount: float  # Сумма платежа


# Функция для отправки уведомления пользователю о бонусе при пополнении
async def stock_notify(user_id):

    await bot.send_message(user_id,
                           "Успей пополнить баланс в течении 24 часов и получи на счёт +30% от суммы пополнения⤵️",
                           reply_markup=user_kb.get_pay(user_id, 30))  # Отправка сообщения пользователю с кнопками
    await db.update_new_stock_time(user_id, int(datetime.now().timestamp()))  # Обновляем время для бонуса


# Функция для отправки уведомления пользователю, если произошла ошибка с действием (например, генерация изображения)
async def action_notify(action_id):

    action = await db.get_action(action_id)  # Получаем информацию о действии
    if not action["get_response"]:  # Если не получен ответ
        await bot.send_message(action["user_id"],
                               "⚠️Произошла какая-то ошибка, попробуйте другой запрос.")  # Уведомляем пользователя


# Событие, которое запускается при старте приложения — запускает планировщик задач
@app.on_event('startup')
def init_scheduler():

    scheduler.start()  # Запуск планировщика


# Маршрут для создания уведомления о действии через вебхуки
@app.post('/action/{action_id}')
async def create_action_notify_request(action_id: int):

    run_date = datetime.now() + timedelta(minutes=5)  # Устанавливаем время запуска задачи через 5 минут
    try:
        # Добавляем задачу в планировщик
        scheduler.add_job(action_notify, "date", run_date=run_date, args=[action_id], id=str(action_id))
    except ConflictingIdError:
        # Если задача с таким ID уже существует, удаляем её и добавляем заново
        scheduler.remove_job(str(action_id))
        scheduler.add_job(action_notify, "date", run_date=run_date, args=[action_id], id=str(action_id))


# Маршрут для создания уведомления о бонусе при пополнении
@app.post('/stock/{user_id}')
async def create_notify_request(user_id: int):
    
    run_date = datetime.now() + timedelta(minutes=10)  # Устанавливаем время запуска задачи через 10 минут
    try:
        # Добавляем задачу в планировщик
        scheduler.add_job(stock_notify, "date", run_date=run_date, args=[user_id], id=str(user_id))
    except ConflictingIdError:
        # Если задача с таким ID уже существует, удаляем её и добавляем заново
        scheduler.remove_job(str(user_id))
        scheduler.add_job(stock_notify, "date", run_date=run_date, args=[user_id], id=str(user_id))


# Маршрут для удаления задачи уведомления о бонусе при пополнении
@app.delete('/stock/{user_id}')
async def delete_notify_request(user_id: int):
    
    try:
        scheduler.remove_job(str(user_id))  # Удаляем задачу из планировщика
    except JobLookupError:
        return  # Игнорируем, если задачи не было найдено


# Запуск приложения через Uvicorn (если файл запущен как скрипт)
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
