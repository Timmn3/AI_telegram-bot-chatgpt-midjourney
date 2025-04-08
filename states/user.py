from aiogram.dispatcher.filters.state import StatesGroup, State  # Импортируем классы для работы с состояниями

# Класс для ввода запросов в ChatGPT и MidJourney
class EnterPromt(StatesGroup):
    gpt_prompt = State()  # Состояние для ввода запроса в ChatGPT
    mdjrny_prompt = State()  # Состояние для ввода запроса в MidJourney

# Класс для ввода суммы пополнения баланса
class EnterAmount(StatesGroup):
    enter_amount = State()  # Состояние для ввода суммы пополнения

# Класс для ввода информации для вывода средств (например, номер карты или кошелька)
class EnterWithdrawInfo(StatesGroup):
    purse = State()  # Состояние для ввода реквизитов для вывода средств

# Класс для изменения описания ChatGPT (информация о пользователе)
class ChangeChatGPTAboutMe(StatesGroup):
    text = State()  # Состояние для ввода текста с описанием пользователя для ChatGPT

class ChangeChatGPTCharacter(StatesGroup):
    text = State()  # Состояние для ввода текста с описанием характера модели для ChatGPT

# Класс для изменения настроек ChatGPT (например, тон, стиль ответов)
class ChangeChatGPTSettings(StatesGroup):
    text = State()  # Состояние для ввода текста с настройками для ChatGPT

# Класс для ввода имени нового чата
class EnterChatName(StatesGroup):
    chat_name = State()  # Состояние для ввода имени нового чата


# Класс для ввода имени имеющегося чата
class EnterChatRename(StatesGroup):
    chat_name = State()  # Состояние для ввода имени нового чата
