from aiogram.dispatcher.filters.state import StatesGroup, State  # Импортируем классы для работы с состояниями

# Класс, описывающий состояния для рассылки сообщений (Mailing)
class Mailing(StatesGroup):
    enter_text = State()  # Состояние, в котором администратор вводит текст для рассылки
    confirm = State()     # Состояние для подтверждения начала рассылки

# Состояния для начисления токенов
class TokenAdding(StatesGroup):
    enter_user_id = State()  # Состояние для ввода user_id
    choose_token_type = State()  # Состояние для выбора типа токенов
    enter_amount = State()  # Состояние для ввода количества токенов