import asyncio
import logging
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree
from typing import Dict, Tuple
import pickle
import random
import json
from collections import deque

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
HISTORY_FILE = "rates_history.pkl"
STATS_FILE = "stats.pkl"

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

stats = {
    'total_requests': 0,
    'total_sent': 0,
    'last_update': None,
    'users_count': set(),
    'daily_stats': {},
    'weekly_avg': {}
}

rates_history = deque(maxlen=30)

def save_stats():
    try:
        stats['users_count'] = list(stats['users_count'])
        with open(STATS_FILE, 'wb') as f:
            pickle.dump(stats, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении статистики: {e}")

def load_stats():
    global stats
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'rb') as f:
                loaded = pickle.load(f)
                loaded['users_count'] = set(loaded['users_count'])
                stats.update(loaded)
    except Exception as e:
        logger.error(f"Ошибка при загрузке статистики: {e}")

def save_rates_history(rates: dict):
    try:
        rates_history.append({
            'date': datetime.now(),
            'rates': rates.copy()
        })
        with open(HISTORY_FILE, 'wb') as f:
            pickle.dump(list(rates_history), f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении истории: {e}")

def load_rates_history():
    global rates_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'rb') as f:
                data = pickle.load(f)
                rates_history = deque(data, maxlen=30)
    except Exception as e:
        logger.error(f"Ошибка при загрузке истории: {e}")

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

def get_trend_arrow(current: float, previous: float) -> str:
    if previous == 0:
        return "○"
    if current > previous:
        return "▲"
    elif current < previous:
        return "▼"
    else:
        return "■"

def format_change(change: float) -> str:
    if change > 0:
        return f"+{change:.4f}"
    elif change < 0:
        return f"{change:.4f}"
    else:
        return "0.0000"

def get_change_emoji(change: float) -> str:
    if change > 0:
        return "🟢"
    elif change < 0:
        return "🔴"
    else:
        return "⚪"

def get_market_status(rates: dict, previous: dict) -> dict:
    usd_change = rates.get('USD', 0) - previous.get('USD', 0)
    eur_change = rates.get('EUR', 0) - previous.get('EUR', 0)
    cny_change = rates.get('CNY', 0) - previous.get('CNY', 0)
    
    up_count = sum(1 for x in [usd_change, eur_change, cny_change] if x > 0)
    down_count = sum(1 for x in [usd_change, eur_change, cny_change] if x < 0)
    
    if up_count == 3:
        return {"status": "🚀 ВСЕ РАСТЕТ", "desc": "Все валюты дорожают"}
    elif down_count == 3:
        return {"status": "📉 ВСЕ ПАДАЕТ", "desc": "Все валюты дешевеют"}
    elif up_count > down_count:
        return {"status": "📊 БОЛЬШЕ РОСТА", "desc": "Преимущественно рост"}
    elif down_count > up_count:
        return {"status": "📊 БОЛЬШЕ ПАДЕНИЯ", "desc": "Преимущественно падение"}
    else:
        return {"status": "⚖️ СМЕШАННО", "desc": "Разнонаправленное движение"}

def get_random_greeting():
    morning_greetings = [
        "✨ ДОБРОЕ УТРО!",
        "🌟 ПРЕКРАСНОГО УТРА!",
        "☀️ С ДОБРЫМ УТРОМ!",
        "💫 НОВОГО ДНЯ!",
        "🌅 ХОРОШЕГО НАЧАЛА!",
        "⭐ УДАЧНОГО ДНЯ!",
        "🎯 ПРОДУКТИВНОГО УТРА!",
        "🚀 ВЗЛЕТАЙ!"
    ]
    return random.choice(morning_greetings)

def get_weather_emoji():
    weather = ["☀️", "🌤️", "⛅", "🌥️", "☁️", "🌦️", "🌧️", "⛈️", "❄️", "🌪️"]
    return random.choice(weather)

def get_motivation():
    messages = [
        "💎 Каждая копейка - шаг к миллиону!",
        "📈 Инвестируй с умом!",
        "💰 Деньги любят счет!",
        "🎯 Будь в тренде!",
        "⭐ Следи за курсом!",
        "🚀 К новым высотам!",
        "💫 Твой капитал в порядке!",
        "🌟 Зарабатывай больше!"
    ]
    return random.choice(messages)

def create_progress_bar(value: float, min_val: float, max_val: float, length: int = 8) -> str:
    if max_val == min_val:
        return "████████"
    
    position = int((value - min_val) / (max_val - min_val) * length)
    position = max(0, min(position, length))
    
    bar = "█" * position + "░" * (length - position)
    return bar

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

def format_rates_message_mobile(rates: dict, previous_rates: dict, date: datetime) -> str:
    date_str = date.strftime("%d.%m.%Y")
    time_str = date.strftime("%H:%M")
    
    usd_change = rates.get('USD', 0) - previous_rates.get('USD', 0)
    eur_change = rates.get('EUR', 0) - previous_rates.get('EUR', 0)
    cny_change = rates.get('CNY', 0) - previous_rates.get('CNY', 0)
    
    usd_trend = get_trend_emoji(rates.get('USD', 0), previous_rates.get('USD', 0))
    eur_trend = get_trend_emoji(rates.get('EUR', 0), previous_rates.get('EUR', 0))
    cny_trend = get_trend_emoji(rates.get('CNY', 0), previous_rates.get('CNY', 0))
    
    usd_arrow = get_trend_arrow(rates.get('USD', 0), previous_rates.get('USD', 0))
    eur_arrow = get_trend_arrow(rates.get('EUR', 0), previous_rates.get('EUR', 0))
    cny_arrow = get_trend_arrow(rates.get('CNY', 0), previous_rates.get('CNY', 0))
    
    market = get_market_status(rates, previous_rates)
    motivation = get_motivation()
    
    message = f"""
╔════════════════════╗
║  💎NT SHIPPING CO💎 ║
╠════════════════════╣
║ {get_weather_emoji()} {date_str} {time_str} ║
╠════════════════════╣
║ {get_random_greeting()} ║
╠════════════════════╣
║  📊 КУРСЫ ЦБ РФ   ║
╠════════════════════╣
║🇺🇸 <b>USD</b> {usd_trend}{usd_arrow}    ║
║<code>{rates.get('USD', 0):.4f}</code> ₽       ║
║{get_change_emoji(usd_change)} {format_change(usd_change)}║
║{create_progress_bar(rates.get('USD', 0), 70, 100)}║
║                    ║
║🇪🇺 <b>EUR</b> {eur_trend}{eur_arrow}    ║
║<code>{rates.get('EUR', 0):.4f}</code> ₽       ║
║{get_change_emoji(eur_change)} {format_change(eur_change)}║
║{create_progress_bar(rates.get('EUR', 0), 80, 110)}║
║                    ║
║🇨🇳 <b>CNY</b> {cny_trend}{cny_arrow}    ║
║<code>{rates.get('CNY', 0):.4f}</code> ₽       ║
║{get_change_emoji(cny_change)} {format_change(cny_change)}║
║{create_progress_bar(rates.get('CNY', 0), 10, 15)}║
╠════════════════════╣
║{market['status']}   ║
║{market['desc']}     ║
╠════════════════════╣
║💬 {motivation}      ║
╠════════════════════╣
║    💎NT SHIPPING💎  ║
╚════════════════════╝
"""
    return message

def format_trends_message_mobile(history: deque) -> str:
    if not history:
        return "❌ Нет данных"
    
    recent = list(history)[-5:]
    
    message = """
╔════════════════════╗
║   📊 ИСТОРИЯ      ║
╠════════════════════╣
"""
    
    for item in recent:
        date = item['date'].strftime("%d.%m")
        usd = item['rates'].get('USD', 0)
        eur = item['rates'].get('EUR', 0)
        cny = item['rates'].get('CNY', 0)
        
        message += f"║{date} {usd:.2f}/{eur:.2f}/{cny:.2f}║\n"
    
    if len(recent) >= 2:
        first_usd = recent[0]['rates'].get('USD', 0)
        last_usd = recent[-1]['rates'].get('USD', 0)
        usd_trend = "📈" if last_usd > first_usd else "📉"
        
        message += f"""
╠════════════════════╣
║Тренд: USD {usd_trend} {last_usd-first_usd:+.2f}₽║
╚════════════════════╝
"""
    return message

def create_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="📸 НАСТРОИТЬ ФОТО", callback_data="setup_photo")
    )
    keyboard.add(
        InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="show_stats")
    )
    keyboard.add(
        InlineKeyboardButton(text="📈 ТЕСТ С ФОТО", callback_data="test_photo")
    )
    keyboard.add(
        InlineKeyboardButton(text="❌ ОТКЛЮЧИТЬ ФОТО", callback_data="disable_photo")
    )
    keyboard.add(
        InlineKeyboardButton(text="📋 ПРОВЕРИТЬ ФОТО", callback_data="check_photo")
    )
    return keyboard

async def send_rates_with_photo(chat_id: str, message_text: str):
    try:
        if photo_settings['use_photo']:
            if photo_settings.get('photo_file_id'):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_settings['photo_file_id'],
                    caption=message_text,
                    parse_mode=types.ParseMode.HTML
                )
            elif photo_settings.get('photo_path') and os.path.exists(photo_settings['photo_path']):
                with open(photo_settings['photo_path'], 'rb') as photo:
                    sent_message = await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=message_text,
                        parse_mode=types.ParseMode.HTML
                    )
                    photo_settings['photo_file_id'] = sent_message.photo[-1].file_id
                    save_photo_settings()
            elif photo_settings.get('photo_url'):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_settings['photo_url'],
                    caption=message_text,
                    parse_mode=types.ParseMode.HTML
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode=types.ParseMode.HTML
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=types.ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке с фото: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=message_text + "\n\n⚠️ Ошибка фото",
            parse_mode=types.ParseMode.HTML
        )

async def send_daily_rates():
    logger.info("📨 Отправка ежедневных курсов...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message_mobile(rates, previous_rates, current_date)
        
        try:
            save_previous_rates(rates)
            save_rates_history(rates)
            
            stats['total_sent'] += 1
            stats['last_update'] = current_date
            save_stats()
            
            await send_rates_with_photo(CHAT_ID, message_text)
            logger.info("✅ Курсы успешно отправлены")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке: {e}")
    else:
        logger.error("❌ Не удалось получить курсы")
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="❌ <b>НЕ УДАЛОСЬ ПОЛУЧИТЬ КУРСЫ</b>\nПроверьте соединение",
                parse_mode=types.ParseMode.HTML
            )
        except:
            pass

@dp.callback_query_handler(lambda c: c.data == 'setup_photo')
async def process_setup_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        """
📸 НАСТРОЙКА ФОТО

1️⃣ Отправьте фото боту
2️⃣ /set_photo_path /путь/к/фото.jpg
3️⃣ /set_photo_url https://example.com/photo.jpg
        """,
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'show_stats')
async def process_stats_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📊 Статистика")
    
    stats_text = f"""
╔════════════════════╗
║   📊 СТАТИСТИКА   ║
╠════════════════════╣
║👥 {len(stats['users_count'])} польз.     ║
║📨 {stats['total_sent']} отправок  ║
║🔄 {stats['total_requests']} запросов ║
║📸 {'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}          ║
╚════════════════════╝
"""
    
    await bot.send_message(
        callback_query.from_user.id,
        stats_text,
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'test_photo')
async def process_test_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📸 Тест...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message_mobile(rates, previous_rates, current_date)
        
        await send_rates_with_photo(callback_query.from_user.id, message_text)
        await bot.send_message(
            callback_query.from_user.id,
            "✅ Тест отправлен!",
            parse_mode=types.ParseMode.HTML
        )
    else:
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Ошибка получения курсов",
            parse_mode=types.ParseMode.HTML
        )

@dp.callback_query_handler(lambda c: c.data == 'disable_photo')
async def process_disable_photo(callback_query: types.CallbackQuery):
    photo_settings['use_photo'] = False
    save_photo_settings()
    await bot.answer_callback_query(callback_query.id, text="✅ Фото отключено")
    await bot.send_message(
        callback_query.from_user.id,
        "✅ Фото отключено",
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'check_photo')
async def process_check_photo(callback_query: types.CallbackQuery):
    status = "🟢 ВКЛ" if photo_settings['use_photo'] else "🔴 ВЫКЛ"
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"""
📸 СТАТУС ФОТО

Статус: {status}
/admin для настройки
        """,
        parse_mode=types.ParseMode.HTML
    )

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    
    welcome_text = """
╔════════════════════╗
║  💎NT SHIPPING💎   ║
╠════════════════════╣
║   👋 ДОБРО          ║
║   ПОЖАЛОВАТЬ!      ║
╠════════════════════╣
║📊 Курсы ЦБ РФ      ║
║💵 USD/EUR/CNY      ║
╠════════════════════╣
║⚡ ВОЗМОЖНОСТИ:      ║
║✅ Рассылка 8:00    ║
║✅ Тренды           ║
║✅ История          ║
║✅ Аналитика        ║
╠════════════════════╣
║📋 КОМАНДЫ:         ║
║💰 /rates - курсы   ║
║📈 /trends - история║
║📊 /analytics - анал║
║ℹ️ /help - помощь   ║
║👤 /about - о боте  ║
╚════════════════════╝
    """
    
    await message.reply(welcome_text, parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ Нет доступа")
        return
    
    admin_text = f"""
╔════════════════════╗
║    ⚙️ АДМИН       ║
╠════════════════════╣
║📸 Фото: {'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}║
║👥 {len(stats['users_count'])} польз.     ║
║📨 {stats['total_sent']} отправок  ║
╚════════════════════╝
    """
    
    await message.reply(admin_text, parse_mode=types.ParseMode.HTML, reply_markup=create_admin_keyboard())

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = """
╔════════════════════╗
║    📚 ПОМОЩЬ      ║
╠════════════════════╣
║📌 ДОБАВЛЕНИЕ:     ║
║1. Настройки канала║
║2. Администраторы  ║
║3. Добавить бота   ║
║4. Разрешить отправ║
╠════════════════════╣
║📋 КОМАНДЫ:        ║
║💰 /rates - курсы  ║
║📈 /trends - истор ║
║📊 /analytics - ана║
║ℹ️ /help - помощь  ║
╠════════════════════╣
║😊 СМАЙЛИКИ:       ║
║📈 - рост         ║
║📉 - падение      ║
║🟢 - позитив      ║
║🔴 - негатив      ║
╚════════════════════╝
    """
    
    await message.reply(help_text, parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    about_text = """
╔════════════════════╗
║  💎NT SHIPPING💎   ║
╠════════════════════╣
║🤖 О БОТЕ          ║
║📌 v4.0            ║
║📌 ЦБ РФ           ║
║📌 8:00 МСК        ║
╠════════════════════╣
║📊 ФУНКЦИИ:        ║
║✅ Авторассылка    ║
║✅ Тренды          ║
║✅ История         ║
║✅ Аналитика       ║
╠════════════════════╣
║👨‍💻 @fuckForensics ║
║🌐 nt-shipping.ru  ║
╚════════════════════╝
    """
    
    await message.reply(about_text, parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['rates'])
async def cmd_rates(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    
    await message.reply("🔄 Получаю...", parse_mode=types.ParseMode.HTML)
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        save_previous_rates(rates)
        save_rates_history(rates)
        
        current_date = datetime.now()
        message_text = format_rates_message_mobile(rates, previous_rates, current_date)
        
        await send_rates_with_photo(message.chat.id, message_text)
    else:
        await message.reply("❌ Ошибка получения", parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['trends'])
async def cmd_trends(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    
    if rates_history:
        message_text = format_trends_message_mobile(rates_history)
        await message.reply(message_text, parse_mode=types.ParseMode.HTML)
    else:
        await message.reply("❌ Нет данных")

@dp.message_handler(commands=['analytics'])
async def cmd_analytics(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    
    if not rates_history or len(rates_history) < 2:
        await message.reply("❌ Мало данных")
        return
    
    recent = list(rates_history)[-5:]
    
    usd_values = [item['rates'].get('USD', 0) for item in recent]
    eur_values = [item['rates'].get('EUR', 0) for item in recent]
    cny_values = [item['rates'].get('CNY', 0) for item in recent]
    
    analytics_text = f"""
╔════════════════════╗
║   📊 АНАЛИТИКА    ║
╠════════════════════╣
║🇺🇸 USD            ║
║📊 {usd_values[-1]:.2f} ₽        ║
║📈 ср:{sum(usd_values)/5:.2f}₽   ║
║                    ║
║🇪🇺 EUR            ║
║📊 {eur_values[-1]:.2f} ₽        ║
║📈 ср:{sum(eur_values)/5:.2f}₽   ║
║                    ║
║🇨🇳 CNY            ║
║📊 {cny_values[-1]:.2f} ₽        ║
║📈 ср:{sum(cny_values)/5:.2f}₽   ║
╚════════════════════╝
    """
    
    await message.reply(analytics_text, parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['set_photo_path'])
async def cmd_set_photo_path(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    path = message.get_args().strip()
    if not path:
        await message.reply("❌ Укажите путь")
        return
    
    if os.path.exists(path):
        photo_settings['use_photo'] = True
        photo_settings['photo_path'] = path
        photo_settings['photo_url'] = ''
        photo_settings['photo_file_id'] = ''
        save_photo_settings()
        await message.reply(f"✅ Путь сохранен")
    else:
        await message.reply("❌ Файл не найден")

@dp.message_handler(commands=['set_photo_url'])
async def cmd_set_photo_url(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    url = message.get_args().strip()
    if not url:
        await message.reply("❌ Укажите URL")
        return
    
    photo_settings['use_photo'] = True
    photo_settings['photo_url'] = url
    photo_settings['photo_path'] = ''
    photo_settings['photo_file_id'] = ''
    save_photo_settings()
    await message.reply(f"✅ URL сохранен")

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        photo_settings['use_photo'] = True
        photo_settings['photo_file_id'] = message.photo[-1].file_id
        photo_settings['photo_path'] = ''
        photo_settings['photo_url'] = ''
        save_photo_settings()
        await message.reply("✅ Фото сохранено!")
    
    if message.caption and '/rates' in message.caption:
        if str(message.chat.id).startswith('-100'):
            return
        
        await message.reply("🔄 Получаю...", parse_mode=types.ParseMode.HTML)
        
        previous_rates = load_previous_rates()
        rates = await fetch_exchange_rates()
        
        if rates:
            save_previous_rates(rates)
            current_date = datetime.now()
            message_text = format_rates_message_mobile(rates, previous_rates, current_date)
            
            await message.reply_photo(
                photo=message.photo[-1].file_id,
                caption=message_text,
                parse_mode=types.ParseMode.HTML
            )

async def on_startup(dp):
    logger.info("🚀 ЗАПУСК...")
    
    load_photo_settings()
    load_rates_history()
    load_stats()
    
    logger.info(f"📊 История: {len(rates_history)}")
    logger.info(f"👥 Пользователей: {len(stats['users_count'])}")
    
    scheduler.add_job(
        send_daily_rates,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_rates",
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ Планировщик: 8:00 МСК")
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"""
╔════════════════════╗
║   ✅ ЗАПУЩЕН      ║
╠════════════════════╣
║⏰ 8:00 МСК        ║
║📊 {CHAT_ID}       ║
║📸 {'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}║
║👥 {len(stats['users_count'])} польз.║
╚════════════════════╝
                """,
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")

async def on_shutdown(dp):
    logger.info("🛑 ОСТАНОВКА...")
    save_stats()
    scheduler.shutdown()
    await bot.close()

if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )