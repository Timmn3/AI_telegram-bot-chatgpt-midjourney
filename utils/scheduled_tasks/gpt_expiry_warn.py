import logging
from datetime import datetime
from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from create_bot import bot
from config import bot_url
from utils import db

logger = logging.getLogger(__name__)


async def gpt_expiry_warn_job(days_left: int = 3):
    """
    Уведомляем пользователей за N дней до окончания доступа к ChatGPT.
    Чтобы не спамить, используем флаг users.gpt_expire_warned.
    """
    rows = await db.get_users_gpt_expiring(days_left=days_left)
    if not rows:
        logger.info("[gpt-expiry-warn] нет пользователей для уведомления")
        return

    sent = 0
    for r in rows:
        user_id = int(r["user_id"])

        ref_link = f"{bot_url}?start=r{user_id}"
        share_url = f"https://t.me/share/url?url={quote(ref_link)}"

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("📩 Поделиться ссылкой (+14 дней)", url=share_url))

        try:
            await bot.send_message(
                user_id,
                "⚠️ <b>Доступ к ChatGPT отключится через 3 дня</b>\n\n"
                "Для дальнейшего использования, приглашай друзей и получай "
                "<b>+14 дней ChatGPT</b> за каждого реферала 🎁\n\n"
                f"{ref_link}\n\n"
                "Приглашенный друг по вашей ссылке, получает <b>14 дней</b> ChatGPT бесплатно 🎁",
                reply_markup=keyboard,
                disable_web_page_preview=True,
                parse_mode="HTML",
            )

            await db.set_gpt_expire_warned(user_id, True)
            sent += 1
        except Exception as e:
            logger.warning(f"[gpt-expiry-warn] не удалось отправить пользователю {user_id}: {e}")

    logger.info(f"[gpt-expiry-warn] отправлено уведомлений: {sent}/{len(rows)}")
