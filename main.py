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

def get_trend_color(current: float, previous: float) -> str:
    if previous == 0:
        return "#808080"
    if current > previous:
        return "#00FF00"
    elif current < previous:
        return "#FF0000"
    else:
        return "#FFFF00"

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
        return {"status": "🚀 РЫНОК РАСТЕТ", "color": "🟢", "desc": "Все валюты дорожают"}
    elif down_count == 3:
        return {"status": "📉 РЫНОК ПАДАЕТ", "color": "🔴", "desc": "Все валюты дешевеют"}
    elif up_count > down_count:
        return {"status": "📊 СМЕШАННАЯ ДИНАМИКА", "color": "🟡", "desc": "Преимущественно рост"}
    elif down_count > up_count:
        return {"status": "📊 СМЕШАННАЯ ДИНАМИКА", "color": "🟠", "desc": "Преимущественно падение"}
    else:
        return {"status": "⚖️ СТАБИЛЬНОСТЬ", "color": "⚪", "desc": "Разнонаправленное движение"}

def get_random_greeting():
    morning_greetings = [
        "✨ ДОБРОЕ УТРО! ✨",
        "🌟 ПРЕКРАСНОГО УТРА! 🌟",
        "☀️ С ДОБРЫМ УТРОМ! ☀️",
        "💫 НОВОГО ДНЯ! 💫",
        "🌅 ХОРОШЕГО НАЧАЛА! 🌅",
        "⭐ УДАЧНОГО ДНЯ! ⭐",
        "🎯 ПРОДУКТИВНОГО УТРА! 🎯",
        "🚀 ВЗЛЕТАЙ С НАМИ! 🚀"
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
        "🎯 Финансовая грамотность - ключ к успеху!",
        "⭐ Следи за курсом, будь в тренде!",
        "🚀 К новым финансовым высотам!",
        "💫 Твой капитал в надежных руках!",
        "🌟 Зарабатывай больше с нами!"
    ]
    return random.choice(messages)

def create_progress_bar(value: float, min_val: float, max_val: float, length: int = 10) -> str:
    if max_val == min_val:
        return "█" * length + "⚪"
    
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

def format_rates_message(rates: dict, previous_rates: dict, date: datetime) -> str:
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
╔════════════════════════════════╗
║     💎 <b>NT SHIPPING CO</b> 💎     ║
╠════════════════════════════════╣
║  {get_weather_emoji()} <b>{date_str}</b>  🕐 {time_str} МСК  ║
╠════════════════════════════════╣
║        {get_random_greeting()}        ║
╠════════════════════════════════╣
║  📊 <b>КУРСЫ ЦБ РФ</b>  {market['color']}  ║
╠════════════════════════════════╣
║                                ║
║  🇺🇸 <b>ДОЛЛАР США</b>              ║
║  <code>{rates.get('USD', 0):>10.4f}</code> ₽ {usd_trend} {usd_arrow}   ║
║  {get_change_emoji(usd_change)} Изм: {format_change(usd_change)}    ║
║  {create_progress_bar(rates.get('USD', 0), 70, 100)}   ║
║                                ║
║  🇪🇺 <b>ЕВРО</b>                     ║
║  <code>{rates.get('EUR', 0):>10.4f}</code> ₽ {eur_trend} {eur_arrow}   ║
║  {get_change_emoji(eur_change)} Изм: {format_change(eur_change)}    ║
║  {create_progress_bar(rates.get('EUR', 0), 80, 110)}   ║
║                                ║
║  🇨🇳 <b>КИТАЙСКИЙ ЮАНЬ</b>          ║
║  <code>{rates.get('CNY', 0):>10.4f}</code> ₽ {cny_trend} {cny_arrow}   ║
║  {get_change_emoji(cny_change)} Изм: {format_change(cny_change)}    ║
║  {create_progress_bar(rates.get('CNY', 0), 10, 15)}   ║
║                                ║
╠════════════════════════════════╣
║  {market['status']}              ║
║  {market['desc']}                ║
╠════════════════════════════════╣
║  💬 <i>"{motivation}"</i>  ║
╠════════════════════════════════╣
║     💎 NT SHIPPING CO 💎       ║
╚════════════════════════════════╝
"""
    return message

def format_trends_message(history: deque) -> str:
    if not history:
        return "❌ Нет данных для анализа"
    
    recent = list(history)[-7:]
    
    message = """
╔════════════════════════════════╗
║    📊 <b>ИСТОРИЯ ЗА 7 ДНЕЙ</b>    ║
╠════════════════════════════════╣
"""
    
    message += "║ Дата     │ USD    │ EUR    │ CNY    ║\n"
    message += "╠════════════════════════════════╣\n"
    
    for item in recent:
        date = item['date'].strftime("%d.%m")
        usd = item['rates'].get('USD', 0)
        eur = item['rates'].get('EUR', 0)
        cny = item['rates'].get('CNY', 0)
        
        message += f"║ {date} │ {usd:.2f} │ {eur:.2f} │ {cny:.2f} ║\n"
    
    if len(recent) >= 2:
        first_usd = recent[0]['rates'].get('USD', 0)
        last_usd = recent[-1]['rates'].get('USD', 0)
        usd_trend = "📈" if last_usd > first_usd else "📉" if last_usd < first_usd else "➖"
        
        first_eur = recent[0]['rates'].get('EUR', 0)
        last_eur = recent[-1]['rates'].get('EUR', 0)
        eur_trend = "📈" if last_eur > first_eur else "📉" if last_eur < first_eur else "➖"
        
        first_cny = recent[0]['rates'].get('CNY', 0)
        last_cny = recent[-1]['rates'].get('CNY', 0)
        cny_trend = "📈" if last_cny > first_cny else "📉" if last_cny < first_cny else "➖"
        
        message += f"""
╠════════════════════════════════╣
║  <b>ТРЕНД ЗА НЕДЕЛЮ:</b>              ║
║  🇺🇸 USD: {usd_trend}  {last_usd-first_usd:+.2f} ₽      ║
║  🇪🇺 EUR: {eur_trend}  {last_eur-first_eur:+.2f} ₽      ║
║  🇨🇳 CNY: {cny_trend}  {last_cny-first_cny:+.2f} ₽      ║
"""
    
    message += """
╚════════════════════════════════╝
"""
    return message

def create_rates_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh_rates"),
        InlineKeyboardButton(text="📈 ГРАФИКИ", url="https://www.cbr.ru/currency_base/dynamics/")
    )
    keyboard.add(
        InlineKeyboardButton(text="📊 ИСТОРИЯ", callback_data="show_history"),
        InlineKeyboardButton(text="📉 ТРЕНДЫ", callback_data="show_trends")
    )
    keyboard.add(
        InlineKeyboardButton(text="💎 САЙТ", url="https://nt-shipping.ru/"),
        InlineKeyboardButton(text="👨‍💻 ПОДДЕРЖКА", url="https://t.me/fuckForensics")
    )
    return keyboard

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
    logger.info("📨 Отправка ежедневных курсов...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        try:
            save_previous_rates(rates)
            save_rates_history(rates)
            
            stats['total_sent'] += 1
            stats['last_update'] = current_date
            save_stats()
            
            await send_rates_with_photo(CHAT_ID, message_text, keyboard)
            logger.info("✅ Курсы успешно отправлены")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке: {e}")
    else:
        logger.error("❌ Не удалось получить курсы")
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="❌ <b>НЕ УДАЛОСЬ ПОЛУЧИТЬ КУРСЫ</b>\nПроверьте соединение с ЦБ РФ",
                parse_mode=types.ParseMode.HTML
            )
        except:
            pass

@dp.callback_query_handler(lambda c: c.data == 'refresh_rates')
async def process_refresh_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="🔄 Обновляю...")
    
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
            await bot.answer_callback_query(callback_query.id, text="✅ Обновлено!")
        except Exception as e:
            await bot.answer_callback_query(callback_query.id, text="❌ Ошибка")
    else:
        await bot.answer_callback_query(callback_query.id, text="❌ Ошибка получения")

@dp.callback_query_handler(lambda c: c.data == 'show_history')
async def process_history_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📊 Загружаю историю...")
    
    if rates_history:
        message_text = format_trends_message(rates_history)
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_rates")
        )
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode=types.ParseMode.HTML
        )
    else:
        await bot.answer_callback_query(callback_query.id, text="❌ Нет данных")

@dp.callback_query_handler(lambda c: c.data == 'show_trends')
async def process_trends_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📉 Анализирую тренды...")
    
    if rates_history and len(rates_history) >= 2:
        recent = list(rates_history)[-7:]
        
        usd_values = [item['rates'].get('USD', 0) for item in recent]
        eur_values = [item['rates'].get('EUR', 0) for item in recent]
        cny_values = [item['rates'].get('CNY', 0) for item in recent]
        
        usd_min, usd_max = min(usd_values), max(usd_values)
        eur_min, eur_max = min(eur_values), max(eur_values)
        cny_min, cny_max = min(cny_values), max(cny_values)
        
        trends_text = f"""
╔════════════════════════════════╗
║     📉 <b>АНАЛИЗ ТРЕНДОВ</b>      ║
╠════════════════════════════════╣

<b>🇺🇸 ДОЛЛАР США</b>
📊 Диапазон: {usd_min:.4f} - {usd_max:.4f} ₽
📈 Волатильность: {usd_max-usd_min:.4f} ₽
📊 Прогноз: {"Рост" if usd_values[-1] > usd_values[0] else "Падение"}

<b>🇪🇺 ЕВРО</b>
📊 Диапазон: {eur_min:.4f} - {eur_max:.4f} ₽
📈 Волатильность: {eur_max-eur_min:.4f} ₽
📊 Прогноз: {"Рост" if eur_values[-1] > eur_values[0] else "Падение"}

<b>🇨🇳 КИТАЙСКИЙ ЮАНЬ</b>
📊 Диапазон: {cny_min:.4f} - {cny_max:.4f} ₽
📈 Волатильность: {cny_max-cny_min:.4f} ₽
📊 Прогноз: {"Рост" if cny_values[-1] > cny_values[0] else "Падение"}

╚════════════════════════════════╝
"""
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_rates")
        )
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=trends_text,
            reply_markup=keyboard,
            parse_mode=types.ParseMode.HTML
        )
    else:
        await bot.answer_callback_query(callback_query.id, text="❌ Недостаточно данных")

@dp.callback_query_handler(lambda c: c.data == 'back_to_rates')
async def process_back_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="🔄 Возвращаюсь...")
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode=types.ParseMode.HTML
        )

@dp.callback_query_handler(lambda c: c.data == 'setup_photo')
async def process_setup_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        """
📸 <b>НАСТРОЙКА ФОТО</b>

<b>Способы загрузки:</b>

1️⃣ <b>Отправьте фото</b> - просто отправьте фото боту
2️⃣ <b>Укажите путь:</b>
   /set_photo_path /путь/к/фото.jpg
3️⃣ <b>Укажите URL:</b>
   /set_photo_url https://example.com/photo.jpg

После загрузки фото будет использоваться при рассылке!
        """,
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'show_stats')
async def process_stats_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📊 Загружаю статистику...")
    
    stats_text = f"""
╔════════════════════════════════╗
║     📊 <b>СТАТИСТИКА БОТА</b>     ║
╠════════════════════════════════╣
║                                ║
║  👥 Пользователей: {len(stats['users_count'])}         ║
║  📨 Отправлено: {stats['total_sent']}            ║
║  🔄 Запросов: {stats['total_requests']}           ║
║                                ║
║  📅 Последнее обновление:      ║
║  {stats['last_update'].strftime('%d.%m.%Y %H:%M') if stats['last_update'] else 'Нет'}  ║
║                                ║
║  📸 Режим фото: {"ВКЛ" if photo_settings['use_photo'] else "ВЫКЛ"}           ║
║                                ║
╚════════════════════════════════╝
"""
    
    await bot.send_message(
        callback_query.from_user.id,
        stats_text,
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'test_photo')
async def process_test_photo(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="📸 Отправляю тест...")
    
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
            "❌ Не удалось получить курсы",
            parse_mode=types.ParseMode.HTML
        )

@dp.callback_query_handler(lambda c: c.data == 'disable_photo')
async def process_disable_photo(callback_query: types.CallbackQuery):
    photo_settings['use_photo'] = False
    save_photo_settings()
    await bot.answer_callback_query(callback_query.id, text="✅ Фото отключено")
    await bot.send_message(
        callback_query.from_user.id,
        "✅ Фото отключено. Сообщения будут без фото.",
        parse_mode=types.ParseMode.HTML
    )

@dp.callback_query_handler(lambda c: c.data == 'check_photo')
async def process_check_photo(callback_query: types.CallbackQuery):
    status = "🟢 ВКЛ" if photo_settings['use_photo'] else "🔴 ВЫКЛ"
    photo_type = ""
    
    if photo_settings.get('photo_file_id'):
        photo_type = "📸 (из Telegram)"
    elif photo_settings.get('photo_path'):
        exists = "✅" if os.path.exists(photo_settings['photo_path']) else "❌"
        photo_type = f"📁 {exists} {photo_settings['photo_path']}"
    elif photo_settings.get('photo_url'):
        photo_type = f"🌐 {photo_settings['photo_url'][:50]}..."
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"""
📸 <b>СТАТУС ФОТО</b>

Статус: {status}
{photo_type}

Используйте /admin для настройки
        """,
        parse_mode=types.ParseMode.HTML
    )

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    
    welcome_text = """
╔════════════════════════════════╗
║     💎 <b>NT SHIPPING CO</b> 💎     ║
╠════════════════════════════════╣
║         👋 ДОБРО ПОЖАЛОВАТЬ!       ║
╠════════════════════════════════╣
║  📊 Официальные курсы валют     ║
║  💵 Центрального Банка РФ       ║
╠════════════════════════════════╣
║  <b>⚡ ВОЗМОЖНОСТИ:</b>               ║
║                                ║
║  ✅ Ежедневная рассылка в 8:00  ║
║  ✅ Красивое оформление         ║
║  ✅ Тренды и аналитика          ║
║  ✅ История за 30 дней          ║
║  ✅ Прогнозы и статистика       ║
║  ✅ Поддержка фото              ║
╠════════════════════════════════╣
║  <b>📋 КОМАНДЫ:</b>                  ║
║                                ║
║  💰 /rates - Курсы сейчас      ║
║  📈 /trends - История          ║
║  📊 /analytics - Аналитика     ║
║  ℹ️ /help - Инструкция         ║
║  👤 /about - О боте            ║
║  ⚙️ /admin - Настройки         ║
╠════════════════════════════════╣
║     💎 NT SHIPPING CO 💎       ║
╚════════════════════════════════╝
    """
    
    keyboard = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(text="💰 КУРСЫ", callback_data="refresh_rates"),
        InlineKeyboardButton(text="📊 АНАЛИТИКА", callback_data="show_trends")
    )
    
    await message.reply(welcome_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard)

@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет доступа к этой команде.")
        return
    
    admin_text = f"""
╔════════════════════════════════╗
║     ⚙️ <b>АДМИН-ПАНЕЛЬ</b>       ║
╠════════════════════════════════╣
║  📸 Фото: {'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}                ║
║  👥 Пользователей: {len(stats['users_count'])}        ║
║  📨 Отправлено: {stats['total_sent']}          ║
║  🔄 Запросов: {stats['total_requests']}         ║
╚════════════════════════════════╝
    """
    
    await message.reply(admin_text, parse_mode=types.ParseMode.HTML, reply_markup=create_admin_keyboard())

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = """
╔════════════════════════════════╗
║     📚 <b>ИНСТРУКЦИЯ</b>          ║
╠════════════════════════════════╣
║  <b>📌 ДОБАВЛЕНИЕ В КАНАЛ</b>     ║
║                                ║
║  1. Откройте настройки канала  ║
║  2. Администраторы → Добавить  ║
║  3. Найдите @ваш_бот           ║
║  4. Отметьте "Отправлять"      ║
║  5. Сохранить                  ║
╠════════════════════════════════╣
║  <b>📋 КОМАНДЫ</b>                 ║
║                                ║
║  💰 /rates - Курсы сейчас      ║
║  📈 /trends - История          ║
║  📊 /analytics - Аналитика     ║
║  ℹ️ /help - Эта инструкция     ║
║  👤 /about - О боте            ║
╠════════════════════════════════╣
║  <b>😊 ЗНАЧЕНИЯ СМАЙЛИКОВ</b>     ║
║                                ║
║  📈 - Рост курса               ║
║  📉 - Падение курса            ║
║  ➖ - Без изменений             ║
║  🟢 - Положительная динамика   ║
║  🔴 - Отрицательная динамика   ║
║  ⚪ - Стабильно                 ║
║  ▲ - Сильный рост              ║
║  ▼ - Сильное падение           ║
╠════════════════════════════════╣
║  📞 <b>ПОДДЕРЖКА</b>               ║
║  @fuckForensics                ║
║  https://nt-shipping.ru/       ║
╚════════════════════════════════╝
    """
    
    keyboard = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(text="👨‍💻 РАЗРАБОТЧИК", url="https://t.me/fuckForensics"),
        InlineKeyboardButton(text="🌐 САЙТ", url="https://nt-shipping.ru/")
    )
    
    await message.reply(help_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard)

@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    about_text = """
╔════════════════════════════════╗
║     💎 <b>NT SHIPPING CO</b> 💎     ║
╠════════════════════════════════╣
║  🤖 <b>О БОТЕ</b>                  ║
║                                ║
║  📌 Название: Currency Bot    ║
║  📌 Версия: 4.0.0             ║
║  📌 Источник: ЦБ РФ           ║
║  📌 Обновление: 8:00 МСК      ║
╠════════════════════════════════╣
║  <b>📊 ФУНКЦИОНАЛ</b>              ║
║                                ║
║  ✅ Авторассылка              ║
║  ✅ Тренды и аналитика        ║
║  ✅ История 30 дней           ║
║  ✅ Прогнозы                  ║
║  ✅ Красивый интерфейс        ║
║  ✅ Поддержка фото            ║
╠════════════════════════════════╣
║  <b>📅 ИНФОРМАЦИЯ</b>              ║
║                                ║
║  👨‍💻 Разработчик: @fuckForensics║
║  📅 Создан: 01.03.2026        ║
║  🌐 Сайт: nt-shipping.ru      ║
║  📊 Канал: @nt_shippingCo     ║
╚════════════════════════════════╝
    """
    
    keyboard = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(text="🌐 САЙТ", url="https://nt-shipping.ru/"),
        InlineKeyboardButton(text="📊 КАНАЛ", url="https://t.me/nt_shippingCo")
    )
    
    await message.reply(about_text, parse_mode=types.ParseMode.HTML, reply_markup=keyboard)

@dp.message_handler(commands=['rates'])
async def cmd_rates(message: types.Message):
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    
    await message.reply("🔄 <i>Получаю курсы...</i>", parse_mode=types.ParseMode.HTML)
    
    previous_rates = load_previous_rates()
    rates = await fetch_exchange_rates()
    
    if rates:
        save_previous_rates(rates)
        save_rates_history(rates)
        
        current_date = datetime.now()
        message_text = format_rates_message(rates, previous_rates, current_date)
        keyboard = create_rates_keyboard()
        
        await send_rates_with_photo(message.chat.id, message_text, keyboard)
    else:
        await message.reply(
            "❌ <b>Не удалось получить курсы</b>\nПопробуйте позже",
            parse_mode=types.ParseMode.HTML
        )

@dp.message_handler(commands=['trends'])
async def cmd_trends(message: types.Message):
    if rates_history:
        message_text = format_trends_message(rates_history)
        await message.reply(message_text, parse_mode=types.ParseMode.HTML)
    else:
        await message.reply("❌ Нет данных для отображения истории")

@dp.message_handler(commands=['analytics'])
async def cmd_analytics(message: types.Message):
    if not rates_history or len(rates_history) < 2:
        await message.reply("❌ Недостаточно данных для анализа")
        return
    
    recent = list(rates_history)[-7:]
    
    usd_values = [item['rates'].get('USD', 0) for item in recent]
    eur_values = [item['rates'].get('EUR', 0) for item in recent]
    cny_values = [item['rates'].get('CNY', 0) for item in recent]
    
    usd_avg = sum(usd_values) / len(usd_values)
    eur_avg = sum(eur_values) / len(eur_values)
    cny_avg = sum(cny_values) / len(cny_values)
    
    analytics_text = f"""
╔════════════════════════════════╗
║     📊 <b>АНАЛИТИКА</b>            ║
╠════════════════════════════════╣
║  <b>🇺🇸 ДОЛЛАР США</b>               ║
║  📈 Среднее: {usd_avg:.4f} ₽     ║
║  📉 Мин: {min(usd_values):.4f} ₽        ║
║  📈 Макс: {max(usd_values):.4f} ₽        ║
║  📊 Волат: {max(usd_values)-min(usd_values):.4f} ₽  ║
║                                ║
║  <b>🇪🇺 ЕВРО</b>                    ║
║  📈 Среднее: {eur_avg:.4f} ₽     ║
║  📉 Мин: {min(eur_values):.4f} ₽        ║
║  📈 Макс: {max(eur_values):.4f} ₽        ║
║  📊 Волат: {max(eur_values)-min(eur_values):.4f} ₽  ║
║                                ║
║  <b>🇨🇳 КИТАЙСКИЙ ЮАНЬ</b>          ║
║  📈 Среднее: {cny_avg:.4f} ₽     ║
║  📉 Мин: {min(cny_values):.4f} ₽        ║
║  📈 Макс: {max(cny_values):.4f} ₽        ║
║  📊 Волат: {max(cny_values)-min(cny_values):.4f} ₽  ║
╚════════════════════════════════╝
    """
    
    await message.reply(analytics_text, parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['set_photo_path'])
async def cmd_set_photo_path(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    path = message.get_args().strip()
    if not path:
        await message.reply("❌ Укажите путь: /set_photo_path /путь/к/фото.jpg")
        return
    
    if os.path.exists(path):
        photo_settings['use_photo'] = True
        photo_settings['photo_path'] = path
        photo_settings['photo_url'] = ''
        photo_settings['photo_file_id'] = ''
        save_photo_settings()
        await message.reply(f"✅ Путь сохранен: {path}\nФото будет использоваться!")
    else:
        await message.reply("❌ Файл не найден")

@dp.message_handler(commands=['set_photo_url'])
async def cmd_set_photo_url(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    url = message.get_args().strip()
    if not url:
        await message.reply("❌ Укажите URL: /set_photo_url https://example.com/photo.jpg")
        return
    
    photo_settings['use_photo'] = True
    photo_settings['photo_url'] = url
    photo_settings['photo_path'] = ''
    photo_settings['photo_file_id'] = ''
    save_photo_settings()
    await message.reply(f"✅ URL сохранен\nФото будет использоваться!")

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        photo_settings['use_photo'] = True
        photo_settings['photo_file_id'] = message.photo[-1].file_id
        photo_settings['photo_path'] = ''
        photo_settings['photo_url'] = ''
        save_photo_settings()
        await message.reply("✅ Фото сохранено! Будет использоваться при рассылке.")
    
    if message.caption and '/rates' in message.caption:
        await message.reply("🔄 <i>Получаю курсы...</i>", parse_mode=types.ParseMode.HTML)
        
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

async def on_startup(dp):
    logger.info("🚀 ЗАПУСК БОТА...")
    
    load_photo_settings()
    load_rates_history()
    load_stats()
    
    logger.info(f"📊 Загружено: {len(rates_history)} записей истории")
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
╔════════════════════════════════╗
║     ✅ <b>БОТ ЗАПУЩЕН</b>         ║
╠════════════════════════════════╣
║  ⏰ Рассылка: 8:00 МСК         ║
║  📊 Канал: {CHAT_ID}           ║
║  📸 Фото: {'ВКЛ' if photo_settings['use_photo'] else 'ВЫКЛ'}             ║
║  👥 Пользователей: {len(stats['users_count'])}     ║
╚════════════════════════════════╝
                """,
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа: {e}")

async def on_shutdown(dp):
    logger.info("🛑 ОСТАНОВКА БОТА...")
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