from aiogram.types import Message, CallbackQuery, ChatActions
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher import FSMContext

from utils import db, ai, more_api  # Модули для взаимодействия с базой данных и API
from states import user as states  # Состояния для пользователя (FSM)
import keyboards.user as user_kb  # Клавиатуры для взаимодействия с пользователем
from config import bot_url
from create_bot import dp  # Диспетчер для регистрации хендлеров


# Сообщения об ошибках для некорректных реквизитов
invalid_purse_text = {'qiwi': 'Введите корректный номер телефона. Например: 79111111111',
                      'bank_card': 'Введите корректный номер карты. Например: 4012888812345678'}


# Хендлер для вывода средств через реферальную систему
@dp.callback_query_handler(text='withdraw_ref_menu')
async def withdraw_ref_menu(call: CallbackQuery):

    user = await db.get_user(call.from_user.id)  # Получаем данные пользователя из базы
    if user['ref_balance'] >= 100:
        # Если баланс достаточен для вывода (минимум 100 рублей), показываем меню вывода средств
        await call.message.answer(
            f'''<b>💸 Вывод средств</b>

<b>Баланс</b>: {user["ref_balance"]} рублей

Вы можете вывести средства на Банковскую карту, QIWI кошелёк, а также использовать для оплаты наших услуг в боте.''',
            reply_markup=user_kb.withdraw_ref_menu)  # Клавиатура с вариантами вывода
    else:
        # Если баланс меньше 100 рублей, вывод средств невозможен
        await call.message.answer('<b>❗️Минимальная сумма для вывода - 100 рублей</b>')
    await call.answer()


# Хендлер для выбора способа вывода средств через callback
@dp.callback_query_handler(Text(startswith='withdraw_ref'))
async def withdraw_ref(call: CallbackQuery, state: FSMContext):

    withdraw_type = call.data.split(':')[1]  # Получаем тип вывода (банк, QIWI или на баланс)
    if withdraw_type == 'bank_card':
        # Если выбран вывод на банковскую карту, запрашиваем номер карты
        await call.message.answer('Введите номер карты. Например: 4012888812345678', reply_markup=user_kb.cancel)
    elif withdraw_type == 'qiwi':
        # Если выбран вывод на QIWI, запрашиваем номер телефона
        await call.message.answer('Введите номер телефона. Например: 79111111111', reply_markup=user_kb.cancel)
    elif withdraw_type == 'balance':
        # Если выбран вывод на баланс бота, сразу зачисляем средства на баланс
        await db.add_balance_from_ref(call.from_user.id)  # Переносим средства с реферального баланса на баланс бота
        await call.message.answer('Средства зачислены на баланс')
        return

    # Устанавливаем состояние для ввода реквизитов
    await states.EnterWithdrawInfo.purse.set()
    await state.update_data(withdraw_type=withdraw_type)  # Сохраняем тип вывода в состояние


# Хендлер для завершения процесса вывода средств (ввод реквизитов)
@dp.message_handler(state=states.EnterWithdrawInfo.purse)
async def finish_withdraw_ref(message: Message, state: FSMContext):

    state_data = await state.get_data()  # Получаем данные из состояния (тип вывода)
    withdraw_type = state_data['withdraw_type']
    try:
        purse = int(message.text)  # Пробуем преобразовать введенные данные в число
    except ValueError:
        await message.answer(invalid_purse_text[withdraw_type])  # Если не удалось — отправляем сообщение об ошибке
        return

    # Проверяем корректность введенных данных в зависимости от типа вывода
    if withdraw_type == 'qiwi':
        if len(str(purse)) != 11:  # Для QIWI номер телефона должен содержать 11 цифр
            await message.answer(invalid_purse_text[withdraw_type])
            return
    elif withdraw_type == 'bank_card':
        if len(str(purse)) != 16:  # Для банковской карты номер должен содержать 16 цифр
            await message.answer(invalid_purse_text[withdraw_type])
            return

    user = await db.get_user(message.from_user.id)  # Получаем данные пользователя из базы
    withdraw_data = more_api.withdraw_ref_balance(purse, user['ref_balance'], withdraw_type)  # Запрос на вывод через API
    if withdraw_data['status'] == 'error':
        
        # Обрабатываем возможные ошибки при выводе
        if withdraw_data['desc'].startswith('Invalid Purse'):
            await message.answer(invalid_purse_text[withdraw_type])  # Неправильные реквизиты
            return
        else:
            await message.answer(f'Произошла ошибка, отправьте её администратору: {withdraw_data["desc"]}')  # Другая ошибка

    # Если все прошло успешно, обнуляем реферальный баланс пользователя и сохраняем транзакцию
    await db.add_withdraw(message.from_user.id, user['ref_balance'])
    await db.reset_ref_balance(message.from_user.id)
    await message.answer('Деньги будут скоро зачислены')  # Уведомляем пользователя об успешном выводе
