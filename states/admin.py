from aiogram.dispatcher.filters.state import StatesGroup, State  # Импортируем классы для работы с состояниями

# Класс, описывающий состояния для рассылки сообщений (Mailing)
class Mailing(StatesGroup):
    enter_text = State()  # Состояние, в котором администратор вводит текст для рассылки
    confirm = State()     # Состояние для подтверждения начала рассылки

