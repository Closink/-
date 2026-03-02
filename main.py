import asyncio
import logging
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree
from typing import Dict, Tuple
import pickle
import random

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "8546494996:AAEh4ylPyN8prRSy0LLr9OE0rZFwggrHEo4"
CHAT_ID = "-1002129097415"
ADMIN_IDS = [8186449861]

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

PREVIOUS_RATES_FILE = "previous_rates.pkl"
PHOTO_SETTINGS_FILE = "photo_settings.pkl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

photo_settings = {
    'use_photo': False,
    'photo_path': '',
    'photo_url': '',
    'photo_file_id': ''
}

def save_photo_settings():
    try:
        with open(PHOTO_SETTINGS_FILE, 'wb') as f:
            pickle.dump(photo_settings, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении настроек фото: {e}")

def load_photo_settings():
    global photo_settings
    try:
        if os.path.exists(PHOTO_SETTINGS_FILE):
            with open(PHOTO_SETTINGS_FILE, 'rb') as f:
                photo_settings.update(pickle.load(f))
    except Exception as e:
        logger.error(f"Ошибка при загрузке настроек фото: {e}")

def save_previous_rates(rates: dict):
    try:
        with open(PREVIOUS_RATES_FILE, 'wb') as f:
            pickle.dump(rates, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении предыдущих курсов: {e}")

def load_previous_rates() -> dict:
    try:
        if os.path.exists(PREVIOUS_RATES_FILE):
            with open(PREVIOUS_RATES_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке предыдущих курсов: {e}")
    return {}

def get_trend_emoji(current: float, previous: float) -> str:
    if previous == 0:
        return "🔄"
    
    if current > previous:
        return "📈"
    elif current < previous:
        return "📉"
    else:
        return "➖"

def get_trend_color(current: float, previous: float) -> str:
    if previous == 0:
        return "#808080"
    if current > previous:
        return "#00FF00"
    elif current < previous:
        return "#FF0000"
    else:
        return "#FFFF00"

def get_random_greeting():
    greetings = [
        "☀️ Доброе утро!",
        "🌅 Хорошего дня!",
        "💼 Удачной недели!",
        "📈 Прибыльных инвестиций!",
        "💰 Отличных заработков!",
        "🌟 Пусть день будет удачным!",
        "💫 С добрым утром!",
        "✨ Новый день - новые возможности!"
    ]
    return random.choice(greetings)

async def fetch_exchange_rates() -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CBR_URL) as response:
                if response.status == 200:
                    xml_data = await response.text()
                    root = ElementTree.fromstring(xml_data)
                    
                    rates = {}
                    
                    for valute in root.findall('.//Valute'):
                        char_code = valute.find('CharCode').text
                        if char_code in ['USD', 'EUR', 'CNY']:
                            value = valute.find('Value').text
                            nominal = valute.find('Nominal').text
                            
                            rate = float(value.replace(',', '.')) / int(nominal)
                            
                            rates[char_code] = round(rate, 4)
                    
                    return rates
                else:
                    logger.error(f"Ошибка при получении данных: {response.status}")
                    return {}
    except Exception as e:
        logger.error(f"Ошибка при получении курсов: {e}")
        return {}

def format_rates_message(rates: dict, previous_rates: dict, date: datetime) -> str:
    date_str = date.strftime("%d.%m.%Y")
    
    usd_trend = get_trend_emoji(rates.get('USD', 0), previous_rates.get('USD', 0))
    eur_trend = get_trend_emoji(rates.get('EUR', 0), previous_rates.get('EUR', 0))
    cny_trend = get_trend_emoji(rates.get('CNY', 0), previous_rates.get('CNY', 0))
    
    usd_change = rates.get('USD', 0) - previous_rates.get('USD', 0)
    eur_change = rates.get('EUR', 0) - previous_rates.get('EUR', 0)
    cny_change = rates.get('CNY', 0) - previous_rates.get('CNY', 0)
    
    usd_change_str = f"+{usd_change:.4f}" if usd_change > 0 else f"{usd_change:.4f}"
    eur_change_str = f"+{eur_change:.4f}" if eur_change > 0 else f"{eur_change:.4f}"
    cny_change_str = f"+{cny_change:.4f}" if cny_change > 0 else f"{cny_change:.4f}"
    
    usd_change_emoji = "🟢" if usd_change > 0 else "🔴" if usd_change < 0 else "⚪"
    eur_change_emoji = "🟢" if eur_change > 0 else "🔴" if eur_change < 0 else "⚪"
    cny_change_emoji = "🟢" if cny_change > 0 else "🔴" if cny_change < 0 else "⚪"
    
    greeting = get_random_greeting()
    
    message = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"     🏦 <b>ЦЕНТРАЛЬНЫЙ БАНК РФ</b>     \n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"{greeting}\n\n"
        
        f"📅 <b>{date_str}</b>\n"
        f"⏰ <b>{datetime.now().strftime('%H:%M')}</b> МСК\n\n"
        
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"     💵 <b>ОФИЦИАЛЬНЫЕ КУРСЫ</b>     \n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"┌─────────────────────────┐\n"
        
        f"│ <b>🇺🇸 ДОЛЛАР США</b>         │\n"
        f"│ <b>{rates.get('USD', 0):.4f}</b> ₽ {usd_trend}          │\n"
        f"│ {usd_change_emoji} Изменение: {usd_change_str}   │\n\n"
        
        f"│ <b>🇪🇺 ЕВРО</b>                │\n"
        f"│ <b>{rates.get('EUR', 0):.4f}</b> ₽ {eur_trend}          │\n"
        f"│ {eur_change_emoji} Изменение: {eur_change_str}   │\n\n"
        
        f"│ <b>🇨🇳 КИТАЙСКИЙ ЮАНЬ</b>     │\n"
        f"│ <b>{rates.get('CNY', 0):.4f}</b> ₽ {cny_trend}          │\n"
        f"│ {cny_change_emoji} Изменение: {cny_change_str}   │\n"
        
        f"└─────────────────────────┘\n\n"
        
        f"📊 <b>ДИНАМИКА</b>\n"
        f"📈 Рост | 📉 Падение | ➖ Без изменений\n\n"
        
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"     💎 NT SHIPPING CO     \n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"💬 Прокомментировать"
    )
    
    return message

def create_rates_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(
            text="🏦 ЦБ РФ",
            url="https://cbr.ru/"
        ),
        InlineKeyboardButton(
            text="📈 Графики",
            url="https://www.cbr.ru/currency_base/dynamics/"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="💎 Наш сайт",
            url="https://nt-shipping.ru/"
        ),
        InlineKeyboardButton(
            text="👨‍💻 Разработчик",
            url="https://t.me/fuckForensics"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data="refresh_rates"
        )
    )
    return keyboard

def create_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(
            text="🖼 Настроить фото",
            callback_data="setup_photo"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📸 Отправить тест с фото",
            callback_data="test_photo"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="❌ Отключить фото",
            callback_data="disable_photo"
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="📊 Проверить фото",
            callback_data="check_photo"
        )
    )
    return keyboard

async def send_rates_with_photo(chat_id: str, message_text: str, keyboard: InlineKeyboardMarkup):
    try:
        if photo_settings['use_photo']:
            if photo_settings.get('photo_file_id'):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_settings['photo_file_id'],
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=types.ParseMode.HTML
                )
            elif photo_settings.get('photo_path') and os.path.exists(photo_settings['photo_path']):
                with open(photo_settings['photo_path'], 'rb') as photo:
                    sent_message = await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=message_text,
                        reply_markup=keyboard,
                        parse_mode=types.ParseMode.HTML
                    )
                    photo_settings['photo_file_id'] = sent_message.photo[-1].file_id
                    save_photo_settings()
            elif photo_settings.get('photo_url'):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_settings['photo_url'],
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=types.ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=types.ParseMode.HTML
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode=types.ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке с фото: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=message_text + "\n\n⚠️ Ошибка при загрузке фото",
            reply_markup=keyboard,
            parse_mode=types.ParseMode.HTML
        )

async def send_daily_rates():
    logger.info("Отправка ежедневных курсов валют...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        try:
            save_previous_rates(rates)
            await send_rates_with_photo(CHAT_ID, message_text, keyboard)
            logger.info("Курсы валют успешно отправлены")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
    else:
        logger.error("Не удалось получить курсы валют")
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="❌ <b>Не удалось получить курсы валют сегодня.</b>\nПроверьте соединение с сайтом ЦБ РФ.",
                parse_mode=types.ParseMode.HTML
            )
        except:
            pass

@dp.callback_query_handler(lambda c: c.data == 'refresh_rates')
async def process_refresh_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="🔄 Обновляю курсы...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        try:
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode=types.ParseMode.HTML
            )
            await bot.answer_callback_query(callback_query.id, text="✅ Курсы обновлены!")
        except Exception as e:
            await bot.answer_callback_query(callback_query.id, text="❌ Ошибка обновления")
    else:
        await bot.answer_callback_query(callback_query.id, text="❌ Не удалось получить курсы")

@dp.callback_query_handler(lambda c: c.data == 'setup_photo')
async def process_setup_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "📸 <b>НАСТРОЙКА ФОТО</b>\n\n"
        "Отправьте фото одним из способов:\n\n"
        "1️⃣ <b>Загрузите фото файлом</b> - просто отправьте фото\n"
        "2️⃣ <b>Укажите путь к файлу</b> - отправьте /set_photo_path /путь/к/фото.jpg\n"
        "3️⃣ <b>Укажите URL фото</b> - отправьте /set_photo_url https://example.com/photo.jpg\n\n"
        "После отправки фото бот запомнит его и будет использовать при рассылке.",
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'test_photo')
async def process_test_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📸 Отправляю тестовое сообщение...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        await send_rates_with_photo(callback_query.from_user.id, message_text, keyboard)
        await bot.send_message(
            callback_query.from_user.id,
            "✅ Тестовое сообщение отправлено!",
            parse_mode=types.ParseMode.HTML
        )
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Не удалось получить курсы валют",
            parse_mode=types.ParseMode.HTML
        )

@dp.callback_query_handler(lambda c: c.data == 'disable_photo')
async def process_disable_photo(callback_query: types.CallbackQuery):
    photo_settings['use_photo'] = False
    save_photo_settings()
    await bot.answer_callback_query(callback_query.id, text="✅ Фото отключено")
    await bot.send_message(
        callback_query.from_user.id,
        "✅ Фото отключено. Теперь сообщения будут отправляться без фото.",
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'check_photo')
async def process_check_photo(callback_query: types.CallbackQuery):
    status = "🟢 Включено" if photo_settings['use_photo'] else "🔴 Выключено"
    photo_type = ""
    if photo_settings.get('photo_file_id'):
        photo_type = "📸 (по file_id)"
    elif photo_settings.get('photo_path'):
        photo_type = f"📁 (путь: {photo_settings['photo_path']})"
    elif photo_settings.get('photo_url'):
        photo_type = f"🌐 (URL: {photo_settings['photo_url'][:50]}...)"
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"📸 <b>СТАТУС ФОТО</b>\n\n"
        f"Статус: {status}\n"
        f"{photo_type}\n\n"
        f"Используйте /admin для настройки",
        parse_mode=types.ParseMode.HTML
    )

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    welcome_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "     💎 <b>NT SHIPPING CO</b>     \n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "👋 <b>Добро пожаловать!</b>\n\n"
        
        "Я бот для отслеживания официальных курсов валют\n"
        "<b>Центрального Банка Российской Федерации</b>\n\n"
        
        "📊 <b>МОИ ВОЗМОЖНОСТИ:</b>\n"
        "• Ежедневная рассылка в 8:00 МСК\n"
        "• 📈 Тренды и динамика изменений\n"
        "• 🎨 Красивый интерфейс\n"
        "• 📸 Поддержка фото\n"
        "• 🔄 Мгновенное обновление\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "     <b>ДОСТУПНЫЕ КОМАНДЫ</b>     \n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "💰 /rates - Получить курсы сейчас\n"
        "📈 /trends - История изменений\n"
        "ℹ️ /help - Подробная инструкция\n"
        "👤 /about - О боте\n"
        "⚙️ /admin - Настройки (для админов)\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "     💎 NT SHIPPING CO     \n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="💰 Курсы", callback_data="refresh_rates"),
        InlineKeyboardButton(text="📈 Графики", url="https://www.cbr.ru/currency_base/dynamics/")
    )
    
    await message.reply(welcome_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard)

@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет доступа к этой команде.")
        return
    
    admin_text = (
        "⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "📸 <b>НАСТРОЙКА ФОТО</b>\n"
        "Здесь вы можете настроить отображение фото\n"
        "при отправке курсов валют.\n\n"
        "Текущий статус: " + ("🟢 Включено" if photo_settings['use_photo'] else "🔴 Выключено")
    )
    
    await message.reply(admin_text, parse_mode=types.ParseMode.HTML, reply_markup=create_admin_keyboard())

@dp.message_handler(commands=['set_photo_path'])
async def cmd_set_photo_path(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    path = message.get_args().strip()
    if not path:
        await message.reply("❌ Укажите путь к файлу: /set_photo_path /путь/к/фото.jpg")
        return
    
    if os.path.exists(path):
        photo_settings['use_photo'] = True
        photo_settings['photo_path'] = path
        photo_settings['photo_url'] = ''
        photo_settings['photo_file_id'] = ''
        save_photo_settings()
        await message.reply(f"✅ Путь к фото сохранен: {path}\nФото будет использоваться при рассылке.")
    else:
        await message.reply("❌ Файл не найден по указанному пути.")

@dp.message_handler(commands=['set_photo_url'])
async def cmd_set_photo_url(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    url = message.get_args().strip()
    if not url:
        await message.reply("❌ Укажите URL фото: /set_photo_url https://example.com/photo.jpg")
        return
    
    photo_settings['use_photo'] = True
    photo_settings['photo_url'] = url
    photo_settings['photo_path'] = ''
    photo_settings['photo_file_id'] = ''
    save_photo_settings()
    await message.reply(f"✅ URL фото сохранен\nФото будет использоваться при рассылке.")

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        photo_settings['use_photo'] = True
        photo_settings['photo_file_id'] = message.photo[-1].file_id
        photo_settings['photo_path'] = ''
        photo_settings['photo_url'] = ''
        save_photo_settings()
        await message.reply("✅ Фото сохранено! Теперь оно будет использоваться при рассылке курсов.")
    
    if message.caption and '/rates' in message.caption:
        await message.reply("🔄 <i>Получаю курсы валют для вашего фото...</i>", parse_mode=types.ParseMode.HTML)
        
        previous_rates = load_previous_rates()
        rates = await fetch_exchange_rates()
        
        if rates:
            save_previous_rates(rates)
            
            current_date = datetime.now()
            message_text = format_rates_message(rates, previous_rates, current_date)
            keyboard = create_rates_keyboard()
            
            await message.reply_photo(
                photo=message.photo[-1].file_id,
                caption=message_text,
                reply_markup=keyboard,
                parse_mode=types.ParseMode.HTML
            )

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = (
        "📚 <b>ПОДРОБНАЯ ИНСТРУКЦИЯ</b>\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔹 <b>ДОБАВЛЕНИЕ В КАНАЛ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "1️⃣ Откройте ваш канал\n"
        "2️⃣ Нажмите на название канала\n"
        "3️⃣ Выберите «Управление каналом»\n"
        "4️⃣ Нажмите «Администраторы»\n"
        "5️⃣ «Добавить администратора»\n"
        "6️⃣ Найдите @ваш_бот\n"
        "7️⃣ Отметьте ✓ «Отправлять сообщения»\n"
        "8️⃣ Нажмите «Сохранить»\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔹 <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "💰 /rates - Получить курсы\n"
        "📈 /trends - История изменений\n"
        "ℹ️ /help - Эта инструкция\n"
        "👤 /about - О боте\n"
        "⚙️ /admin - Настройки (админ)\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔹 <b>ЗНАЧЕНИЯ СМАЙЛИКОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "📈 <b>Рост</b> - курс вырос\n"
        "📉 <b>Падение</b> - курс упал\n"
        "➖ <b>Стабильно</b> - без изменений\n"
        "🔄 <b>Нет данных</b> - первое получение\n"
        "🟢 <b>Рост</b> - положительная динамика\n"
        "🔴 <b>Падение</b> - отрицательная динамика\n"
        "⚪ <b>Стабильно</b> - без изменений\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔹 <b>КОНТАКТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "👨‍💻 Разработчик: @fuckForensics\n"
        "🌐 Сайт: https://nt-shipping.ru/\n"
        "📊 Канал: @nt_shippingCo\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="👨‍💻 Разработчик", url="https://t.me/fuckForensics"),
        InlineKeyboardButton(text="🌐 Сайт", url="https://nt-shipping.ru/")
    )
    
    await message.reply(help_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    about_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "     💎 <b>NT SHIPPING CO</b>     \n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "🤖 <b>О БОТЕ</b>\n\n"
        
        "📌 <b>Название:</b> Currency Rate Bot\n"
        "📌 <b>Версия:</b> 3.0.0\n"
        "📌 <b>Источник:</b> Центральный Банк РФ\n"
        "📌 <b>Обновление:</b> Ежедневно в 8:00 МСК\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>ФУНКЦИОНАЛ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "• ✅ Автоматическая рассылка\n"
        "• 📈 Отображение трендов\n"
        "• 📉 Сравнение с прошлым днём\n"
        "• 🎨 Красивый интерфейс\n"
        "• 📸 Поддержка фото\n"
        "• 🔄 Интерактивные кнопки\n"
        "• 🌐 Ссылки на графики\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>ИНФОРМАЦИЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "👨‍💻 <b>Разработчик:</b> @fuckForensics\n"
        "📅 <b>Создан:</b> 01.03.2026\n"
        "🌐 <b>Сайт:</b> https://nt-shipping.ru/\n"
        "📊 <b>Канал:</b> @nt_shippingCo\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "     💎 NT SHIPPING CO     \n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="🌐 Сайт", url="https://nt-shipping.ru/"),
        InlineKeyboardButton(text="📊 Канал", url="https://t.me/nt_shippingCo")
    )
    
    await message.reply(about_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard)

@dp.message_handler(commands=['trends'])
async def cmd_trends(message: types.Message):
    previous_rates = load_previous_rates()
    current_rates = await fetch_exchange_rates()
    
    if current_rates and previous_rates:
        trends_text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "     📊 <b>ИСТОРИЯ ИЗМЕНЕНИЙ</b>     \n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for currency in ['USD', 'EUR', 'CNY']:
            current = current_rates.get(currency, 0)
            previous = previous_rates.get(currency, 0)
            change = current - previous
            percent = (change / previous * 100) if previous != 0 else 0
            
            emoji = get_trend_emoji(current, previous)
            change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
            
            currency_symbols = {
                'USD': '🇺🇸 ДОЛЛАР США',
                'EUR': '🇪🇺 ЕВРО',
                'CNY': '🇨🇳 КИТАЙСКИЙ ЮАНЬ'
            }
            
            trends_text += (
                f"<b>{currency_symbols[currency]}</b>\n"
                f"┌─────────────────────┐\n"
                f"│ {emoji} Текущий: {current:.4f} ₽\n"
                f"│ 📊 Прошлый: {previous:.4f} ₽\n"
                f"│ {change_emoji} Изменение: {change:+.4f} ₽\n"
                f"│ 📈 Процент: {percent:+.2f}%\n"
                f"└─────────────────────┘\n\n"
            )
        
        trends_text += "━━━━━━━━━━━━━━━━━━━━━━\n     💎 NT SHIPPING CO     \n━━━━━━━━━━━━━━━━━━━━━━"
        
        await message.reply(trends_text, parse_mode=types.ParseMode.HTML)
    else:
        await message.reply("❌ Недостаточно данных для отображения трендов.")

@dp.message_handler(commands=['rates'])
async def cmd_rates(message: types.Message):
    await message.reply("🔄 <i>Получаю актуальные курсы валют...</i>", parse_mode=types.ParseMode.HTML)
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        save_previous_rates(rates)
        
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        await send_rates_with_photo(message.chat.id, message_text, keyboard)
    else:
        await message.reply(
            "❌ <b>Не удалось получить курсы валют.</b>\nПопробуйте позже или проверьте соединение.",
            parse_mode=types.ParseMode.HTML
        )

@dp.message_handler(commands=['settime'])
async def cmd_settime(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет прав на выполнение этой команды.")
        return
    
    args = message.get_args()
    if not args:
        await message.reply(
            "❌ Укажите время в формате ЧЧ:ММ\n"
            "Пример: /settime 09:30"
        )
        return
    
    try:
        hour, minute = map(int, args.split(':'))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            scheduler.reschedule_job(
                job_id='daily_rates',
                trigger='cron',
                hour=hour,
                minute=minute
            )
            await message.reply(
                f"✅ Время рассылки изменено на {hour:02d}:{minute:02d} МСК",
                parse_mode=types.ParseMode.HTML
            )
        else:
            await message.reply("❌ Неверный формат времени.")
    except:
        await message.reply("❌ Неверный формат. Используйте ЧЧ:ММ")

async def on_startup(dp):
    logger.info("🚀 Бот запускается...")
    
    load_photo_settings()
    previous_rates = load_previous_rates()
    if previous_rates:
        logger.info(f"📊 Загружены предыдущие курсы: {previous_rates}")
    
    if photo_settings['use_photo']:
        logger.info(f"📸 Режим фото: ВКЛЮЧЕН")
    
    scheduler.add_job(
        send_daily_rates,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_rates",
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ Планировщик запущен. Отправка каждый день в 8:00 МСК")
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "     ✅ <b>БОТ ЗАПУЩЕН</b>     \n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⏰ Рассылка: <b>8:00 МСК</b>\n"
                f"📊 Канал: <b>{CHAT_ID}</b>\n"
                f"📸 Фото: <b>{'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def on_shutdown(dp):
    logger.info("🛑 Бот останавливается...")
    scheduler.shutdown()
    await bot.close()

if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )