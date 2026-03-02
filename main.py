import asyncio
import logging
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree
from typing import Dict, Tuple
import pickle

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "8546494996:AAEh4ylPyN8prRSy0LLr9OE0rZFwggrHEo4"
CHAT_ID = "-1002129097415"
ADMIN_IDS = [8186449861]

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

PREVIOUS_RATES_FILE = "previous_rates.pkl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


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
    
    message = (
        f"🏦 <b>Курсы валют ЦБ РФ</b>\n"
        f"📅 {date_str}\n\n"
        f"Доброе утро!\n\n"
        f"Официальный курс валют на сегодня\n"
        f"{date_str}\n\n"
        f"🇨🇳 CNY, 1 ¥  {cny_trend}\n"
        f"🇺🇸 USD, 1 $  {usd_trend}\n"
        f"🇪🇺 EUR, 1 €  {eur_trend}\n\n"
        f"<code>{rates.get('CNY', 0):.4f} ₽</code>\n"
        f"<code>{rates.get('USD', 0):.4f} ₽</code>\n"
        f"<code>{rates.get('EUR', 0):.4f} ₽</code>\n\n"
        f"💬 Прокомментировать"
    )
    
    return message


def create_rates_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(
            text="🔗 Курсы ЦБ РФ",
            url="https://cbr.ru/"
        ),
        InlineKeyboardButton(
            text="📊 Графики",
            url="https://www.cbr.ru/currency_base/dynamics/"
        )
    )
    return keyboard


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
            
            await bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                reply_markup=keyboard,
                parse_mode=types.ParseMode.HTML
            )
            logger.info("Курсы валют успешно отправлены")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
    else:
        logger.error("Не удалось получить курсы валют")
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="❌ <b>Не удалось получить курсы валют сегодня.</b>\n"
                     "Проверьте соединение с сайтом ЦБ РФ.",
                parse_mode=types.ParseMode.HTML
            )
        except:
            pass


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 <b>Привет! Я бот для отслеживания курсов валют ЦБ РФ</b>\n\n"
        "📊 Каждое утро в 8:00 я отправляю актуальные курсы USD, EUR и CNY.\n\n"
        "📈 <b>Что я умею:</b>\n"
        "• Показывать тренды (📈 выросли, 📉 упали)\n"
        "• Отправлять курсы по запросу\n"
        "• Давать ссылки на официальные графики\n\n"
        "🔍 <b>Команды:</b>\n"
        "/rates - получить курсы сейчас\n"
        "/help - подробная инструкция и помощь",
        parse_mode=types.ParseMode.HTML
    )


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = (
        "📚 <b>ПОДРОБНАЯ ИНСТРУКЦИЯ</b>\n\n"
        
        "🔹 <b>КАК ДОБАВИТЬ БОТА В КАНАЛ/ГРУППУ</b>\n"
        "1. Откройте ваш канал или группу\n"
        "2. Нажмите на название канала/группы\n"
        "3. Выберите «Управление каналом» или «Добавить участника»\n"
        "4. В поиске введите @имя_бота\n"
        "5. Добавьте бота как администратора\n\n"
        
        "🔹 <b>КАК ВЫДАТЬ ПРАВА АДМИНИСТРАТОРА</b>\n"
        "1. В настройках канала выберите «Администраторы»\n"
        "2. Нажмите «Добавить администратора»\n"
        "3. Выберите бота из списка\n"
        "4. <b>ОБЯЗАТЕЛЬНО отметьте галочку:</b>\n"
        "   ✓ «Отправлять сообщения»\n"
        "   ✓ «Редактировать сообщения» (опционально)\n"
        "5. Нажмите «Сохранить»\n\n"
        
        "🔹 <b>НАСТРОЙКА ЕЖЕДНЕВНОЙ РАССЫЛКИ</b>\n"
        "По умолчанию бот отправляет курсы в 8:00 утра по московскому времени.\n\n"
        
        "🔹 <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n"
        "/start - приветствие\n"
        "/help - эта инструкция\n"
        "/rates - получить курсы сейчас\n"
        "/trends - показать историю изменений\n"
        "/about - информация о боте\n\n"
        
        "🔹 <b>ЧТО ОЗНАЧАЮТ СМАЙЛИКИ</b>\n"
        "📈 - курс вырос по сравнению со вчера\n"
        "📉 - курс упал по сравнению со вчера\n"
        "➖ - без изменений\n"
        "🔄 - нет данных для сравнения\n\n"
        
        "🔹 <b>ОТПРАВКА КАРТИНОК</b>\n"
        "Чтобы добавить картинку к курсам, отправьте фото с подписью /rates\n\n"
        
        "📞 <b>ПОДДЕРЖКА</b>\n"
        "По всем вопросам: @fuckForensics\n"
        "Сайт: https://nt-shipping.ru/"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="📊 Добавить бота в канал", url="https://t.me/your_bot_username?startchannel")
    )
    keyboard.add(
        InlineKeyboardButton(text="👨‍💻 Разработчик", url="https://t.me/fuckForensics")
    )
    keyboard.add(
        InlineKeyboardButton(text="🌐 Наш сайт", url="https://nt-shipping.ru/")
    )
    
    await message.reply(
        help_text,
        parse_mode=types.ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    about_text = (
        "🤖 <b>О БОТЕ</b>\n\n"
        "Название: Currency Rate Bot\n"
        "Версия: 2.0.0\n"
        "Источник данных: Центральный Банк РФ (cbr.ru)\n"
        "Обновление: Ежедневно в 8:00 МСК\n\n"
        
        "📊 <b>Функционал:</b>\n"
        "• Автоматическая рассылка курсов\n"
        "• Отображение трендов (📈📉)\n"
        "• Сравнение с предыдущим днём\n"
        "• Инлайн-кнопки для быстрого перехода\n\n"
        
        "👨‍💻 <b>Разработчик:</b> @fuckForensics\n"
        "📅 Дата создания: 2026.03.01\n"
        "🌐 Сайт: https://nt-shipping.ru/"
    )
    
    await message.reply(about_text, parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['trends'])
async def cmd_trends(message: types.Message):
    previous_rates = load_previous_rates()
    current_rates = await fetch_exchange_rates()
    
    if current_rates and previous_rates:
        trends_text = "📊 <b>ИСТОРИЯ ИЗМЕНЕНИЙ</b>\n\n"
        
        for currency in ['USD', 'EUR', 'CNY']:
            current = current_rates.get(currency, 0)
            previous = previous_rates.get(currency, 0)
            change = current - previous
            percent = (change / previous * 100) if previous != 0 else 0
            
            emoji = get_trend_emoji(current, previous)
            
            currency_symbols = {
                'USD': '🇺🇸 Доллар',
                'EUR': '🇪🇺 Евро',
                'CNY': '🇨🇳 Юань'
            }
            
            trends_text += (
                f"{currency_symbols[currency]}:\n"
                f"{emoji} {current:.4f} ₽ (было {previous:.4f})\n"
                f"Изменение: {change:+.4f} ₽ ({percent:+.2f}%)\n\n"
            )
        
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
        
        await message.reply(
            text=message_text,
            reply_markup=keyboard,
            parse_mode=types.ParseMode.HTML
        )
    else:
        await message.reply(
            "❌ <b>Не удалось получить курсы валют.</b>\n"
            "Попробуйте позже или проверьте соединение.",
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


@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
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


async def on_startup(dp):
    logger.info("Бот запускается...")
    
    previous_rates = load_previous_rates()
    if previous_rates:
        logger.info(f"Загружены предыдущие курсы: {previous_rates}")
    
    scheduler.add_job(
        send_daily_rates,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_rates",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Планировщик запущен. Отправка каждый день в 8:00 по московскому времени")
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "✅ <b>Бот успешно запущен!</b>\n"
                f"⏰ Ежедневная рассылка в 8:00 МСК\n"
                f"📊 Канал: {CHAT_ID}",
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def on_shutdown(dp):
    logger.info("Бот останавливается...")
    scheduler.shutdown()
    await bot.close()


if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )