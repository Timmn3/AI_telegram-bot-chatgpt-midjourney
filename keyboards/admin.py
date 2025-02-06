from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton  # Импортируем типы кнопок для создания клавиатур


# Кнопка для отмены текущего действия (например, при рассылке сообщений или вводе данных)
cancel = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(KeyboardButton("Отмена"))


# Основное меню для администраторов с двумя кнопками: для управления партнерской программой и бонусными ссылками
admin_menu = InlineKeyboardMarkup(row_width=1).add(
    # Кнопка для перехода в меню партнерской программы
    InlineKeyboardButton('Партнерская программа', callback_data='admin_ref_menu'),
    # Кнопка для управления бонусными ссылками (промокодами)
    InlineKeyboardButton('Бонус ссылки', callback_data='admin_promo_menu'))

def more_stats_kb():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton('Расширенная статистика', callback_data='more_stats')
    )

def less_stats_kb():
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton('Краткая статистика', callback_data='stats')
    )