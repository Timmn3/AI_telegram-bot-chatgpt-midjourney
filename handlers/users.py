import logging
from datetime import datetime, timedelta
from typing import List
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ChatActions, ContentType, MediaGroup, Update, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext
import re
import tempfile
import os
from urllib import parse
from keyboards.user import image_openai_menu, partner
from states.user import EnterChatName, EnterChatRename
from utils import db, ai, more_api, pay  # Импорт утилит для взаимодействия с БД и внешними API
from states import user as states  # Состояния FSM для пользователя
import keyboards.user as user_kb  # Клавиатуры для взаимодействия с пользователями
from config import bot_url, TOKEN, NOTIFY_URL, bug_id, PHOTO_PATH, MJ_PHOTO_BASE_URL, ADMINS_CODER, check_channel
from create_bot import dp, bot  # Диспетчер из create_bot.py
from utils.ai import mj_api, text_to_speech, voice_to_text
from aiogram.utils.exceptions import CantParseEntities, RetryAfter
import html
import asyncio

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')

vary_types = {"subtle": "Subtle", "strong": "Strong"}  # Типы для использования в дальнейшем

'''
# Проверка и активация промокодов
async def check_promocode(user_id, code, bot: Bot):

    promocode = await db.get_promocode_by_code(code)  # Получаем промокод по коду
    if promocode is None:
        return
    # Проверяем, использовал ли пользователь этот промокод ранее
    user_promocode = await db.get_user_promocode_by_promocode_id_and_user_id(promocode["promocode_id"], user_id)
    all_user_promocode = await db.get_all_user_promocode_by_promocode_id(promocode["promocode_id"])

    # Если пользователь не использовал промокод и есть свободные активации, применяем его
    if user_promocode is None and len(all_user_promocode) < promocode["uses_count"]:
        await db.create_user_promocode(promocode["promocode_id"], user_id)
        await db.add_balance(user_id, promocode['amount'], is_promo=True)  # Пополняем баланс на сумму промокода
        await bot.send_message(user_id, f"<b>Баланс пополнен на {promocode['amount']} рублей.</b>")
    else:
        # Уведомление, если промокод уже использован или исчерпаны активации
        if user_promocode is not None:
            await bot.send_message(user_id, "<b>Данная ссылка была активирована Вами ранее.</b>")
        elif len(all_user_promocode) >= promocode["uses_count"]:
            await bot.send_message(user_id, "<b>Ссылка исчерпала максимальное количество активаций.</b>")
'''


# Хэндлер команды /start
@dp.message_handler(state="*", commands='start')
async def start_message(message: Message, state: FSMContext):
    try:
        # Завершаем текущее состояние (если оно есть)
        await state.finish()
    except Exception as e:
        logger.warning(f"Не удалось очистить состояние: {e}")
    try:
        await state.reset_data()
    except Exception:
        pass

    # Обрабатываем параметры команды /start (например, реферальные коды)
    msg_args = message.get_args().split("_")
    inviter_id = 0
    code = None
    if msg_args != ['']:
        for msg_arg in msg_args:
            if msg_arg[0] == "r":
                try:
                    inviter_id = int(msg_arg[1:])
                except ValueError:
                    continue
            elif msg_arg[0] == "p":
                code = msg_arg[1:]

    user = await db.get_user(message.from_user.id)

    if user is None:
        await db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, int(inviter_id))
        await db.change_default_ai(message.from_user.id, "chatgpt")  # ← фиксируем ChatGPT в БД на этапе регистрации
        default_ai = "chatgpt"

        # Уведомление пригласившего пользователя + продление ChatGPT на 14 дней
        if inviter_id != 0 and int(inviter_id) != int(message.from_user.id):
            inviter = await db.get_user(inviter_id)
            if inviter:
                # ✅ продлеваем доступ пригласившему
                await db.extend_gpt_access(inviter_id, 14)
                await db.add_gpt_referral_days(inviter_id, 14)

                # берём обновлённые данные, чтобы показать новую дату
                inviter_after = await db.get_user(inviter_id)
                access_until = inviter_after.get("gpt_access_until")

                if access_until:
                    until_str = access_until.strftime("%d.%m.%Y %H:%M")
                else:
                    until_str = "—"

                # 🔔 уведомление (если включено)
                if inviter_after.get("ref_notifications_enabled", True):
                    try:
                        keyboard = InlineKeyboardMarkup().add(
                            InlineKeyboardButton(
                                "Отключить уведомления",
                                callback_data="disable_ref_notifications"
                            )
                        )
                        await bot.send_message(
                            inviter_id,
                            f"""🎉 <b>У Вас новый реферал</b>
└ Аккаунт: <code>{message.from_user.id}</code>

✅ <b>Добавили вам +14 дней ChatGPT</b>
⏳ Доступ до: <b>{until_str}</b>""",
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        logging.warning(f"Не удалось отправить уведомление о реферале: {e}")

        await message.answer(
            """ 👋 Добро пожаловать!
🎁 <b>У вас активирован пробный тариф на 14 дней.</b>

Бот подходит для множества задач:
💬 <b>ChatGPT</b> — ответы на вопросы, анализ изображений, помощь с текстами, идеями и задачами
🎨 <b>Midjourney</b> — создание изображений по вашему описанию
<b>Выберите, с чего хотите начать</b> 👇 """,
            reply_markup=user_kb.get_start_inline()
        )
    else:
        await db.change_default_ai(message.from_user.id, "chatgpt")
        example_prompt = await generate_example_prompt()
        await message.answer(
            f"""<b>Введите запрос</b>
Например: <code>{example_prompt}</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-ChatGPT-podrobnaya-instrukciya-06-04">Подробная инструкция.</a></u>""",
            reply_markup=user_kb.get_menu("chatgpt"),
            disable_web_page_preview=True
        )


# Снижение баланса пользователя
async def remove_balance(bot: Bot, user_id):
    await db.remove_balance(user_id)
    user = await db.get_user(user_id)
    # Если баланс меньше 50, отправляем уведомление о необходимости пополнения
    if user["balance"] <= 50:
        await db.update_stock_time(user_id, int(datetime.now().timestamp()))
        await bot.send_message(user_id, """ ⚠️ Заканчивается баланс!
Успей пополнить в течении 24 часов и получи на счёт +10% от суммы пополнения ⤵️""",
                               reply_markup=user_kb.get_pay(user_id, 10))  # Кнопка пополнения баланса


# Функция для уведомления пользователя о недостатке средств
async def not_enough_balance(bot: Bot, user_id: int, ai_type: str):
    now = datetime.now()
    if ai_type == "chatgpt":
        user = await db.get_user(user_id)
        model = user["gpt_model"]

        logger.info(f"Токены для ChatGPT закончились. User: {user}, Model: {model}")

        if model == '5':
            await db.set_model(user_id, "5-mini")
            await bot.send_message(user_id, "⚠️ Превышен допустимый лимит запросов модели GPT-5.2\n"
                                            "✅ Модель для ChatGPT изменена на GPT-5-mini")
        elif model == '5-mini':
            await db.set_model(user_id, "5")
            # await bot.send_message(user_id, "⚠️ Превышен допустимый лимит запросов модели GPT-5-mini\n"
            #                                 "✅ Модель для ChatGPT изменена на GPT-5")
        else:
            await bot.send_message(user_id,
                               f"⚠️ Превышен допустимый лимит запросов, попробуйте позже")  # Отправляем уведомление с клавиатурой для пополнения токенов


    elif ai_type == "image":
        user_data = await db.get_user_notified_mj(user_id)

        if user_data and user_data['last_notification']:
            last_notification = user_data['last_notification']

            # Если уведомление было менее 24 часов назад, показываем меню со скидкой
            if now < last_notification + timedelta(hours=24):
                await bot.send_message(user_id, """
Выберите количество запросов⤵️
                """,
                                       reply_markup=user_kb.get_midjourney_discount_requests_menu()
                                       )
                return
        await bot.send_message(user_id, """
Выберите количество запросов⤵️
        """,
                               reply_markup=user_kb.get_midjourney_requests_menu())  # Отправляем уведомление с клавиатурой для пополнения запросов

    elif ai_type == "image_openai":
        await bot.send_message(user_id, """
        ⚠️ Запросы для "Изображения от OpenAI" закончились!

        Выберите интересующий вас вариант⤵️
                """,
                               reply_markup=user_kb.get_midjourney_requests_menu())


# Генерация изображения через MidJourney
async def get_mj(prompt, user_id, bot: Bot):
    user = await db.get_user(user_id)

    # Проверяем наличие запросов и отправляем уведомление, если запросы исчерпаны
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(bot, user_id, "image")  # Отправляем уведомление о недостатке средств
        return

    await bot.send_message(user_id, "Ожидайте, генерирую изображение.. 🕙 ",
                           reply_markup=user_kb.get_menu(user["default_ai"]))
    # await bot.send_message(user_id, "В настоящее время генерация не доступна, попробуйте позже!")
    await bot.send_chat_action(user_id, ChatActions.UPLOAD_PHOTO)

    if '—' in prompt:
        prompt.replace('—', '--')

    res = await ai.get_mdjrny(prompt, user_id)  # Получаем изображение через API

    logger.info(f"MidJourney: {res}")

    if res is None:
        await bot.send_message(user_id, f"Произошла ошибка, повторите попытку позже")
        return
    elif ('Banned Prompt' in res):
        await bot.send_message(user_id, f"Запрещенное слово в запросе:\n\n{res}")
        return
    elif ('Invalid image prompt position' in res):
        await bot.send_message(user_id, f"Некорректная структура запроса:\n\n{res}")
        return
    elif ('status' in res) and (res['status'] == "failed"):
        await bot.send_message(user_id, f"Произошла ошибка, подробности ошибки:\n\n{res['message']}")
        return

    await db.mark_used_trial(user_id)
    # Проверка на количество оставшихся запросов MidJourney
    now = datetime.now()
    user_notified = await db.get_user_notified_mj(user_id)
    user = await db.get_user(user_id)  # Получаем обновленные данные пользователя

    if 1 < user["mj"] <= 3:  # Если осталось 3 или меньше запросов
        if user_notified is None:
            await db.create_user_notification_mj(user_id)
            await notify_low_midjourney_requests(user_id, bot)  # Отправляем уведомление о низком количестве токенов
            # await db.set_user_notified(user_id)  # Помечаем, что уведомление отправлено
        else:
            last_notification = user_notified['last_notification']
            if last_notification is None or now > last_notification + timedelta(days=30):
                await db.update_user_notification_mj(user_id)
                await notify_low_midjourney_requests(user_id, bot)

async def gen_image_openai(message: Message):
    await message.answer("Выберите действие:", reply_markup=image_openai_menu)


def split_message(text: str, max_length: int, is_code: bool = False) -> list:
    """Разбивает длинное сообщение на части, не превышающие max_length, с учетом кода."""
    lines = text.split('\n')
    parts = []
    current_part = ""

    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            parts.append(current_part)
            current_part = ""
        current_part += line + '\n'

    if current_part:
        parts.append(current_part)

    if is_code:
        # Оборачиваем каждую часть в <pre><code>...</code></pre>
        return [f"<pre><code>{part.strip()}</code></pre>" for part in parts]

    return parts


def process_formula(match):
    formula = match.group(1)

    # Замены для наиболее популярных команд
    formula = re.sub(r"\\frac\{(.*?)\}\{(.*?)\}", r"\1 / \2", formula)  # \frac{a}{b} → a / b
    formula = re.sub(r"\\text\{(.*?)\}", r"\1", formula)  # \text{...} → обычный текст
    formula = formula.replace(r"\times", "×").replace(r"\cdot", "·")  # Умножение
    formula = formula.replace(r"\implies", "⇒").replace(r"\approx", "≈")  # Символы логики
    formula = re.sub(r"\\sqrt\{(.*?)\}", r"√(\1)", formula)  # Корень: \sqrt{a} → √(a)

    # Обработка степеней: x^2 → x² (для цифр 0–9)
    def replace_power(m):
        base, exp = m.group(1), m.group(2)
        try:
            exp_int = int(exp)
            if 0 <= exp_int <= 9:
                return f"{base}{chr(8304 + exp_int)}"
            else:
                return f"{base}^{exp}"  # для более сложных степеней
        except ValueError:
            return f"{base}^{exp}"
    formula = re.sub(r"([a-zA-Z])\^([0-9]+)", replace_power, formula)

    # Индексы: t_1 → t₁
    def replace_subscript(m):
        base, sub = m.group(1), m.group(2)
        try:
            sub_int = int(sub)
            if 0 <= sub_int <= 9:
                return f"{base}{chr(8320 + sub_int)}"
            else:
                return f"{base}_{sub}"
        except ValueError:
            return f"{base}_{sub}"
    formula = re.sub(r"([a-zA-Z])_([0-9]+)", replace_subscript, formula)

    # Углы: \degree → °
    formula = re.sub(r"\\degree", "°", formula)

    # Греческие буквы
    greek_letters = {
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε",
        r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ",
        r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\omicron": "ο",
        r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ",
        r"\phi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω"
    }
    for latex, symbol in greek_letters.items():
        formula = formula.replace(latex, symbol)

    # Замена потенциально нечитабельных символов
    formula = formula.replace("⁲", "²")

    # Убираем все оставшиеся неизвестные надстрочные символы, кроме ² и ³
    formula = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]", lambda m: m.group(0) if m.group(0) in "²³" else "", formula)

    # Убираем лишние \ (после всех замен)
    formula = formula.replace("\\", "")

    # Экранирование оставшихся символов для правильного отображения в Telegram
    return f"<pre>{html.escape(formula.strip())}</pre>"




def normalize_telegram_html(text: str) -> str:
    """
    Нормализует HTML-ответ под ограничения Telegram HTML.

    Что делает:
    - заменяет <br>, <br/>, <br /> на обычные переводы строк;
    - убирает проблемные блочные теги <p>, <div>;
    - очищает лишние атрибуты у <pre> и <code>;
    - приводит текст к более безопасному виду для parse_mode="HTML".

    :param text: Исходный текст ответа
    :return: Нормализованный текст для Telegram HTML
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Telegram HTML не поддерживает <br/>
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)

    # Убираем часто встречающиеся блочные теги, которые Telegram тоже не любит
    text = re.sub(r"(?i)<p\s*>", "", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<div\s*>", "", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)

    # Неразрывные пробелы
    text = text.replace("&nbsp;", " ")

    # Нормализуем code/pre, если модель добавила атрибуты
    text = re.sub(r"(?is)<pre\b[^>]*>\s*<code\b[^>]*>", "<pre><code>", text)
    text = re.sub(r"(?is)</code>\s*</pre>", "</code></pre>", text)
    text = re.sub(r"(?is)<pre\b[^>]*>", "<pre>", text)
    text = re.sub(r"(?is)<code\b[^>]*>", "<code>", text)

    # Чистим избыточные пустые строки
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def format_math_in_text(text: str) -> str:
    """
    Обрабатывает LaTeX-подобные формулы в тексте и сохраняет Telegram HTML-разметку.

    Важно:
    - не экранирует весь текст через html.escape(...),
      иначе ломаются <b>, <i>, <code>, <pre> и другие допустимые Telegram HTML-теги;
    - только преобразует формулы и затем нормализует HTML под Telegram.

    :param text: Исходный текст ответа модели
    :return: Подготовленный текст для отправки в Telegram
    """
    if not text:
        return ""

    # Обработка формул внутри \[...\] и \(...\)
    text = re.sub(r"\\\[(.*?)\\\]", process_formula, text, flags=re.DOTALL)
    text = re.sub(r"\\\((.*?)\\\)", process_formula, text, flags=re.DOTALL)

    return normalize_telegram_html(text)


async def send_message_with_html(bot: Bot, chat_id: int, text: str, reply_markup=None):
    """
    Отправляет сообщение в Telegram с parse_mode="HTML".

    Логика:
    1. Сначала нормализуем HTML под ограничения Telegram.
    2. Пробуем отправить как HTML.
    3. Если Telegram не смог распарсить сущности, отправляем безопасный plain text,
       чтобы пользователь не видел сырые HTML-теги.

    :param bot: Экземпляр бота
    :param chat_id: ID чата
    :param text: Текст сообщения
    :param reply_markup: Клавиатура (опционально)
    """
    safe_text = normalize_telegram_html(text)

    try:
        await bot.send_message(
            chat_id,
            safe_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

    except CantParseEntities as e:
        logger.warning(f"Telegram не смог распарсить HTML: {e}")

        # Запасной вариант: убираем все HTML-теги, чтобы не показывать пользователю сырой HTML
        plain_text = re.sub(r"(?is)<[^>]+>", "", safe_text)
        plain_text = html.unescape(plain_text).strip()

        await bot.send_message(
            chat_id,
            plain_text if plain_text else "Произошла ошибка форматирования ответа.",
            reply_markup=reply_markup
        )

    except RetryAfter as e:
        await asyncio.sleep(e.timeout + 0.1)
        await bot.send_message(
            chat_id,
            safe_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.exception(f"Ошибка отправки сообщения: {e}")

        plain_text = re.sub(r"(?is)<[^>]+>", "", safe_text)
        plain_text = html.unescape(plain_text).strip()

        await bot.send_message(
            chat_id,
            plain_text if plain_text else "Произошла ошибка отправки ответа.",
            reply_markup=reply_markup
        )



def ensure_code_block_integrity(text: str) -> str:
    """Гарантирует, что <pre><code> и </code></pre> используются корректно."""
    has_open = "<pre><code>" in text
    has_close = "</code></pre>" in text

    if has_open and not has_close:
        return text + "</code></pre>"
    elif has_close and not has_open:
        return "<pre><code>" + text
    return text


async def get_gpt(prompt, messages, user_id, bot: Bot, state: FSMContext):
    """
    Основной запрос к GPT.
    Отличие от предыдущей версии: после отправки ответа пользователю «тяжёлые» шаги
    (имя чата, keywords, summary) выполняются в фоне и НЕ блокируют обработку следующих апдейтов.
    """
    text = '⏳ ChatGPT генерирует ответ, ожидайте...'
    message_wait = await bot.send_message(user_id, text)
    try:
        user = await db.get_user(user_id)
        lang_text = {"en": "compose an answer in English", "ru": "составь ответ на русском языке"}
        model = user['gpt_model']
        model_dashed = model.replace("-", "_")

        current_chat = await db.get_chat_by_id(user["current_chat_id"])
        summary = current_chat["summary"] if current_chat else ""
        keywords = current_chat["keywords"] if current_chat and current_chat.get("keywords") else []

        # Подмешиваем summary/keywords в промпт, если есть
        if summary:
            prompt = f"Ранее в этом чате обсуждалось: {summary.strip()}\n\n" + prompt
        if keywords:
            joined_keywords = ', '.join(keywords)
            prompt = f"Ключевые слова, которые стоит учитывать: {joined_keywords}\n\n" + prompt

        prompt += f"\n{lang_text[user['chat_gpt_lang']]}"

        prompt += """
                Ты — полезный, понятный и внимательный AI-помощник для Telegram-бота.

                Отвечай так, чтобы сообщения были: 
                - структурированными; 
                - развёрнутыми и содержательными; 
                - легко читаемыми в Telegram; 
                - визуально аккуратными; 
                - полезными уже с первого абзаца; 
                - дружелюбными, но без лишней воды.

                Общие правила ответа:
                1. Всегда сначала давай прямой, содержательный ответ по сути вопроса.
                2. Если вопрос требует объяснения, анализа, сравнения, интерпретации, причин, морали, вывода или совета — отвечай развёрнуто, а не поверхностно.
                3. Не ограничивайся общими фразами. Раскрывай причинно-следственные связи: почему именно, за счёт чего, в чём это проявляется, к чему приводит.
                4. Строй ответ по понятным смысловым блокам с абзацами и подзаголовками, вначале абзаца добавляй уместный эмодзи.
                5. По необходимости используй в тексте эмодзи.
                6. Если у вопроса есть несколько уровней раскрытия, строй ответ по логике:
                   - вывод;
                   - основная мысль;
                   - разбор по пунктам;
                   - общий смысл / контекст;
                   - при необходимости короткий итог.
                7. Первый абзац всегда должен сразу давать полезный ответ, а не начинаться с общих рассуждений.
                8. Не делай ответ шаблонным. Количество смысловых блоков определяй по теме, а не по фиксированному шаблону.
                9. Не добавляй бесполезные вступления, повторы и очевидные фразы ради объёма.
                10. Если пользователь просит кратко — отвечай кратко, иначе отвечай максимально подробно.
                11. Добавляй полезное продолжение только если оно действительно уместно.
                13. Если уместно, в конце можно добавить один полезный follow-up и выдели его жирным шрифтом: 
                    - предложить пример; 
                    - предложить современную формулировку; 
                    - предложить переформулировать ответ под конкретный формат;
                    - предложи альтернативные варианты и смежные темы для обсуждения.

                Требования к качеству объяснения:
                1. Ответ должен быть не просто правильным, а понятным: читатель должен увидеть логику рассуждения.
                2. Если вопрос начинается со слов «почему», «зачем», «в чём смысл», «чем отличается», «объясни», «докажи», «сравни», «какова мораль», «в чём причина» — обязательно раскрывай тему глубже среднего.
                3. Если вопрос допускает неоднозначность, показывай основной вывод и затем поясняй нюансы.

                Стиль:
                1. Пиши естественно, уверенно, ясно и содержательно.
                2. Дружелюбный тон допустим, но без излишней легковесности.

                Форматирование под Telegram HTML:
                1. Отправляй сообщения в формате Telegram HTML.
                2. Экранируй спецсимволы HTML в обычном тексте.
                3. Используй только поддерживаемые Telegram HTML-теги.
                4. Для акцента на ключевых мыслях используй <b>...</b>.
                5. Разбивай ответ на удобные абзацы и смысловые блоки.
                6. Не используй длинные сплошные полотна текста.
                7. Не используй Markdown-разметку вместо Telegram HTML.
                8. Не добавляй лишние декоративные разделители.

                Правила для кода:
                1. Показывай код только если пользователь явно просит код, функцию, пример кода или техническую реализацию.
                2. Если в ответе есть программный код:
                   - код не должен превышать 2000 символов;
                   - многострочный код заключай в <pre><code>...</code></pre>;
                   - однострочный код заключай в <code>...</code>.
                3. Если в ответе присутствует HTML-код как пример, оборачивай его в <pre><code>...</code></pre>.
                4. Не смешивай плохо читаемый текст и код в одном абзаце.

                """

        message_user = prompt

        if messages is None:
            messages = []
        messages.append({"role": "user", "content": prompt})

        logger.info(f"Текстовый запрос к ChatGPT. User: {user}, Model: {model}, tokens: {user[f'tokens_{model_dashed}']}")
        await bot.send_chat_action(user_id, ChatActions.TYPING)
        res = await ai.get_gpt(messages, model)

        # Удаляем "ожидание"
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_wait.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение ожидания: {e}")

        # Форматируем и отправляем ответ (как у тебя было)
        html_content = format_math_in_text(res["content"])
        code_blocks = re.findall(r"(<pre><code>.*?</code></pre>)", html_content, re.DOTALL)
        non_code_content = re.sub(r"<pre><code>.*?</code></pre>", "", html_content, flags=re.DOTALL)
        non_code_content = html.unescape(non_code_content)

        for code in code_blocks:
            code = html.unescape(code)
            if len(code) > 3000:
                parts = split_message(code, 3000, is_code=True)
                for part in parts:
                    part = ensure_code_block_integrity(part)
                    await send_message_with_html(bot, user_id, part, reply_markup=user_kb.get_clear_or_audio())
            else:
                code = ensure_code_block_integrity(code)
                await send_message_with_html(bot, user_id, code, reply_markup=user_kb.get_clear_or_audio())

        if len(non_code_content) <= 3000:
            non_code_content = ensure_code_block_integrity(non_code_content)
            await send_message_with_html(bot, user_id, non_code_content, reply_markup=user_kb.get_clear_or_audio())
        else:
            parts = split_message(non_code_content, 3000)
            for idx, part in enumerate(parts):
                part = ensure_code_block_integrity(part)
                if idx == len(parts) - 1:
                    await send_message_with_html(bot, user_id, part, reply_markup=user_kb.get_clear_or_audio())
                else:
                    await send_message_with_html(bot, user_id, part)

        await state.update_data(content=res["content"])

        if not res["status"]:
            return

        # Обновляем локальный контекст сообщений
        message_gpt = res["content"]
        messages.append({"role": "assistant", "content": message_gpt})

        # Быстро обеспечиваем наличие chat_id без ожидания GPT-имени
        had_chat = bool(current_chat)
        if not had_chat:
            # Временное имя — просто первые 50 символов вопроса пользователя
            provisional_name = re.sub(r"\s+", " ", message_user).strip().strip('"')[:50] or "Новый чат"
            new_chat_id = await db.create_chat(user_id, name=provisional_name, summary="")
            await db.set_current_chat(user_id, new_chat_id)
            chat_id = new_chat_id
        else:
            chat_id = current_chat["id"]

        # Сохраняем реплики синхронно (это быстро)
        await db.add_message(chat_id, user_id, message_user)
        await db.add_message(chat_id, None, message_gpt)

        # Списываем токены/триал и логируем действие — синхронно
        await db.remove_chatgpt(user_id, res["tokens"], model)
        await db.mark_used_trial(user_id)
        await db.add_action(user_id, model)

        # Запускаем тяжёлую пост-обработку в фоне: имя (если чат новый), keywords и summary
        asyncio.create_task(_postprocess_chat(chat_id, user_id, message_user, message_gpt, model, had_chat))

        return messages
    finally:
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_wait.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение ожидания: {e}")

async def _postprocess_chat(chat_id: int, user_id: int, message_user: str, message_gpt: str, model: str, had_chat: bool):
    """
    Фоновая пост-обработка чата:
    - генерирует осмысленное имя для нового чата;
    - извлекает ключевые слова;
    - обновляет краткое summary.
    Выполняется асинхронно в фоне и НЕ блокирует ответы на команды (/start и др.).
    """
    try:
        # Имя для нового чата
        if not had_chat:
            try:
                generated_name = await generate_chat_name(message_user, model, message_gpt)
            except Exception as e:
                logger.warning(f"Не удалось сгенерировать имя чата: {e}")
                # Запасной вариант — обрезанный текст вопроса
                generated_name = (re.sub(r"\s+", " ", message_user).strip().strip('"')[:50] or "Новый чат")
            try:
                conn = await db.get_conn()
                await conn.execute("UPDATE chats SET name = $1, updated_at = NOW() WHERE id = $2",
                                   generated_name, chat_id)
                await conn.close()
            except Exception as e:
                logger.warning(f"Не удалось сохранить имя чата: {e}")

        # Ключевые слова
        try:
            keywords = await extract_keywords_from_message(message_user, chat_id, model)
            await update_chat_keywords(chat_id, keywords)
        except Exception as e:
            logger.warning(f"Не удалось обновить ключевые слова: {e}")

        # Сводка (summary)
        try:
            row = await db.get_chat_by_id(chat_id)
            old_summary = row["summary"] if row else ""
            new_summary = await update_chat_summary(chat_id, message_user, message_gpt, model, old_summary)
            await db.update_chat_summary(chat_id, new_summary)
        except Exception as e:
            logger.warning(f"Не удалось обновить summary: {e}")

    except Exception:
        logger.exception("postprocess failed")


async def update_chat_keywords(chat_id: int, new_keywords: list[str]):
    if not new_keywords:
        return
    conn = await db.get_conn()

    row = await conn.fetchrow("SELECT keywords FROM chats WHERE id = $1", chat_id)
    existing_keywords = row["keywords"] if row and row["keywords"] else []

    # Объединяем списки, удаляем дубли
    combined_keywords = list(set(existing_keywords + new_keywords))[:20]  # максимум 20 слов

    await conn.execute(
        "UPDATE chats SET keywords = $1, updated_at = NOW() WHERE id = $2",
        combined_keywords, chat_id
    )
    await conn.close()

async def extract_keywords_from_message(message: str, chat_id: int, model: str) -> list[str]:
    # Проверка на наличие слова "запомни"
    must_extract = "запомни" in message.lower()

    prompt = (
        f"Пользователь написал сообщение:\n"
        f"{message}\n\n"
    )

    if must_extract:
        prompt += (
            "Так как пользователь просит 'запомни', обязательно выдели до 5 ключевых слов или фраз, "
            "даже если они кажутся незначительными. "
            "Ответ верни строго в формате Python-списка строк, например:\n"
            "['важное', 'запомнить', 'инструкция']\n"
        )
    else:
        prompt += (
            "Выдели до 5 ключевых слов или фраз (если они есть), описывающих суть или важные темы в сообщении. "
            "Если ключевых слов нет — верни пустой список []. Ответ верни строго в формате Python-списка строк."
        )

    response = await ai.get_gpt(
        messages=[
            {"role": "system", "content": "Ты извлекаешь ключевые слова из пользовательских сообщений."},
            {"role": "user", "content": prompt}
        ],
        model=model
    )

    try:
        keywords = eval(response["content"])
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            return keywords
    except Exception:
        pass
    return []


async def update_chat_summary(chat_id: int, message_user: str, message_gpt: str, model: str,
                              old_summary: str = "") -> str:
    summary_prompt = (
        f"Вот краткое описание предыдущей беседы: {old_summary}\n\n"
        f"Добавь к нему краткое описание следующей части диалога:\n"
        f"Пользователь: {message_user}\n"
        f"Ассистент: {message_gpt}\n\n"
        f"Обновлённая краткая сводка (максимум 3000 символов):"
    )

    response = await ai.get_gpt(
        messages=[
            {"role": "system",
             "content": "Ты ассистент, умеющий сжимать диалоги в краткое описание. Пиши коротко и по делу."},
            {"role": "user", "content": summary_prompt}
        ],
        model=model
    )

    return response["content"].strip()

# генерируем имя при помощи GPT
async def generate_chat_name(message_user: str, model: str, message_gpt: str) -> str:
    prompt = (
        f"Пользователь задал вопрос: \"{message_user}\"\n"
        f"Ассистент ответил: \"{message_gpt}\"\n\n"
        f"На основе этого диалога придумай короткое, осмысленное название чата (до 50 символов):"
    )

    response = await ai.get_gpt(
        messages=[
            {"role": "system", "content": "Ты генерируешь короткие и содержательные заголовки диалогов."},
            {"role": "user", "content": prompt}
        ],
        model=model
    )

    return response["content"].strip().strip('"')[:50]


import random

async def generate_example_prompt() -> str:
    """
    Возвращает случайный пример пользовательского запроса к ChatGPT из заранее заданного списка.
    """
    examples = [
        "Напиши короткое поздравление с днём рождения",
        "Объясни простыми словами, как работает нейросеть",
        "Составь план старта онлайн-бизнеса",
        "Придумай идею для арт-проекта",
        "Дай советы по самоорганизации",
        "Напиши интересный пост для Telegram-канала",
        "Придумай креативное описание товара",
        "Расскажи о пользе прогулок на свежем воздухе",
        "Составь список идей для хобби",
        "Объясни, как работает квантовый компьютер",
        "Напиши вдохновляющую цитату",
        "Помоги придумать название для бренда одежды",
        "Дай советы, как улучшить сон",
        "Составь список фильмов на вечер",
        "Придумай тему для короткой статьи",
        "Объясни, как работает искусственный интеллект",
        "Напиши стихотворение про осень",
        "Расскажи интересный факт о космосе",
        "Дай идею для подарка другу",
        "Придумай необычную идею свидания на природе",
    ]

    return random.choice(examples)




''' Новые две функции - уведомления об заканчивающихся токенах '''


# Уведомение о низком количестве токенов GPT
# async def notify_low_chatgpt_tokens(user_id, bot: Bot):
#     logger.info('Внутри скидочного уведомления - выбираем модель')
#
#     await bot.send_message(user_id, """
# У вас заканчиваются запросы для 💬 ChatGPT
# Специально для вас мы подготовили <b>персональную скидку</b>!
# Выберите интересующую Вас модель⤵️
#     """, reply_markup=user_kb.get_chatgpt_models_noback('discount'))


# Уведомление о низком количестве запросов MidJourney
async def notify_low_midjourney_requests(user_id, bot: Bot):
    await bot.send_message(user_id, """
У вас заканчиваются запросы для 🎨 Midjourney
Специально для вас мы подготовили <b>персональную скидку</b>!

Успейте приобрести запросы со скидкой, предложение актуально <b>24 часа</b>⤵️
    """, reply_markup=user_kb.get_midjourney_discount_notification())


# @dp.errors_handler()
# async def log_all_updates(update: Update, exception: Exception = None):
#     logging.debug(f"Update received: {update.to_python()}")
#     if exception:
#         logging.error(f"Exception: {exception}")
#     return True

'''
@dp.callback_query_handler()
async def all_callback_handler(call: CallbackQuery):
    logging.info(f"Received callback_data: {call.data}")
    await call.message.answer("Callback received")
'''


# Хендлер настроек ChatGPT
@dp.callback_query_handler(text="settings")
async def settings(call: CallbackQuery):
    if not await check_access_or_prompt(call):
        return
    user = await db.get_user(call.from_user.id)
    user_lang = user["chat_gpt_lang"]

    await call.message.answer("""Здесь Вы можете изменить настройки 
ChatGPT⤵️""", reply_markup=user_kb.settings(user_lang, 'acc'))
    await call.answer()


# Хендлер для проверки подписки через callback-запрос
from aiogram.types import CallbackQuery, ChatMember
from config import channel_id
from aiogram.utils.exceptions import ChatNotFound
from keyboards.user import partner  # клавиатура с кнопкой «Подписаться»

@dp.callback_query_handler(text="check_sub")
async def check_sub(call: CallbackQuery):
    user_id = call.from_user.id

    try:
        # Проверка подписки через Telegram API
        status: ChatMember = await bot.get_chat_member(channel_id, user_id)
        if status.status == "left":
            await call.message.answer("Для продолжения использования, подпишитесь на наш канал⤵️",
                                      reply_markup=partner)
            await call.answer()
            return  # не показываем меню
    except ChatNotFound:
        await call.message.answer("Канал не найден.")
        await call.answer()
        return
    except Exception:
        await call.message.answer("⚠️ Не удалось проверить подписку. Попробуйте позже.")
        await call.answer()
        return

    # Подписка подтверждена, работаем дальше
    user = await db.get_user(user_id)
    if user is None:
        await db.add_user(user_id, call.from_user.username, call.from_user.first_name, 0)
        user = await db.get_user(user_id)

    # Обновляем статус в БД (если используешь is_subscribed)
    await db.update_is_subscribed(user_id, True)

    # Сообщение с запросом ввода
    example_prompt = await generate_example_prompt()
    await call.message.answer(
        f"""<b>Введите запрос</b>
    Например: <code>{example_prompt}</code>

    <u><a href="https://telegra.ph/Kak-polzovatsya-ChatGPT-podrobnaya-instrukciya-06-04">Подробная инструкция.</a></u>""",
        reply_markup=user_kb.get_menu("chatgpt"),
        disable_web_page_preview=True
    )


# Хендлер для удаления сообщения через callback-запрос
@dp.callback_query_handler(text="delete_msg")
async def delete_msg(call: CallbackQuery, state: FSMContext):
    await call.message.delete()  # Удаляем сообщение


# Хендлер для возврата к главному меню через callback-запрос
@dp.callback_query_handler(text="back_to_menu")
async def back_to_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)  # Получаем данные пользователя

    # Сообщение с запросом ввода
    example_prompt = await generate_example_prompt()
    await call.message.answer(
        f"""<b>Введите запрос</b>
        Например: <code>{example_prompt}</code>

        <u><a href="https://telegra.ph/Kak-polzovatsya-ChatGPT-podrobnaya-instrukciya-06-04">Подробная инструкция.</a></u>""",
        reply_markup=user_kb.get_menu("chatgpt"),
        disable_web_page_preview=True
    )

#     await call.message.answer("""NeuronAgent 🤖 - 2 нейросети в одном месте!
#
# ChatGPT или Midjourney?""", reply_markup=user_kb.get_start_inline())  # Меню выбора AI
    await call.message.delete()  # Удаляем предыдущее сообщение


@dp.message_handler(state="*", text="🤝 Партнерская программа")
@dp.message_handler(commands='partner')
async def ref_menu(message: Message):
    user_id = message.from_user.id
    ref_data = await db.get_ref_stat(user_id)
    user = await db.get_user(user_id)

    all_income = ref_data['all_income'] if ref_data.get('all_income') is not None else 0
    count_refs = int(ref_data.get("count_refs") or 0)
    orders_count = int(ref_data.get("orders_count") or 0)
    available_for_withdrawal = ref_data.get("available_for_withdrawal") or 0

    # ✅ Всего заработано дней доступа к ChatGPT за рефералов (накопительно, не зависит от старых инвайтов)
    total_gpt_days = int((user.get("gpt_referral_days_earned") if user else 0) or 0)

    ref_link = f'{bot_url}?start=r{user_id}'

    # Формируем клавиатуру
    text_url = parse.quote(ref_link)
    share_url = f'https://t.me/share/url?url={text_url}'

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton('📩 Поделится ссылкой', url=share_url),
        # InlineKeyboardButton('💳 Вывод средств', callback_data='withdraw_ref_menu')
    )

    # Добавляем кнопку включения уведомлений, если они отключены
    if user and not user.get("ref_notifications_enabled", True):
        keyboard.add(
            InlineKeyboardButton("🔔 Включить уведомления о рефералах", callback_data="enable_ref_notifications")
        )

    # Добавляем кнопку назад в конце
    keyboard.add(InlineKeyboardButton(' 🔙 Назад', callback_data='check_sub'))

    await message.answer_photo(
        more_api.get_qr_photo(ref_link),
        caption=f'''<b>🤝 Партнёрская программа</b>

<i>Приводи друзей и получай 2 недели ChatGPT бесплатно.</i>

<b>⬇️ Твоя реферальная ссылка:</b>
└ {ref_link}

<b>🏅 Статистика:</b>
├ Лично приглашённых: <b>{count_refs}</b>
├ Всего получено дней для ChatGPT: <b>{total_gpt_days}</b>

Ваша реферальная ссылка: ''',
        reply_markup=keyboard
    )


@dp.message_handler(state="*", text="⚙ Аккаунт")
@dp.message_handler(state="*", commands="account")
async def show_profile(message: Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    user_lang = user['chat_gpt_lang']

    mj = int(user['mj']) + int(user['free_image'])
    mj = mj if mj >= 0 else 0

    access_ok = await check_access_or_prompt(message)
    if not access_ok and mj == 0:
        return

    # ✅ дни доступа к ChatGPT
    from math import ceil
    from datetime import datetime

    def ru_days(n: int) -> str:
        n = abs(int(n))
        n100 = n % 100
        n10 = n % 10
        if 11 <= n100 <= 14:
            return "дней"
        if n10 == 1:
            return "день"
        if 2 <= n10 <= 4:
            return "дня"
        return "дней"

    access_until = user.get("gpt_access_until")
    days_left = 0
    if access_until:
        now = datetime.utcnow()
        delta_sec = (access_until - now).total_seconds()
        if delta_sec > 0:
            days_left = int(ceil(delta_sec / 86400))
    days_word = ru_days(days_left)

    logger.info(f"Аккаунт {user_id}: mj={mj}, gpt_days_left={days_left}")

    sub_text = f"""
Вам доступно⤵️

Генерации 🎨 Midjourney:  {format(mj, ',').replace(',', ' ')}
💬 GPT-5.2:  {days_left} {days_word}
💬 GPT-5-mini:  {days_left} {days_word}
                    """

    await message.answer(
        f"""🆔: <code>{user_id}</code>
{sub_text}""",
        reply_markup=user_kb.get_account(user_lang, "account")
    )


# Хендлер для возврата к профилю пользователя через callback-запрос
@dp.callback_query_handler(Text(startswith="back_to_profile"), state="*")
async def back_to_profile(call: CallbackQuery, state: FSMContext):
    logger.info(f"Back To Profile {call.data}")

    src = call.data.split(":")[1]
    user_id = call.from_user.id
    user = await db.get_user(user_id)  # Получаем данные пользователя

    if src == "acc":
        # Удаляем старое сообщение с текстом и клавиатурой
        await call.message.delete()

        await state.finish()
        user_lang = user['chat_gpt_lang']

        # Формируем текст с количеством доступных генераций и токенов
        mj = int(user['mj']) + int(user['free_image']) if int(user['mj']) + int(user['free_image']) >= 0 else 0
        gpt_5 = max(int(user.get('tokens_5', 0)), 0)
        gpt_5_mini = max(int(user.get('tokens_5_mini', 0)), 0)

        logger.info(
            f"Количество токенов и запросов для {user_id}:mj: {mj}, gpt_5: {gpt_5}, gpt_5_mini: {gpt_5_mini}")

        keyboard = user_kb.get_account(user_lang, "account")

        # ✅ дни доступа к ChatGPT
        from math import ceil
        from datetime import datetime

        access_until = user.get("gpt_access_until")
        days_left = 0
        if access_until:
            now = datetime.utcnow()
            delta_sec = (access_until - now).total_seconds()
            if delta_sec > 0:
                days_left = int(ceil(delta_sec / 86400))

        # Формируем текст с количеством доступных генераций и токенов
        sub_text = f"""
Вам доступно⤵️

Генерации 🎨 Midjourney:  {format(mj, ',').replace(',', ' ')}
💬 GPT-5.2:  {days_left} дней
💬 GPT-5-mini:  {days_left} дней
                    """

        # Отправляем сообщение с обновленными данными аккаунта
        await call.message.answer(f"""🆔: <code>{user_id}</code>
    {sub_text}""", reply_markup=keyboard)

    else:
        await state.finish()

#         if src == "not_gpt":
#             await call.message.edit_text("""
# У вас заканчиваются токены для 💬 ChatGPT
# Специально для вас мы подготовили <b>персональную скидку</b>!
#
# Успейте приобрести токены со скидкой, предложение актуально <b>24 часа</b>⤵️
#             """, reply_markup=user_kb.get_chatgpt_tokens_menu('disount', user["gpt_model"]))

        if src == "not_mj":
            await call.message.edit_text("""
У вас заканчиваются запросы для 🎨 Midjourney
Специально для вас мы подготовили <b>персональную скидку</b>!

Успейте приобрести запросы со скидкой, предложение актуально <b>24 часа</b>⤵️
            """, reply_markup=user_kb.get_midjourney_discount_notification())

    await call.answer()


# Хендлер для смены языка через callback-запрос
@dp.callback_query_handler(Text(startswith="change_lang:"))
async def change_lang(call: CallbackQuery):
    curr_lang = call.data.split(":")[1]  # Текущий язык
    from_msg = call.data.split(":")[2]  # Источник сообщения (откуда был вызван callback)
    new_lang = "en" if curr_lang == "ru" else "ru"  # Смена языка
    await db.change_chat_gpt_lang(call.from_user.id, new_lang)  # Обновляем язык в базе
    lang_text = {"ru": "русский", "en": "английский"}
    await call.answer(f"Язык изменён на {lang_text[new_lang]}")
    if from_msg == "acc":
        kb = user_kb.settings(new_lang, from_msg)  # Меню ChatGPT
    else:
        kb = user_kb.get_account(new_lang, from_msg)  # Меню аккаунта
    await call.message.edit_reply_markup(reply_markup=kb)  # Обновляем клавиатуру


# Главное меню для генерации изображений от OpenAI
@dp.message_handler(state="*", text="🎨 Image OpenAI ✅")
@dp.message_handler(state="*", text="🎨 Image OpenAI")
@dp.message_handler(state="*", commands="image_openai")
async def image_openai_menu_handler(message: Message, state: FSMContext):
    if not await check_access_or_prompt(message):
        return
    if state:
        await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "image_openai")  # Устанавливаем ChatGPT как основной AI
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} вызвал Главное меню для генерации изображений от OpenAI")
    await gen_image_openai(message)

# Хендлер для ChatGPT
@dp.message_handler(state="*", text="💬 ChatGPT ✅")
@dp.message_handler(state="*", text="💬 ChatGPT")
@dp.message_handler(state="*", commands="chatgpt")
async def ask_question(message: Message, state: FSMContext):
    if not await check_access_or_prompt(message):
        return
    if state:
        await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "chatgpt")  # Устанавливаем ChatGPT как основной AI
    await message.answer("Режим: ChatGPT", reply_markup=user_kb.get_menu("chatgpt"))

    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if user is None:
        await db.add_user(user_id, message.from_user.username, message.from_user.first_name, 0)
        try:
            await db.set_model(user_id, "5")
        except Exception:
            pass
        await db.change_default_ai(user_id, "chatgpt")
        user = await db.get_user(user_id)

    # безопасно получаем модель
    model = (user.get("gpt_model") or "5").replace("-", "_")

    # безопасно проверяем токены
    tokens_left = int(user.get(f"tokens_{model}", 0) or 0)
    if tokens_left <= 0:
        return await not_enough_balance(message.bot, user_id, "chatgpt")

    # Получаем текущий активный чат
    current_chat = await db.get_chat_by_id(user["current_chat_id"])

    # если этот чат неактивен > 24ч — закрываем и просим ввести новый запрос
    if await close_inactive_chat_and_prompt(message, with_mode_banner=False):
        return

    # Отправляем пользователю имя текущего чата (если есть)
    if current_chat and current_chat["name"]:
        keyboard = InlineKeyboardMarkup(row_width=1).add(
            InlineKeyboardButton("🗂 Мои чаты", callback_data="my_chats"),
            InlineKeyboardButton("➕ Новый чат", callback_data="create_new_chat"),
        )
        await message.answer(
            f" 💬 Активный чат: *{current_chat['name']}*\n\n"
            f"Выберите чат или введите запрос⤵️",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        # Сообщение с запросом ввода
        example_prompt = await generate_example_prompt()
        await message.answer(
            f"""<b>Введите запрос</b>
Например: <code>{example_prompt}</code>

Или настройте ChatGPT под свои задачи по кнопке ⤵️

<u><a href="https://telegra.ph/Kak-polzovatsya-ChatGPT-podrobnaya-instrukciya-06-04">Подробная инструкция.</a></u>""",
            reply_markup=InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("⚙️ Настройки ChatGPT", callback_data="settings")
            ),
            disable_web_page_preview=True
        )


@dp.callback_query_handler(text="create_new_chat", state="*")
async def handle_create_new_chat(call: CallbackQuery, state: FSMContext):
    await state.finish()
    user_id = call.from_user.id

    # Удаляем активный чат
    await db.set_current_chat(user_id, None)

    # Сообщение с предложением ввести первый запрос
    example_prompt = await generate_example_prompt()
    await call.message.edit_text(
        f"<b>Введите запрос для нового чата⤵️</b>\n"
        f"Например: <code>{example_prompt}</code>",
        parse_mode="HTML"
    )


# Хендлер для вывода информации о поддержке
@dp.message_handler(state="*", text="👨🏻‍💻 Поддержка")
@dp.message_handler(state="*", commands="help")
async def support(message: Message, state: FSMContext):
    await state.finish()  # Завершаем текущее состояние
    await message.answer('Ответы на многие вопросы можно найти в нашем <a href="https://t.me/NeuronAgent">канале</a>.',
                         disable_web_page_preview=True, reply_markup=user_kb.about)  # Кнопка с инструкцией


# Хендлер для MidJourney
@dp.message_handler(state="*", text="🎨 Midjourney ✅")
@dp.message_handler(state="*", text="🎨 Midjourney")
@dp.message_handler(state="*", commands="midjourney")
async def gen_img(message: Message, state: FSMContext):
    # if not await check_access_or_prompt(message):
    #     return
    # user_id = message.from_user.id
    await state.finish()  # Завершаем текущее состояние
    await db.change_default_ai(message.from_user.id, "image")  # Устанавливаем MidJourney как основной AI
    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя
    # Проверяем наличие токенов и подписки
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(message.bot, message.from_user.id, "image")  # Сообщаем об исчерпании лимита
        return

    # Сообщение с запросом ввода
    await message.answer("""<b>Введите запрос для генерации изображения</b>
<i>Например:</i> <code>Замерзшее бирюзовое озеро вокруг заснеженных горных вершин</code>

<u><a href="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16">Подробная инструкция.</a></u>""",
                         reply_markup=user_kb.get_menu("image"),
                         disable_web_page_preview=True)


# Хендлер для выбора суммы через callback-запрос
@dp.callback_query_handler(Text(startswith="select_amount"))
async def select_amount(call: CallbackQuery):
    amount = int(call.data.split(":")[1])  # Получаем сумму из callback
    # Генерация ссылок для пополнения
    urls = {
        "tinkoff": pay.get_pay_url_tinkoff(call.from_user.id, amount),
        "freekassa": pay.get_pay_url_freekassa(call.from_user.id, amount),
        "payok": pay.get_pay_url_payok(call.from_user.id, amount),
    }
    await call.message.answer(f"""💰 Сумма: <b>{amount} рублей

♻️ Средства зачислятся автоматически</b>""", reply_markup=user_kb.get_pay_urls(urls))  # Кнопки с ссылками на оплату
    await call.answer()


# Хендлер для отмены текущего состояния
@dp.message_handler(state="*", text="Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.finish()  # Завершаем текущее состояние
    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя
    await message.answer("Ввод остановлен", reply_markup=user_kb.get_menu(user["default_ai"]))  # Возвращаем меню


# Хендлер для выбора изображения через callback
@dp.callback_query_handler(Text(startswith="choose_image:"))
async def choose_image(call: CallbackQuery):
    await call.answer()  # Закрываем callback уведомление
    user = await db.get_user(call.from_user.id)

    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(call.bot, call.from_user.id, "image")  # Проверка наличия баланса для MidJourney
        return
    action_id = call.data.split(":")[1]
    image_id = call.data.split(":")[2]
    task_id = (await db.get_task_by_action_id(int(action_id)))["external_task_id"]
    await call.message.answer("Ожидайте, сохраняю изображение в отличном качестве… ⏳ ",
                              reply_markup=user_kb.get_menu(user["default_ai"]))
    res = await ai.get_choose_mdjrny(task_id, image_id, call.from_user.id)  # Запрос к MidJourney API

    if res is not None and "success" not in res:
        if "message" in res and res["message"] == "repeat task":
            return await call.message.answer(
                "Вы уже сохраняли это изображение!")  # Сообщение, если изображение уже сохранялось


# Хендлер для изменения изображения через callback
@dp.callback_query_handler(Text(startswith="change_image:"))
async def change_image(call: CallbackQuery):
    await call.answer()  # Закрываем callback уведомление
    user_id = call.from_user.id
    user_notified = await db.get_user_notified_mj(user_id)

    user = await db.get_user(user_id)
    if user["mj"] <= 0 and user["free_image"] <= 0:
        await not_enough_balance(call.bot, user_id, "image")  # Проверка лимитов
        return
    action = call.data.split(":")[3]
    button_type = call.data.split(":")[1]
    value = call.data.split(":")[2]
    task_id = (await db.get_task_by_action_id(int(action)))["external_task_id"]
    await call.message.answer("Ожидайте, обрабатываю изображение ⏳ ",
                              reply_markup=user_kb.get_menu(user["default_ai"]))

    action_id = await db.add_action(user_id, "image", button_type)

    if 1 < user["mj"] <= 3:  # Если осталось 3 или меньше запросов
        now = datetime.now()

        if user_notified is None:
            await db.create_user_notification_mj(user_id)
            await notify_low_midjourney_requests(user_id,
                                                 call.bot)  # Отправляем уведомление о низком количестве токенов
            # await db.set_user_notified(user_id)  # Помечаем, что уведомление отправлено
        else:
            last_notification = user_notified['last_notification']
            if last_notification is None or now > last_notification + timedelta(days=30):
                await db.update_user_notification_mj(user_id)
                await notify_low_midjourney_requests(user_id, call.bot)

    if button_type == "zoom":
        response = await mj_api.outpaint(task_id, value, action_id)  # Масштабирование изображения через API
    elif button_type == "vary":
        response = await mj_api.variation(task_id, value, action_id)  # Вариация изображения через API


# Хендлер для очистки контента через callback
@dp.callback_query_handler(text="clear_content")
async def clear_content(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    await state.finish()  # Завершаем текущее состояние
    await call.message.answer("Диалог завершен",
                              reply_markup=user_kb.get_menu(user["default_ai"]))  # Сообщение о завершении диалога
    try:
        await call.answer()  # Закрываем callback уведомление
    except:
        pass


# Хендлер для повторного ввода запроса через callback
@dp.callback_query_handler(Text(startswith="try_prompt"))
async def try_prompt(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if "prompt" not in data:
        await call.message.answer("Попробуйте заново ввести запрос")
        return await call.answer()  # Закрываем callback уведомление
        await state.finish()
    await call.answer()

    user = await db.get_user(call.from_user.id)
    if user["default_ai"] == "image":
        await get_mj(data['prompt'], call.from_user.id, call.bot)  # Генерация изображения


# Хендлер для настроек ChatGPT: ввод данных о пользователе через callback
@dp.callback_query_handler(text="chatgpt_about_me", state="*")
async def chatgpt_about_me(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

    await call.message.answer(
        '<b>Введите запрос</b>\n\nПоделитесь с ChatGPT любой информацией о себе, чтобы получить более качественные ответы⤵️\n\n<u><a href="https://telegra.ph/Tonkaya-nastrojka-ChatGPT-06-30">Инструкция.</a></u>',
        disable_web_page_preview=True,
        reply_markup=user_kb.clear_description())
    await state.set_state(states.ChangeChatGPTAboutMe.text)  # Устанавливаем состояние ввода данных
    await call.answer()


# Хендлер для сохранения введенной информации о пользователе в ChatGPT
@dp.message_handler(state=states.ChangeChatGPTAboutMe.text)
async def change_profile_info(message: Message, state: FSMContext):
    if len(message.text) > 256:
        return await message.answer("Максимальная длина 256 символов")
    await db.update_chatgpt_about_me(message.from_user.id, message.text)  # Обновляем данные в базе
    await message.answer("✅ Описание обновлено!")
    await state.finish()


# Показать список характеров
@dp.callback_query_handler(text="character_menu", state="*")
async def character_menu(call: CallbackQuery, state: FSMContext):
    await state.finish()
    characters = await db.get_characters(call.from_user.id)
    active = await db.get_active_character(call.from_user.id)
    active_id = active["id"] if active else None

    text = "<b>🎭 Характер ChatGPT</b>\n\nНастройте ChatGPT как Вам удобно — тон, настроение, эмоциональный окрас сообщений.\n\n"
    if not characters:
        text += "У вас ещё нет характеров. Создайте первый!"
    else:
        active_name = active["name"] if active else "не выбран"
        text += f"Активный: <b>{active_name}</b>"

    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=user_kb.character_list_keyboard(characters, active_id))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=user_kb.character_list_keyboard(characters, active_id))
    await call.answer()


# Создание нового характера — запрос названия
@dp.callback_query_handler(text="new_character", state="*")
async def new_character(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "Введите название характера:",
        reply_markup=user_kb.edit_character_instructions_keyboard()
    )
    await states.CreateCharacter.name.set()
    await call.answer()


# Получаем название нового характера
@dp.message_handler(state=states.CreateCharacter.name)
async def create_character_name(message: Message, state: FSMContext):
    if len(message.text) > 64:
        return await message.answer("Максимальная длина названия — 64 символа")
    await state.update_data(name=message.text)
    await message.answer(
        "Укажите инструкции для характера:",
        reply_markup=user_kb.edit_character_instructions_keyboard()
    )
    await states.CreateCharacter.instructions.set()


# Получаем инструкции и создаём характер
@dp.message_handler(state=states.CreateCharacter.instructions)
async def create_character_instructions(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    char_id = await db.create_character(message.from_user.id, name, message.text)
    await db.set_active_character(message.from_user.id, char_id)
    await state.finish()
    await message.answer(
        f"<b>{html.escape(name)}</b> успешно создан",
        parse_mode="HTML"
    )


# Настройки конкретного характера
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("character_settings:"), state="*")
async def character_settings(call: CallbackQuery, state: FSMContext):
    await state.finish()
    char_id = int(call.data.split(":")[1])
    char = await db.get_character(char_id)
    if not char:
        await call.answer("Характер не найден", show_alert=True)
        return
    active = await db.get_active_character(call.from_user.id)
    text = f"<b>Настройки для {html.escape(char['name'])}</b>\n\n<i>{html.escape(char['instructions'])}</i>"
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=user_kb.character_settings_keyboard(char_id))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=user_kb.character_settings_keyboard(char_id))
    await call.answer()


# Выбрать характер как активный
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("select_character:"), state="*")
async def select_character(call: CallbackQuery, state: FSMContext):
    char_id = int(call.data.split(":")[1])
    char = await db.get_character(char_id)
    if not char:
        await call.answer("Характер не найден", show_alert=True)
        return
    await db.set_active_character(call.from_user.id, char_id)
    text = f"<b>Настройки для {html.escape(char['name'])}</b>\n\n<i>{html.escape(char['instructions'])}</i>"
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=user_kb.character_settings_keyboard(char_id))
    except Exception:
        pass
    # Обычное сообщение по схеме
    await call.message.answer(
        f"<b>{html.escape(char['name'])}</b> успешно загружен\n\nВведите запрос⤵️",
        parse_mode="HTML"
    )
    await call.answer()


# Редактировать характер — запрос нового названия
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("edit_character:"), state="*")
async def edit_character(call: CallbackQuery, state: FSMContext):
    char_id = int(call.data.split(":")[1])
    await state.update_data(char_id=char_id)
    await call.message.edit_text(
        "Введите новое название:",
        reply_markup=user_kb.edit_character_name_keyboard()
    )
    await states.EditCharacter.name.set()
    await call.answer()


# Пропустить переименование — оставить старое название
@dp.callback_query_handler(text="skip_character_name", state=states.EditCharacter.name)
async def skip_character_name(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "Укажите инструкции для характера:",
        reply_markup=user_kb.edit_character_instructions_keyboard()
    )
    await states.EditCharacter.instructions.set()
    await call.answer()


# Пропустить смену инструкций — оставить старые
@dp.callback_query_handler(text="skip_character_instructions", state=states.EditCharacter.instructions)
async def skip_character_instructions(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    char_id = data["char_id"]
    char = await db.get_character(char_id)
    if not char:
        await state.finish()
        await call.answer("Характер не найден", show_alert=True)
        return
    name_changed = "new_name" in data
    new_name = data["new_name"] if name_changed else char["name"]
    if name_changed:
        await db.update_character(char_id, new_name, char["instructions"])
    await state.finish()
    await call.answer()
    if name_changed:
        await call.message.answer(
            f"Характер переименован в <b>{html.escape(new_name)}</b>\n\nВведите запрос⤵️",
            parse_mode="HTML"
        )
    else:
        await call.message.answer("Инструкции не изменены")


# Получаем новое название
@dp.message_handler(state=states.EditCharacter.name)
async def edit_character_name(message: Message, state: FSMContext):
    if len(message.text) > 64:
        return await message.answer("Максимальная длина названия — 64 символа")
    await state.update_data(new_name=message.text)
    await message.answer(
        "Укажите инструкции для характера:",
        reply_markup=user_kb.edit_character_instructions_keyboard()
    )
    await states.EditCharacter.instructions.set()


# Получаем новые инструкции и сохраняем
@dp.message_handler(state=states.EditCharacter.instructions)
async def edit_character_instructions(message: Message, state: FSMContext):
    data = await state.get_data()
    char_id = data["char_id"]
    char = await db.get_character(char_id)
    if not char:
        await state.finish()
        return await message.answer("Характер не найден")
    name_changed = "new_name" in data
    new_name = data["new_name"] if name_changed else char["name"]
    await db.update_character(char_id, new_name, message.text)
    await state.finish()
    if name_changed:
        await message.answer(
            f"Характер переименован в <b>{html.escape(new_name)}</b>\n\nВведите запрос⤵️",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"Инструкции для <b>{html.escape(new_name)}</b> успешно изменены",
            parse_mode="HTML"
        )


# Удалить характер — показать подтверждение
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("delete_character:"), state="*")
async def delete_character(call: CallbackQuery, state: FSMContext):
    char_id = int(call.data.split(":")[1])
    char = await db.get_character(char_id)
    if not char:
        await call.answer("Характер не найден", show_alert=True)
        return
    try:
        await call.message.edit_text(
            f"Вы действительно хотите удалить характер <b>{html.escape(char['name'])}</b>?",
            parse_mode="HTML",
            reply_markup=user_kb.confirm_delete_character_keyboard(char_id)
        )
    except Exception:
        await call.message.answer(
            f"Вы действительно хотите удалить характер <b>{html.escape(char['name'])}</b>?",
            parse_mode="HTML",
            reply_markup=user_kb.confirm_delete_character_keyboard(char_id)
        )
    await call.answer()


# Подтвердить удаление
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_delete_character:"), state="*")
async def confirm_delete_character(call: CallbackQuery, state: FSMContext):
    char_id = int(call.data.split(":")[1])
    char = await db.get_character(char_id)
    name = char["name"] if char else "характер"
    active = await db.get_active_character(call.from_user.id)
    if active and active["id"] == char_id:
        await db.set_active_character(call.from_user.id, None)
    await db.delete_character(char_id)
    await call.answer()
    await call.message.answer(
        f"<b>{html.escape(name)}</b> успешно удален",
        parse_mode="HTML"
    )


# Удалить все характеры
@dp.callback_query_handler(text="delete_all_characters", state="*")
async def delete_all_characters(call: CallbackQuery, state: FSMContext):
    await db.set_active_character(call.from_user.id, None)
    await db.delete_all_characters(call.from_user.id)
    await call.answer("🗑 Все характеры удалены", show_alert=False)
    text = "<b>🎭 Характер ChatGPT</b>\n\nУ вас ещё нет характеров. Создайте первый!"
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=user_kb.character_list_keyboard([]))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=user_kb.character_list_keyboard([]))


# Хендлер для сброса настроек ChatGPT
@dp.callback_query_handler(text="reset_chatgpt_settings", state="*")
async def reset_chatgpt_settings(call: CallbackQuery, state: FSMContext):
    await db.update_chatgpt_character(call.from_user.id, "")
    await db.update_chatgpt_about_me(call.from_user.id, "")  # Сброс данных
    await call.answer("Описание удалено", show_alert=True)


# Хендлер для изменения настроек ChatGPT
@dp.callback_query_handler(text="chatgpt_settings", state="*")
async def chatgpt_setting(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    await call.message.answer(
        '<b>Введите запрос</b>\n\nНастройте ChatGPT как вам удобно - тон, настроение, эмоциональный окрас сообщений ⤵️\n\n<u><a href="https://telegra.ph/Tonkaya-nastrojka-ChatGPT-06-30">Инструкция.</a></u>',
        disable_web_page_preview=True,
        reply_markup=user_kb.get_menu(user["default_ai"]))
    await state.set_state(states.ChangeChatGPTSettings.text)  # Устанавливаем состояние ввода настроек
    await call.answer()


# Хендлер для сохранения новых настроек ChatGPT
@dp.message_handler(state=states.ChangeChatGPTSettings.text)
async def change_profile_settings(message: Message, state: FSMContext):
    if len(message.text) > 256:
        return await message.answer("Максимальная длина 256 символов")
    await db.update_chatgpt_settings(message.from_user.id, message.text)  # Обновляем настройки в базе
    await message.answer("Описание обновлено!")
    await state.finish()


# Основной хендлер для обработки сообщений и генерации запросов
@dp.message_handler(content_types=['text'], regexp=r'^(?!/).+')
async def gen_prompt(message: Message, state: FSMContext):
    if not await check_access_or_prompt(message):
        return

    user = await db.get_user(message.from_user.id)

    # если чат неактивен > 24ч, очищаем его и переключаемся на ChatGPT
    # with_mode_banner=True, если пользователь был НЕ в ChatGPT (например, в Midjourney)
    with_mode_banner = (user and user.get("default_ai") != "chatgpt")
    if await close_inactive_chat_and_prompt(message, with_mode_banner=with_mode_banner):
        return

    await state.update_data(prompt=message.text)  # Сохраняем запрос пользователя
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if user is None:
        await message.answer("Введите команду /start для перезагрузки бота")
        # return await message.bot.send_message(ADMINS_CODER, user_id)
    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace("-", "_")

        logger.info(f'Текстовый запрос к GPT. User: {user}, Model: {model}, tokens: {user[f"tokens_{model}"]}')

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, user_id, "chatgpt")

        data = await state.get_data()
        active_char = await db.get_active_character(user_id)
        char_instructions = active_char["instructions"] if active_char else ""
        system_msg = user["chatgpt_about_me"] + "\n" + char_instructions
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt=message.text, messages=messages, user_id=user_id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        update_messages = update_messages[-10:]  # хранить только последние 10 сообщений
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(message.text, user_id, message.bot)  # Генерация изображения через MidJourney
    elif user["default_ai"] == "image_openai":
        await gen_image_openai(message)


# Хэндлер для работы с голосовыми сообщениями
@dp.message_handler(content_types=['voice'])
async def handle_voice(message: Message, state: FSMContext):
    file_info = await message.bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    file = await message.bot.download_file(file_path)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_ogg_file:
        temp_ogg_file.write(file.getbuffer())
        temp_ogg_path = temp_ogg_file.name

    text = voice_to_text(temp_ogg_path)
    os.remove(temp_ogg_path)
    await state.update_data(prompt=text)  # Сохраняем запрос пользователя

    user = await db.get_user(message.from_user.id)

    if user is None:
        await message.answer("Введите команду /start для перезагрузки бота")

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace("-", "_")

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, message.from_user.id, "chatgpt")

        data = await state.get_data()
        active_char = await db.get_active_character(message.from_user.id)
        char_instructions = active_char["instructions"] if active_char else ""
        system_msg = user["chatgpt_about_me"] + "\n" + char_instructions
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt=text, messages=messages, user_id=message.from_user.id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(text, message.from_user.id, message.bot)  # Генерация изображения через MidJourney\
    elif user["default_ai"] == "image_openai":
        await gen_image_openai(message)


# Перевод текста в Аудио
@dp.callback_query_handler(text="text_to_audio")
async def return_voice(call: CallbackQuery, state: FSMContext):
    if not await check_access_or_prompt(call):
        return
    processing_message = await call.message.answer("⏳ Идёт запись голосового, ожидайте")
    user_id = call.from_user.id

    # Пытаемся получить текущий голос пользователя
    try:
        user_voice = await db.get_voice(user_id)
        if not user_voice:  # Если результат пустой
            raise ValueError("User voice not found")
    except (ValueError, Exception):  # Если строки нет или другая ошибка
        user_voice = await db.create_voice(user_id)  # Создаем запись

    # Получаем данные из состояния
    content_raw = await state.get_data()

    content = content_raw.get("content")
    if not content:
        await call.message.answer("Нет текста для озвучивания.")
        return

    # Генерация аудио из текста
    audio_response = text_to_speech(content, voice=user_voice)
    # Удаляем сообщение "⏳ Идёт запись голосового, ожидайте"
    await processing_message.delete()
    # Отправляем голосовое сообщение
    await call.message.answer_voice(voice=audio_response)

    # Закрываем callback уведомление
    try:
        await call.answer()
    except Exception as e:
        logger.error(f"Ошибка при закрытии callback уведомления: {e}")


# Хендлер для обработки фотографий
@dp.message_handler(is_media_group=False, content_types="photo")
async def photo_imagine(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.caption is None:
        await message.answer("Добавьте описание к фотографии")
        return
    file = await message.photo[-1].get_file()
    photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
    ds_photo_url = await more_api.upload_photo_to_host(photo_url)  # Загрузка фото на внешний хостинг
    if ds_photo_url == "error":
        await message.answer("Генерация с фото недоступна, повторите попытку позже")
        await message.bot.send_message(bug_id, "Необходимо заменить API-ключ фотохостинга")
        return
    prompt = ds_photo_url + " " + message.caption  # Создаем запрос на основе фотографии и описания
    await state.update_data(prompt=prompt)

    user = await db.get_user(user_id)

    if user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace('-', '_')

        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, message.from_user.id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_settings"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]
        update_messages = await get_gpt(prompt, messages=messages, user_id=message.from_user.id,
                                        bot=message.bot, state=state)  # Генерация ответа от ChatGPT
        await state.update_data(messages=update_messages)

    elif user["default_ai"] == "image":
        await get_mj(prompt, message.from_user.id, message.bot)
    elif user["default_ai"] == "image_openai":
        await gen_image_openai(message)


# Хендлер для обработки альбомов (групповых фото)
@dp.message_handler(is_media_group=True, content_types=ContentType.ANY)
async def handle_albums(message: Message, album: List[Message], state: FSMContext):
    # Собираем все фото из альбома
    photos = [m for m in album if m.photo]
    if len(photos) < 2:
        return await message.answer("Пришлите как минимум 2 фото одним альбомом")

    # (у альбома подпись чаще всего в первом элементе, но на всякий случай ищем по всем)
    caption = ""
    for m in album:
        if (m.caption or "").strip():
            caption = m.caption.strip()
            break
    if not caption:
        await message.answer("Добавьте описание к фотографии")
        return

    # Грузим ВСЕ фото на внешний хостинг
    ds_urls = []
    for m in photos:
        file = await m.photo[-1].get_file()
        url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        ds_url = await more_api.upload_photo_to_host(url)
        if ds_url == "error":
            await message.answer("Генерация с фото недоступна, повторите попытку позже")
            await message.bot.send_message(bug_id, "Необходимо заменить API-ключ фотохостинга")
            return
        ds_urls.append(ds_url)

    # Промпт: все ссылки + подпись
    prompt = (" ".join(ds_urls) + " " + caption).strip()
    await state.update_data(prompt=prompt)

    user = await db.get_user(message.from_user.id)

    # ✅ Если выбран ChatGPT — анализируем изображения через ChatGPT и НЕ вызываем Midjourney
    if user and user["default_ai"] == "chatgpt":
        model = (user["gpt_model"]).replace('-', '_')
        if user[f"tokens_{model}"] <= 0:
            return await not_enough_balance(message.bot, message.from_user.id, "chatgpt")

        data = await state.get_data()
        system_msg = user["chatgpt_about_me"] + "\n" + user["chatgpt_settings"]
        messages = [{"role": "system", "content": system_msg}] if "messages" not in data else data["messages"]

        update_messages = await get_gpt(
            prompt,
            messages=messages,
            user_id=message.from_user.id,
            bot=message.bot,
            state=state
        )
        await state.update_data(messages=update_messages)
        return  # В ChatGPT-режиме Midjourney не трогаем

    # 🎨 Иначе — режимы изображений (Midjourney и т.п.)
    await get_mj(prompt, message.from_user.id, message.bot)



# Вход в меню выбора модели GPT
@dp.callback_query_handler(text="model_menu")
async def model_menu(call: CallbackQuery):
    user_id = call.from_user.id
    user_model = await db.get_model(user_id)

    logger.info(f"User ID: {user_id}, текущая модель: {user_model}")

    # Динамическое создание клавиатуры с выбранным моделью
    keyboard = user_kb.model_keyboard(selected_model=user_model)

    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

    await call.message.answer("Выберите модель GPT для диалогов⤵️:", reply_markup=keyboard)
    await call.answer()


# Выбор модели GPT
@dp.callback_query_handler(text_contains="select_model")
async def select_model(call: CallbackQuery):
    user_id = call.from_user.id
    selected_model = call.data.split(":")[1]  # Извлечение выбранной модели из данных

    logger.info(f"User ID: {user_id}, выбранная модель: {selected_model}")
    selected_model_bd = selected_model

    try:
        # Записываем выбранную модель в базу данных
        await db.set_model(user_id, selected_model_bd)

        # Получаем обновленную клавиатуру с выбранной моделью
        keyboard = user_kb.model_keyboard(selected_model=selected_model)

        await call.message.edit_text("Выберите модель GPT для диалогов⤵️:", reply_markup=keyboard)

        if selected_model == '5':
            await call.message.answer(f"✅ Модель для ChatGPT изменена на GPT-5.2")
        else:
            await call.message.answer(f"✅ Модель для ChatGPT изменена на GPT-5-mini")
    except Exception as e:
        logger.error(f"Ошибка при выборе модели GPT: {e}")
        await call.answer()


# Вход в меню выбора голоса
@dp.callback_query_handler(text="voice_menu")
async def voice_menu(call: CallbackQuery):
    user_id = call.from_user.id
    user_voice = await db.get_voice(user_id)

    # Удаляем старое сообщение с текстом и клавиатурой
    await call.message.delete()

    # Динамическое создание клавиатуры с выбранным голосом
    keyboard = user_kb.voice_keyboard(selected_voice=user_voice)

    await call.message.answer("Выберите голос для ChatGPT⤵️:", reply_markup=keyboard)
    await call.answer()


# Выбор голоса
@dp.callback_query_handler(text_contains="select_voice")
async def select_voice(call: CallbackQuery):
    user_id = call.from_user.id
    selected_voice = call.data.split(":")[1]  # Извлечение выбранного голоса из данных

    try:
        # Записываем выбранный голос в базу данных
        await db.set_voice(user_id, selected_voice)

        # Получаем обновлённую клавиатуру с выбранным голосом
        updated_keyboard = user_kb.voice_keyboard(selected_voice=selected_voice)

        # Редактируем текущее сообщение с новой клавиатурой
        await call.message.edit_reply_markup(reply_markup=updated_keyboard)

        # Отправляем уведомление об успешном выборе
        await call.answer(f"Выбран голос: {selected_voice} ✅ ")
    except Exception as e:
        logger.error(f"Ошибка при выборе голоса: {e}")
        await call.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)


# Хэндлер для отправки всех голосов
@dp.callback_query_handler(text="check_voice")
async def check_voice(call: CallbackQuery):
    user_id = call.from_user.id
    user_lang = await db.get_chat_gpt_lang(user_id)

    # Путь к папке с файлами
    if user_lang == "ru":
        voices_path = "voices_ru"
    elif user_lang == "en":
        voices_path = "voices_en"

    # Проверяем, что папка существует
    if not os.path.exists(voices_path):
        await call.message.answer("⚠️ Папка с голосами не найдена.")
        return

    # Получаем список файлов .mp3
    voice_files = [f for f in os.listdir(voices_path) if f.endswith(".mp3")]

    # Если файлов нет, отправляем сообщение
    if not voice_files:
        await call.message.answer("⚠️ В папке 'voices' нет доступных файлов.")
        return

    # Создаем медиа-группу
    media_group = MediaGroup()
    for voice_file in voice_files:
        file_path = os.path.join(voices_path, voice_file)
        audio = InputFile(file_path)
        media_group.attach_audio(audio)

    # Отправляем файлы одним сообщением
    await call.message.answer(f"Ответы ChatGPT:{'RUS' if user_lang == 'ru' else 'ENG'}")
    await call.message.answer_media_group(media_group)
    await call.answer()


@dp.callback_query_handler(text="my_chats")
async def show_my_chats(call: CallbackQuery, page: int = 0):
    """
    Обработчик команды "my_chats", который отображает список чатов пользователя
    с пагинацией и предоставляет возможность управления чатами.

    :param call: Объект CallbackQuery, содержащий данные вызова.
    :param page: Номер страницы для отображения чатов.
    """
    if not await check_access_or_prompt(call):
        return
    user_id = call.from_user.id

    # Получаем данные пользователя
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Конфигурация пагинации
    chats_per_page = 4  # Количество чатов на одной странице
    offset = page * chats_per_page

    # Получаем список чатов пользователя с учетом пагинации
    conn = await db.get_conn()
    chats = await conn.fetch(
        "SELECT id, name FROM chats WHERE user_id = $1 ORDER BY created_at LIMIT $2 OFFSET $3",
        user["user_id"], chats_per_page, offset
    )
    await conn.close()

    current_chat_id = user["current_chat_id"]

    # Формируем текст сообщения
    text = (
        "🗂 *Меню чатов позволяет:*\n"
        "- Создавать новые чаты\n"
        "- Переключаться между чатами\n"
        "- Изменять настройки и названия чатов\n\n"
        "*Выберите необходимый чат ⤵️*"
    )

    # Формируем клавиатуру с кнопками
    kb = InlineKeyboardMarkup(row_width=2)

    # Кнопки: удалить все и создать новый
    kb.add(
        InlineKeyboardButton("❌ Удалить все чаты", callback_data="delete_all_chats"),
        InlineKeyboardButton("➕ Новый чат", callback_data="create_chat")
    )

    # Кнопки чатов
    for chat in chats:
        chat_name = chat["name"]
        chat_id = chat["id"]
        # Отметка активного чата
        if chat_id == current_chat_id:
            chat_button_text = f"✅ {chat_name}"
        else:
            chat_button_text = chat_name
        kb.add(InlineKeyboardButton(chat_button_text, callback_data=f"select_chat:{chat_id}"))

    # Пагинация
    kb.row(
        InlineKeyboardButton(" ⏮ ", callback_data=f"page:first:{page}"),
        InlineKeyboardButton(" ◀ ", callback_data=f"page:prev:{page}"),
        InlineKeyboardButton(" ▶ ", callback_data=f"page:next:{page}"),
        InlineKeyboardButton(" ⏭ ", callback_data=f"page:last:{page}")
    )

    # Назад
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="settings"))

    # Отправляем обновленное сообщение с чатиками и кнопками
    await call.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('page:'))
async def paginate_chats(call: CallbackQuery):
    """
    Обработчик пагинации чатов. Позволяет пользователю переходить между страницами
    списка чатов (первая, предыдущая, следующая, последняя).

    :param call: Объект CallbackQuery, содержащий данные вызова.
    """
    # Получаем данные из callback_data
    page_data = call.data.split(":")
    action = page_data[1]  # first, prev, next, last
    current_page = int(page_data[2])  # Текущая страница

    # Получаем данные пользователя
    user_id = call.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем количество чатов пользователя
    conn = await db.get_conn()
    total_chats = await conn.fetchval(
        "SELECT COUNT(*) FROM chats WHERE user_id = $1", user_id
    )
    await conn.close()

    # Количество чатов на одной странице
    chats_per_page = 4
    total_pages = (total_chats // chats_per_page) + (1 if total_chats % chats_per_page > 0 else 0) - 1

    # Определяем номер новой страницы
    if action == 'first':
        new_page = 0
    elif action == 'prev' and current_page > 0:
        new_page = current_page - 1
    elif action == 'next' and current_page < total_pages:
        new_page = current_page + 1
    elif action == 'last':
        new_page = total_pages
    else:
        new_page = current_page  # если страниц нет, остаёмся на текущей

    # Получаем чаты для новой страницы
    offset = new_page * chats_per_page
    conn = await db.get_conn()
    chats = await conn.fetch(
        "SELECT id, name FROM chats WHERE user_id = $1 ORDER BY created_at LIMIT $2 OFFSET $3",
        user_id, chats_per_page, offset
    )
    await conn.close()

    current_chat_id = user["current_chat_id"]

    # Формируем текст для обновленного списка чатов
    text = (
        "🗂 *Меню чатов позволяет:*\n"
        "- Создавать новые чаты\n"
        "- Переключаться между чатами\n"
        "- Изменять настройки и названия чатов\n\n"
        "*Выберите необходимый чат ⤵️*"
    )

    # Формируем клавиатуру с кнопками
    kb = InlineKeyboardMarkup(row_width=2)

    # Кнопки: удалить все и создать новый
    kb.add(
        InlineKeyboardButton("❌ Удалить все чаты", callback_data="delete_all_chats"),
        InlineKeyboardButton("➕ Новый чат", callback_data="create_chat")
    )

    # Кнопки чатов
    for chat in chats:
        chat_name = chat["name"]
        chat_id = chat["id"]
        if chat_id == current_chat_id:
            chat_button_text = f"✅ {chat_name}"
        else:
            chat_button_text = chat_name
        kb.add(InlineKeyboardButton(chat_button_text, callback_data=f"select_chat:{chat_id}"))

    # Пагинация
    kb.row(
        InlineKeyboardButton(" ⏮ ", callback_data=f"page:first:{new_page}"),
        InlineKeyboardButton(" ◀ ", callback_data=f"page:prev:{new_page}"),
        InlineKeyboardButton(" ▶ ", callback_data=f"page:next:{new_page}"),
        InlineKeyboardButton(" ⏭ ", callback_data=f"page:last:{new_page}")
    )

    # Назад
    kb.add(InlineKeyboardButton(" 🔙 Назад", callback_data="settings"))

    # Отправляем обновленное сообщение с чатиками и кнопками
    try:
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        pass

    # Закрытие всплывающего окна
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('select_chat:'))
async def select_chat(call: CallbackQuery):
    """
    Обработчик выбора чата. Позволяет пользователю выбрать чат для переключения
    и отображения дополнительных настроек чата.

    :param call: Объект CallbackQuery, содержащий данные вызова.
    """
    # Получаем ID выбранного чата
    chat_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    # Получаем данные пользователя
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем информацию о выбранном чате
    chat = await db.get_chat_by_id(chat_id)
    chat_name = chat["name"]

    # Текст для выбранного чата
    text = f'Управление чатом\n"*{chat_name}*"'

    # Формируем кнопки для управления выбранным чатом
    select_button_text = "✅ Выбран" if chat_id == user["current_chat_id"] else " ▶️ Выбрать этот чат"
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(select_button_text, callback_data=f"select_active_chat:{chat_id}"),
        InlineKeyboardButton("✏️ Переименовать чат", callback_data=f"rename_chat:{chat_id}"),
        InlineKeyboardButton("🗑 Удалить чат", callback_data=f"delete_selected_chat:{chat_id}"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Обновляем сообщение с новым текстом и кнопками
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('select_active_chat:'))
async def select_active_chat(call: CallbackQuery):
    """
    Обрабатывает выбор активного чата пользователем.

    При получении callback-запроса с выбранным чатом обновляется текущий активный чат
    пользователя и отправляется сообщение о том, что чат успешно загружен.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID выбранного чата
    user_id = call.from_user.id  # Получаем ID пользователя
    user = await db.get_user(user_id)  # Получаем данные пользователя из базы данных

    if not user:
        # Если пользователь не найден, показываем ошибку
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Обновляем текущий активный чат для пользователя в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE users SET current_chat_id = $1 WHERE user_id = $2", chat_id, user["user_id"]
    )
    await conn.close()

    # Отправляем сообщение о том, что чат успешно загружен
    await call.message.edit_text("Чат успешно загружен. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith('rename_chat:'))
async def rename_chat(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает запрос на переименование чата.

    При получении callback-запроса с ID чата сохраняет его в состоянии для дальнейшего использования,
    затем запрашивает новое имя чата у пользователя.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Сохраняем chat_id в состояние FSM для дальнейшего использования
    await state.update_data(chat_id=chat_id)

    # Запрашиваем новое имя чата у пользователя
    await call.message.answer("Введите новое имя для чата:")

    # Переходим в состояние ожидания нового имени чата
    await EnterChatRename.chat_name.set()


@dp.callback_query_handler(lambda c: c.data.startswith('delete_selected_chat:'))
async def delete_selected_chat(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление выбранного чата.

    При получении callback-запроса с ID чата удаляет соответствующий чат из базы данных и
    обновляет список чатов, показывая пользователю уведомление об успешном удалении.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Удаляем выбранный чат из базы данных
    conn = await db.get_conn()
    await conn.execute("DELETE FROM chats WHERE id = $1", chat_id)
    await conn.close()

    # Отправляем сообщение об успешном удалении
    await call.message.edit_text("Чат успешно удалён. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(lambda c: c.data.startswith('select_chat:'))
async def select_chat(call: CallbackQuery):
    """
    Обрабатывает выбор чата пользователем.

    При получении callback-запроса с ID выбранного чата обновляется текущий активный чат
    пользователя и отображается обновлённый список чатов.
    """
    chat_id = int(call.data.split(":")[1])  # Извлекаем ID чата
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        # Если пользователь не найден, показываем ошибку
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Обновляем текущий активный чат пользователя в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE users SET current_chat_id = $1 WHERE user_id = $2", chat_id, user["user_id"]
    )
    await conn.close()

    # Обновляем список чатов
    await show_my_chats(call)


@dp.callback_query_handler(text="delete_all_chats")
async def confirm_delete_all_chats(call: CallbackQuery):
    """
    Запрашивает подтверждение на удаление всех чатов.

    При получении callback-запроса с текстом подтверждения, отправляется сообщение с запросом
    на подтверждение удаления всех чатов. Если пользователь подтверждает, чаты будут удалены.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Формируем текст для подтверждения удаления
    confirmation_text = "Вы действительно хотите удалить все чаты?"
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("❌ Удалить все чаты", callback_data="confirm_delete_all_chats"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Отправляем сообщение с кнопками подтверждения
    await call.message.edit_text(confirmation_text, reply_markup=kb)
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(text="confirm_delete_all_chats")
async def delete_all_chats(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление всех чатов пользователя.

    При получении callback-запроса с подтверждением, удаляет все чаты пользователя из базы данных,
    обновляет список чатов и отправляет уведомление об успешном удалении.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Удаляем все чаты пользователя из базы данных
    conn = await db.get_conn()
    await conn.execute("DELETE FROM chats WHERE user_id = $1", user_id)
    await conn.close()

    # Обновляем список чатов
    await show_my_chats(call)

    # Отправляем сообщение об успешном удалении
    await call.message.edit_text("Все чаты успешно удалены. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()


@dp.callback_query_handler(text="create_chat")
async def create_chat(call: CallbackQuery):
    """
    Запрашивает у пользователя название для нового чата.

    При получении callback-запроса с командой создания чата, проверяет лимит чатов,
    затем запрашивает у пользователя название для нового чата и переходит в состояние ожидания ввода.
    """
    if not await check_access_or_prompt(call):
        return
    user_id = call.from_user.id  # Получаем ID пользователя

    # Проверка количества уже созданных чатов
    conn = await db.get_conn()
    chat_count = await conn.fetchval("SELECT COUNT(*) FROM chats WHERE user_id = $1", user_id)
    await conn.close()

    if chat_count >= 10:
        await call.answer("Вы уже создали максимум 10 чатов. Удалите один, чтобы создать новый.", show_alert=True)
        return

    # Запрашиваем название нового чата
    await call.message.answer("Введите название чата:")

    # Переходим в состояние ожидания ввода названия нового чата
    await EnterChatName.chat_name.set()



@dp.message_handler(state=EnterChatName.chat_name)
async def process_new_chat_name(message: Message, state: FSMContext):
    """
    Обрабатывает введённое пользователем название нового чата.

    При получении нового имени чата, проверяет его на пустоту, затем создает новый чат в базе данных,
    обновляет текущий чат пользователя и отправляет уведомление об успешном создании чата.
    """
    user_id = message.from_user.id  # Получаем ID пользователя
    chat_name = message.text.strip()  # Получаем название чата

    if not chat_name:
        # Если название пустое, запрашиваем ввод заново
        await message.answer("Название чата не может быть пустым. Пожалуйста, введите название.")
        return

    # Создаем новый чат в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "INSERT INTO chats (user_id, name, created_at, updated_at) VALUES ($1, $2, NOW(), NOW())",
        user_id, chat_name
    )
    await conn.close()

    # Получаем ID нового чата
    conn = await db.get_conn()
    new_chat_id = await conn.fetchval(
        "SELECT id FROM chats WHERE user_id = $1 AND name = $2 LIMIT 1", user_id, chat_name
    )
    await conn.close()

    # Устанавливаем новый чат как активный
    await db.set_current_chat(user_id, new_chat_id)

    # Подтверждаем создание чата
    await message.answer(f'Чат "_{chat_name}_" успешно создан!\n\n*Введите запрос ⤵️*', parse_mode="Markdown")

    # Завершаем состояние
    await state.finish()


@dp.message_handler(state=EnterChatRename.chat_name)
async def process_rename_chat_name(message: Message, state: FSMContext):
    """
    Обрабатывает запрос на переименование чата.

    При получении нового имени для чата, проверяет его на пустоту, затем обновляет имя чата в базе данных
    и отправляет уведомление о том, что переименование успешно завершено.
    """
    user_id = message.from_user.id  # Получаем ID пользователя
    chat_name = message.text.strip()  # Получаем новое имя чата

    if not chat_name:
        # Если название пустое, запрашиваем ввод заново
        await message.answer("Название чата не может быть пустым. Пожалуйста, введите название.")
        return

    # Получаем данные из состояния (chat_id)
    data = await state.get_data()
    chat_id = data["chat_id"]  # Получаем ID чата из состояния

    # Обновляем имя чата в базе данных
    conn = await db.get_conn()
    await conn.execute(
        "UPDATE chats SET name = $1, updated_at = NOW() WHERE id = $2 AND user_id = $3",
        chat_name, chat_id, user_id
    )
    await conn.close()

    # Подтверждаем успешное переименование чата
    await message.answer(f'Чат успешно переименован в "_{chat_name}_".\n\n*Введите запрос ⤵️*', parse_mode="Markdown")

    # Завершаем состояние
    await state.finish()


@dp.callback_query_handler(text="delete_chat")
async def delete_chat(call: CallbackQuery):
    """
    Обрабатывает запрос на удаление текущего чата пользователя.

    При получении запроса, запрашивает у пользователя подтверждение на удаление чата.
    Если пользователь подтверждает удаление, удаляет чат из базы данных.
    """
    if not await check_access_or_prompt(call):
        return
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Получаем имя текущего чата пользователя
    conn = await db.get_conn()
    chat = await conn.fetchrow("SELECT name FROM chats WHERE id = $1", user["current_chat_id"])
    await conn.close()

    if not chat:
        # Если чатов нет, сообщаем пользователю
        await call.message.edit_text("Активных чатов нет. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
        return

    chat_name = chat["name"]  # Извлекаем название чата

    # Запрашиваем у пользователя подтверждение удаления
    confirmation_text = f'Вы действительно хотите удалить чат: "*{chat_name}*?"'
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Удалить чат", callback_data="confirm_delete_chat"),
        InlineKeyboardButton("🔙 Назад", callback_data="my_chats")
    )

    # Отправляем сообщение с запросом подтверждения удаления
    await call.message.edit_text(confirmation_text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()  # Закрытие всплывающего окна


@dp.callback_query_handler(text="confirm_delete_chat")
async def confirm_delete_chat(call: CallbackQuery):
    """
    Подтверждает удаление чата пользователя.

    При получении запроса на подтверждение удаления, удаляет текущий чат пользователя из базы данных
    и отправляет уведомление об успешном удалении.
    """
    user_id = call.from_user.id  # Получаем ID пользователя

    # Получаем данные пользователя из базы данных
    user = await db.get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    # Удаляем текущий чат пользователя из базы данных
    conn = await db.get_conn()
    await conn.execute(
        "DELETE FROM chats WHERE id = $1", user["current_chat_id"]

    )
    await conn.close()

    # Подтверждаем успешное удаление чата
    await call.message.edit_text("Чат успешно удален. \n\n*Введите запрос ⤵️*", parse_mode="Markdown")
    await call.answer()


# Проверка доступа к ChatGPT по сроку (14 дней + продления за рефералов)
# Если доступ закончился — отправляет сообщение и возвращает False
async def check_access_or_prompt(message) -> bool:
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    # если вдруг пользователя нет в БД (например, старые апдейты/ручные тесты)
    if user is None:
        await db.add_user(
            user_id,
            getattr(message.from_user, "username", None),
            getattr(message.from_user, "first_name", None),
            0
        )
        user = await db.get_user(user_id)

    now = datetime.utcnow()
    access_until = user.get("gpt_access_until")

    # Если у пользователя ещё нет срока — выдаём дефолтные 14 дней и сохраняем в БД
    if not access_until:
        await db.extend_gpt_access(user_id, 14)
        user = await db.get_user(user_id)
        access_until = user.get("gpt_access_until")


    # страховка: если в БД по какой-то причине NULL — даём 14 дней (пока без сохранения в БД)
    if access_until is None:
        access_until = now + timedelta(days=14)

    if now >= access_until:
        ref_link = f"{bot_url}?start=r{user_id}"

        from urllib.parse import quote
        share_url = f"https://t.me/share/url?url={quote(ref_link)}"

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("💰 Доступ к ChatGPT", callback_data="buy_chatgpt_14days"),
            InlineKeyboardButton("📩 Поделиться ссылкой (+14 дней)", url=share_url)
        )

        await bot.send_message(
            user_id,
            f"⛔️ Доступ к ChatGPT закончился.\n\n"
            f"Приглашай друзей по своей ссылке — за каждого даём +14 дней.\n"
            f"Или оплатите доступ к ChatGPT на 14 дней\n\n"
            f"Твоя ссылка:\n{ref_link}",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return False

    return True

async def check_reg(user_id) -> bool:
    status: ChatMember = await bot.get_chat_member(channel_id, user_id)
    # Если пользователь не подписан (status == "left"), блокируем дальнейшее выполнение
    if status.status == "left":
        return False
    return True

@dp.callback_query_handler(text="disable_ref_notifications")
async def disable_notifications(call: CallbackQuery):
    await db.set_ref_notifications(call.from_user.id, False)
    await call.message.edit_reply_markup()  # убираем кнопку
    await call.answer("Уведомления отключены.", show_alert=True)


@dp.callback_query_handler(text="enable_ref_notifications")
async def enable_notifications(call: CallbackQuery):
    await db.set_ref_notifications(call.from_user.id, True)
    await call.answer("Уведомления включены.", show_alert=True)

from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

INACTIVITY_HOURS = 24

async def close_inactive_chat_and_prompt(message, *, with_mode_banner: bool):
    """
    Если у пользователя выбран активный чат, но в нём не было запросов > 24 ч,
    снимаем активный чат, переводим бот в режим ChatGPT и отправляем нужные сообщения.
    Возвращает True, если чат был закрыт и мы уже всё показали пользователю.
    """
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    chat_id = user.get("current_chat_id")
    if not chat_id:
        return False

    chat = await db.get_chat_by_id(chat_id)
    if not chat:
        # на всякий случай почистим ссылку у пользователя
        await db.set_current_chat(user_id, None)
        return False

    last_touch = await db.get_chat_last_activity(chat_id)
    if not last_touch:
        return False

    now = datetime.utcnow()  # работаем в UTC
    if now - last_touch <= timedelta(hours=INACTIVITY_HOURS):
        logger.info(f"last_touch={last_touch}, now={now}, delta={(now - last_touch)}")
        return False

    # Снимаем активный чат и переводим в ChatGPT
    await db.set_current_chat(user_id, None)
    await db.change_default_ai(user_id, "chatgpt")


    if with_mode_banner:
        await message.answer("Режим: ChatGPT", reply_markup=user_kb.get_menu("chatgpt"))

    # Уведомление о закрытии + кнопка «Мои чаты»
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("🗂 Мои чаты", callback_data="my_chats")
    )
    chat_name = chat["name"] or "Без названия"
    await message.answer(
        f'Ваш диалог "*{chat_name}*" был закрыт, введите новый запрос или откройте предыдущий диалог из списка ⤵️',
        parse_mode="Markdown",
        reply_markup=kb
    )
    return True


@dp.callback_query_handler(Text(startswith="choose_ai:"))
async def choose_ai(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":")[1]          # 'gpt' | 'mj'
    user_id = call.from_user.id

    # ⚙️ гарантируем, что пользователь есть в БД
    user = await db.get_user(user_id)
    if user is None:
        await db.add_user(user_id, call.from_user.username, call.from_user.first_name, 0)
        try:
            await db.set_model(user_id, "5")  # дефолт для GPT
        except Exception:
            pass
        await db.change_default_ai(user_id, "chatgpt" if choice == "gpt" else "image")

    await call.answer()

    if choice == "gpt":
        await ask_question(call.message, state)
    else:
        await gen_img(call.message, state)
