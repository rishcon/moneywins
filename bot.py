import os
import re
import logging
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
    ConversationHandler
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '8145762372:AAFKVlNjCopg_VYnlAq92d4LDCITYUMQMXY')

# Состояния для ConversationHandler
AMOUNT, FROM_CUR, TO_CUR = range(3)

# Источники курсов
API_SOURCES = [
    # latest endpoint
    lambda frm, to, amt: requests.get(
        "https://api.exchangerate.host/latest",
        params={"base": frm, "symbols": to}, timeout=5
    ).json().get('rates', {}).get(to) * float(amt),
    # convert endpoint
    lambda frm, to, amt: requests.get(
        "https://api.exchangerate.host/convert",
        params={"from": frm, "to": to, "amount": amt}, timeout=5
    ).json().get('result'),
    # ER-API endpoint
    lambda frm, to, amt: requests.get(
        f"https://open.er-api.com/v6/latest/{frm}", timeout=5
    ).json().get('rates', {}).get(to) * float(amt)
]

# Популярные пары
POPULAR = [
    ('100 USD → KZT', '100:USD:KZT'),
    ('1 EUR → USD', '1:EUR:USD'),
    ('1 GBP → USD', '1:GBP:USD'),
    ('1 USD → EUR', '1:USD:EUR'),
]

# Команда /start
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f'convert:{data}')] for name, data in POPULAR
    ]
    keyboard.append([InlineKeyboardButton('💬 Ручной ввод', callback_data='manual')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        '👋 Привет! Выбери быстрый вариант или выполните ручной ввод:',
        reply_markup=reply_markup
    )

# Начало ручного ввода
def manual_start(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    query.message.reply_text(
        'Введите сумму для конвертации:',
        reply_markup=ReplyKeyboardRemove()
    )
    return AMOUNT

# Шаг: сумма
def manual_amount(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    try:
        float(text)
        context.user_data['manual_amount'] = text
    except ValueError:
        update.message.reply_text('❗️ Введите корректное число, например: 100')
        return AMOUNT
    presets = ['USD', 'EUR', 'GBP', 'KZT', 'RUB']
    buttons = [[KeyboardButton(c) for c in presets[i:i+3]] for i in range(0, len(presets), 3)]
    update.message.reply_text(
        'Выберите исходную валюту:',
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    )
    return FROM_CUR

# Шаг: исходная валюта
def manual_from(update: Update, context: CallbackContext) -> int:
    frm = update.message.text.strip().upper()
    if not re.fullmatch(r'[A-Za-z]{3}', frm):
        update.message.reply_text('❗️ Введите трехбуквенный код валюты, например USD')
        return FROM_CUR
    context.user_data['manual_from'] = frm
    presets = ['USD', 'EUR', 'GBP', 'KZT', 'RUB']
    buttons = [[KeyboardButton(c) for c in presets[i:i+3]] for i in range(0, len(presets), 3)]
    update.message.reply_text(
        'Выберите целевую валюту:',
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    )
    return TO_CUR

# Шаг: целевая валюта и конвертация
def manual_to(update: Update, context: CallbackContext) -> int:
    to = update.message.text.strip().upper()
    if not re.fullmatch(r'[A-Za-z]{3}', to):
        update.message.reply_text('❗️ Введите трехбуквенный код валюты, например EUR')
        return TO_CUR
    amt = context.user_data.pop('manual_amount')
    frm = context.user_data.pop('manual_from')
    result = None
    for src in API_SOURCES:
        try:
            res = src(frm, to, amt)
            if res is not None:
                result = res
                break
        except Exception as e:
            logger.warning(f'Manual convert source error: {e}')
            continue
    if result is not None:
        update.message.reply_text(
            f'{amt} {frm} = {result:.2f} {to}',
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        update.message.reply_text(
            '❗️ Не удалось получить курс.\nПопробуйте позже.',
            reply_markup=ReplyKeyboardRemove()
        )
    return ConversationHandler.END

# Отмена ручного ввода
def manual_cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('❌ Операция отменена.', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Обработка кнопок
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data == 'manual':
        return manual_start(update, context)
    if data.startswith('convert:'):
        try:
            _, amt, frm, to = data.split(':')
            result = None
            for src in API_SOURCES:
                try:
                    res = src(frm, to, amt)
                except Exception as e:
                    logger.warning(f'Quick convert source error: {e}')
                    continue
                if res is not None:
                    result = res
                    break
            if result is not None:
                query.message.reply_text(f'{amt} {frm} = {result:.2f} {to}')
            else:
                query.message.reply_text('❗️ Не удалось получить курс из всех источников.')
        except Exception as e:
            logger.error(f'Quick convert failed: {e}')
            query.message.reply_text('❗️ Ошибка при конвертации.')

# Основная функция
if __name__ == '__main__':
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    manual_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(manual_start, pattern='^manual$')],
        states={
            AMOUNT: [MessageHandler(Filters.text & ~Filters.command, manual_amount)],
            FROM_CUR: [MessageHandler(Filters.text & ~Filters.command, manual_from)],
            TO_CUR: [MessageHandler(Filters.text & ~Filters.command, manual_to)],
        },
        fallbacks=[CommandHandler('cancel', manual_cancel)],
        allow_reentry=True
    )
    dp.add_handler(manual_conv)
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(CommandHandler('cancel', manual_cancel))
    updater.start_polling()
    logger.info('🔔 Бот запущен')
    updater.idle()
