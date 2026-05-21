from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils import db

_banned_keyboard = InlineKeyboardMarkup().add(
    InlineKeyboardButton("✉️ Написать в поддержку", url="https://t.me/NeuronSupportBot")
)

_BAN_TEXT = (
    "🚫 <b>Ваш аккаунт заблокирован.</b>\n\n"
    "Если вы считаете, что произошла ошибка — обратитесь в поддержку."
)


class BanCheckMiddleware(BaseMiddleware):

    async def on_pre_process_message(self, message: types.Message, data: dict):
        if await db.is_user_banned(message.from_user.id):
            await message.answer(_BAN_TEXT, reply_markup=_banned_keyboard)
            raise CancelHandler()

    async def on_pre_process_callback_query(self, callback_query: types.CallbackQuery, data: dict):
        if await db.is_user_banned(callback_query.from_user.id):
            await callback_query.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
            raise CancelHandler()
