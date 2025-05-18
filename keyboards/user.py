from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove, WebAppInfo  # Импортируем необходимые классы для создания клавиатур
from urllib import parse  # Модуль для работы с URL


# Клавиатура для вывода реферальных средств (выбор способа вывода)
withdraw_ref_menu = InlineKeyboardMarkup(row_width=2).add(
    InlineKeyboardButton("На банковскую карту", callback_data='withdraw_ref:bank_card')).add(
    InlineKeyboardButton("QIWI", callback_data="withdraw_ref:qiwi"),
    InlineKeyboardButton("На баланс", callback_data="withdraw_ref:balance")
)


# Клавиатура с ссылками для информации о проекте и поддержке
about = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("📢Канал проекта", url="https://t.me/NeuronAgent"),
                                              InlineKeyboardButton("🆘Помощь", url="https://t.me/NeuronSupportBot"),
                                              InlineKeyboardButton("Инструкция для Midjourney", url="https://telegra.ph/Kak-polzovatsya-MidJourney-podrobnaya-instrukciya-10-16"))


# Кнопка для отмены действия (например, при вводе данных)
cancel = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(KeyboardButton("Отмена"))


# Клавиатура для пополнения баланса (предлагает выбрать тариф)
top_up_balance = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton("💰Выбрать тариф", callback_data="buy_sub"))


# Кнопка для подтверждения подписки на канал и проверки подписки
partner = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton("↗️Перейти и подписаться", url="https://t.me/NeuronAgent"),
    InlineKeyboardButton("✅Я подписался", callback_data="check_sub"))


# Кнопка для возврата к выбору суммы пополнения
back_to_choose = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton("🔙Назад", callback_data="back_to_choose_balance"))


# Языковые настройки для клавиатур
lang_text = {"en": "ENG", "ru": "RUS"}


# Кнопка для завершения текущего диалога (например, с ChatGPT) и перевода текста в аудио
def get_clear_or_audio():    
    
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("⚙️Настройки ChatGPT", callback_data="settings"),
        InlineKeyboardButton("🗣Озвучить текст", callback_data="text_to_audio"),
        InlineKeyboardButton("🗂Мои чаты", callback_data="my_chats"),
        InlineKeyboardButton("🗑Удалить чат", callback_data="delete_chat")
        )


# Клавиатура с настройками аккаунта пользователя (выбор тарифа, смена языка, сброс настроек)
def get_account(lang, from_msg):

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("💰Выбрать тариф", callback_data="buy_sub"),
        InlineKeyboardButton("⚙️Настройки ChatGPT", callback_data="settings")
    )

# Настройки ChatGPT
def settings(lang, from_msg):
    flag = '🇷🇺' if lang == 'ru' else '🇬🇧'

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("🤖Выбрать модель ChatGPT", callback_data="model_menu"),
        InlineKeyboardButton(f"Ответы ChatGPT: {flag}", callback_data=f"change_lang:{lang}:{from_msg}"),
        InlineKeyboardButton("✍🏻Рассказать о себе", callback_data="chatgpt_about_me"),
        InlineKeyboardButton("🎭Характер ChatGPT", callback_data="character_menu"),
        InlineKeyboardButton("🗣Изменить голос ChatGPT", callback_data="voice_menu"),
        InlineKeyboardButton("🗂Мои чаты", callback_data="my_chats"),
        InlineKeyboardButton("🔙Назад", callback_data="back_to_profile:acc")
    )

# Выбор модели GPT для диалогов
def model_keyboard(selected_model: str):
    models = {"4o": "GPT-4o",
              "o4-mini": "GPT-o4-mini",
              "4_1": "GPT-4.1",
              "o1": "GPT-o1"}
    buttons = [
        InlineKeyboardButton(
            f"{value}✅" if key == selected_model else value,
            callback_data=f"select_model:{key}"
        )
        for key, value in models.items()
    ]
    return InlineKeyboardMarkup(row_width=1).add(*buttons).add(
        InlineKeyboardButton("📋Отличия моделей GPT", url="https://telegra.ph/Otlichiya-modelej-GPT-12-24"),
        InlineKeyboardButton("🔙Назад", callback_data="back_to_profile:acc")
    )

# Выбор голоса для ChatGPT
def voice_keyboard(selected_voice: str):
    voices = {"alloy": "Даниэль(Alloy)",
              "echo": "Антоний(Echo)",
              "fable": "Чарли(Fable)",
              "onyx": "Михаил(Onyx)", 
              "nova": "Эмилия(Nova)", 
              "shimmer": "Сидни(Shimmer)"}
    buttons = [
        InlineKeyboardButton(
            f"{value}✅" if key == selected_voice else value, 
            callback_data=f"select_voice:{key}"
        )
        for key, value in voices.items()
    ]
    return InlineKeyboardMarkup(row_width=2).add(*buttons).add(
        InlineKeyboardButton("🔉Прослушать голоса", callback_data="check_voice"),
        InlineKeyboardButton("🔙Назад", callback_data="back_to_profile:acc")
    )


# Удалить описание или вернуться назад
def clear_description():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("✖️Удалить описание", callback_data="reset_chatgpt_settings"),
        InlineKeyboardButton("🔙Назад", callback_data="back_to_profile:acc")
    )


# Кнопка для вариации запроса (например, в MidJourney)
def get_try_prompt(ai_type):

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("🔄 Другой вариант", callback_data=f"try_prompt:{ai_type}"))


# Главное меню бота, где пользователь выбирает, с каким AI он хочет работать (ChatGPT или MidJourney)
def get_menu(default_ai):

    return ReplyKeyboardMarkup(resize_keyboard=True, row_width=2).add(KeyboardButton(f"{'🎨Midjourney✅' if default_ai == 'image' else '🎨Midjourney'}"),
                                                                      KeyboardButton(f"{'🎨Image OpenAI✅' if default_ai == 'image_openai' else '🎨Image OpenAI'}"),
                                                                      KeyboardButton(f"{'💬ChatGPT✅' if default_ai == 'chatgpt' else '💬ChatGPT'}"),
                                                                      KeyboardButton("⚙Аккаунт"),
                                                                      KeyboardButton("👨🏻‍💻Поддержка"),
                                                                      KeyboardButton("🤝Партнерская программа"))


# Кнопки для выбора способа оплаты (Tinkoff, криптовалюта и т.д.)
def get_pay_urls(urls, order_id, model, src='acc'):

    back = f"buy_chatgpt_tokens:{model}:normal" if model != 'midjourney' else 'buy_midjourney_requests'

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("Банковская карта", url=urls["tinkoff"]),
        # InlineKeyboardButton("Криптовалюта", web_app=WebAppInfo(url=urls["freekassa"])),
        InlineKeyboardButton("Telegram Stars", callback_data=f"tg_stars:{order_id}"),
        InlineKeyboardButton("🔙Назад", callback_data=back))


# Клавиатура для оплаты через Telegram Stars
def get_tg_stars_pay():

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Telegram Stars", pay=True))  # Кнопка для оплаты через Telegram
    kb.add(InlineKeyboardButton("🔙Назад", callback_data=f"delete_msg"))  # Кнопка для возврата
    return kb


# Кнопки для управления реферальными ссылками (поделиться ссылкой, вывести средства)
def get_ref_menu(url):

    text_url = parse.quote(url)  # Кодируем URL
    url = f'https://t.me/share/url?url={text_url}'  # Формируем ссылку для поделиться
    return InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton('📩Поделится ссылкой', url=url),
                                                 InlineKeyboardButton('💳Вывод средств',
                                                                      callback_data='withdraw_ref_menu'),
                                                 InlineKeyboardButton('🔙Назад', callback_data='check_sub'))


# Кнопки для выбора изображения (вариации, зум и т.д.)
def get_try_prompt_or_choose(task_id, include_try=False):

    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("u1", callback_data=f"choose_image:{task_id}:1"),
        InlineKeyboardButton("u2", callback_data=f"choose_image:{task_id}:2"),
        InlineKeyboardButton("u3", callback_data=f"choose_image:{task_id}:3"),
        InlineKeyboardButton("u4", callback_data=f"choose_image:{task_id}:4"))
    if include_try:
        kb.add(InlineKeyboardButton("🔄 Ещё варианты", callback_data=f"try_prompt:image"))  # Кнопка для вариации запроса
    return kb


# Кнопки для изменения изображения (вариация, зум и т.д.)
def get_choose(task_id):

    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🪄 Vary (Subtle)", callback_data=f"change_image:vary:low:{task_id}"),
        InlineKeyboardButton("🪄 Vary (Strong)", callback_data=f"change_image:vary:high:{task_id}"),
        InlineKeyboardButton("🔍 Zoom Out 2x", callback_data=f"change_image:zoom:2:{task_id}"),
        InlineKeyboardButton("🔍 Zoom Out 1.5x", callback_data=f"change_image:zoom:1.5:{task_id}"))


''' Новые кнопки для выбора покупки токенов для GPT или MJ '''

# Кнопки выбора типа токенов
def get_neural_network_menu():

    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("💬ChatGPT", callback_data="select_gpt_tokens"),
        InlineKeyboardButton("🎨Midjourney", callback_data="buy_midjourney_requests")
    )

def get_chatgpt_models():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("GPT-4.1", callback_data="buy_chatgpt_tokens:4.1:normal"),
        InlineKeyboardButton("GPT-o1", callback_data="buy_chatgpt_tokens:o1:normal"),
        InlineKeyboardButton("📋Отличия моделей GPT", url="https://telegra.ph/Otlichiya-modelej-GPT-12-24"),
        InlineKeyboardButton("🔙Назад", callback_data="buy_sub")
    )

def get_chatgpt_models_noback(discount=None):

    target = 'discount' if discount else 'normal'
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("GPT-4.1", callback_data=f"buy_chatgpt_tokens:4.1:{target}"),
        InlineKeyboardButton("GPT-o1", callback_data=f"buy_chatgpt_tokens:o1:{target}"),
        InlineKeyboardButton("📋Отличия моделей GPT", url="https://telegra.ph/Otlichiya-modelej-GPT-12-24"),
    )


# Кнопки выбора количества токенов для ChatGPT
# Mode - Normal - пользователь решил купить токены, Discount - у него действует скидка, Notification - перешел из уведомления о скидке
# Model - 4.1, o1
def get_chatgpt_tokens_menu(mode, model):

    source = 'acc' if mode == 'normal' else 'not_gpt'
    back = "buy_sub" if mode == 'normal' else 'back_to_discount' 

    prices = {'4.1': {'normal': {'price': [199, 349, 469, 739, 10],
                                'percent': [0, 12, 21, 25, 0]},
                     'discount': {'price': ['199 > 189', '349 > 315', '469 > 412', '739 > 628', '10 > 5'],
                                  'price_data' : [189, 315, 412, 628, 5],
                                  'percent': [5, 10, 12, 15, 0]}},


              'o1': {'normal': {'price': [199, 349, 469, 739, 10],
                                'percent': [0, 12, 21, 25, 0]},
                     'discount': {'price': ['199 > 189', '349 > 315', '469 > 412', '739 > 628', '10 > 5'],
                                  'price_data' : [189, 315, 412, 628, 5],
                                  'percent': [5, 10, 12, 15, 0]}}}

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(
            f"20 тыс токенов, {prices[model][mode]['price'][0]}₽" + ('' if mode == 'normal' else f' (-{prices[model][mode]["percent"][0]}%)'), 
            callback_data=f"tokens:20000:{model}:{prices[model][mode]['price'][0] if mode == 'normal' else prices[model][mode]['price_data'][0]}:{source}"),
        InlineKeyboardButton(
            f"40 тыс токенов, {prices[model][mode]['price'][1]}₽ (-{prices[model][mode]['percent'][1]}%)", 
            callback_data=f"tokens:40000:{model}:{prices[model][mode]['price'][1] if mode == 'normal' else prices[model][mode]['price_data'][1]}:{source}"),
        InlineKeyboardButton(
            f"60 тыс токенов, {prices[model][mode]['price'][2]}₽ (-{prices[model][mode]['percent'][2]}%)",
            callback_data=f"tokens:60000:{model}:{prices[model][mode]['price'][2] if mode == 'normal' else prices[model][mode]['price_data'][2]}:{source}"),
        InlineKeyboardButton(
            f"100 тыс токенов, {prices[model][mode]['price'][3]}₽ (-{prices[model][mode]['percent'][3]}%)",
            callback_data=f"tokens:100000:{model}:{prices[model][mode]['price'][3] if mode == 'normal' else prices[model][mode]['price_data'][3]}:{source}"),
        # InlineKeyboardButton(
        #     f"1 тыс токенов, {prices[model][mode]['price'][4]}₽ (-{prices[model][mode]['percent'][4]}%)", 
        #     callback_data=f"tokens:1000:{model}:{prices[model][mode]['price'][4] if mode == 'normal' else prices[model][mode]['price_data'][4]}:{source}"),  
        InlineKeyboardButton("📋Что такое токены", url="https://telegra.ph/CHto-takoe-tokeny-12-23-3"),          
        InlineKeyboardButton("🔙Назад", callback_data=back)
    )


# Кнопки выбора количества запросов для Midjourney
def get_midjourney_requests_menu():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("10 генераций, 149₽", callback_data="select_midjourney_requests:10:149:acc"),
        InlineKeyboardButton("20 генераций, 259₽ (-13%)", callback_data="select_midjourney_requests:20:259:acc"),
        InlineKeyboardButton("50 генераций, 599₽ (-19%)", callback_data="select_midjourney_requests:50:599:acc"),
        InlineKeyboardButton("100 генераций, 1099₽ (-26%)", callback_data="select_midjourney_requests:100:1099:acc"),
        InlineKeyboardButton("🔙Назад", callback_data="buy_sub")
    )

'''
# Кнопки выбора количества токенов для ChatGPT СО СКИДКОЙ
def get_chatgpt_discount_tokens_menu():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("100 тыс токенов, 149₽ > 139₽ (-5%)", callback_data="select_chatgpt_tokens:100000:139:acc"),
        InlineKeyboardButton("200 тыс токенов, 249₽ > 224₽ (-10%)", callback_data="select_chatgpt_tokens:200000:224:acc"),
        InlineKeyboardButton("500 тыс токенов, 449₽ > 381₽ (-15%)", callback_data="select_chatgpt_tokens:500000:381:acc"),
        InlineKeyboardButton("🔙Назад", callback_data="buy_sub")
    )
'''

# Кнопки выбора количества запросов для Midjourney СО СКИДКОЙ
def get_midjourney_discount_requests_menu():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("10 генераций, 149₽", callback_data="select_midjourney_requests:10:149:acc"),
        InlineKeyboardButton("20 генераций, 259₽ > 246₽ (-5%)", callback_data="select_midjourney_requests:20:246:acc"),
        InlineKeyboardButton("50 генераций, 599₽ > 550₽ (-8%)", callback_data="select_midjourney_requests:50:550:acc"),
        InlineKeyboardButton("100 генераций, 1099₽ > 989₽ (-10%)", callback_data="select_midjourney_requests:100:989:acc"),
        InlineKeyboardButton("🔙Назад", callback_data="buy_sub")
    )

'''    
# Кнопки выбора количества токенов для ChatGPT СО СКИДКОЙ при уведомлении
def get_chatgpt_discount_nofication():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("100 тыс токенов, 149₽ > 139₽ (-5%)", callback_data="select_chatgpt_tokens:100000:139:not_gpt"),
        InlineKeyboardButton("200 тыс токенов, 249₽ > 224₽ (-10%)", callback_data="select_chatgpt_tokens:200000:224:not_gpt"),
        InlineKeyboardButton("500 тыс токенов, 449₽ > 381₽ (-15%)", callback_data="select_chatgpt_tokens:500000:381:not_gpt")
    )
'''

# Кнопки выбора количества запросов для Midjourney СО СКИДКОЙ при уведомлении
def get_midjourney_discount_notification():

    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("20 генераций, 259₽ > 246₽ (-5%)", callback_data="select_midjourney_requests:20:246:not_mj"),
        InlineKeyboardButton("50 генераций, 599₽ > 550₽ (-8%)", callback_data="select_midjourney_requests:50:550:not_mj"),
        InlineKeyboardButton("100 генераций, 1099₽ > 989₽ (-10%)", callback_data="select_midjourney_requests:100:989:not_mj")
    )

# Inline-меню для "Изображения от OpenAI"
image_openai_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Генерации изображения", callback_data="generate_image_prompt"),
            InlineKeyboardButton(text="Редактировать изображение", callback_data="edit_image"),
        ],
        [
            InlineKeyboardButton(text="Настройки", callback_data="image_settings"),
        ],
    ]
)

# Inline-меню для настроек
settings_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="/size — Выбрать размер", callback_data="set_size"),
            InlineKeyboardButton(text="/quality — Выбрать качество", callback_data="set_quality"),
        ],
        [
            InlineKeyboardButton(text="/background — Выбрать фон", callback_data="set_background"),
        ],
        [
            InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu"),
        ],
    ]
)

# Inline-клавиатура для выбора размера
size_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="1024x1024", callback_data="size_1024x1024"),
            InlineKeyboardButton(text="1536x1024", callback_data="size_1536x1024"),
            InlineKeyboardButton(text="1024x1536", callback_data="size_1024x1536"),
        ],
        [
            InlineKeyboardButton(text="Назад", callback_data="back_to_settings"),
        ]
    ]
)