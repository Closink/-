import logging
import os
from datetime import datetime
from xml.etree import ElementTree
import pickle
from collections import deque

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN        = "8546494996:AAEh4ylPyN8prRSy0LLr9OE0rZFwggrHEo4"
CHAT_ID      = "-1002129097415"
ADMIN_IDS    = [8186449861]
CBR_URL      = "https://www.cbr.ru/scripts/XML_daily.asp"

PREVIOUS_RATES_FILE  = "previous_rates.pkl"
PHOTO_SETTINGS_FILE  = "photo_settings.pkl"
HISTORY_FILE         = "rates_history.pkl"
STATS_FILE           = "stats.pkl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot       = Bot(token=TOKEN)
dp        = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

photo_settings = {
    'use_photo':     False,
    'photo_path':    '',
    'photo_url':     '',
    'photo_file_id': ''
}

stats = {
    'total_requests': 0,
    'total_sent':     0,
    'last_update':    None,
    'users_count':    set(),
}

rates_history = deque(maxlen=30)


def save_stats():
    try:
        data = stats.copy()
        data['users_count'] = list(stats['users_count'])
        with open(STATS_FILE, 'wb') as f:
            pickle.dump(data, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")

def load_stats():
    global stats
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'rb') as f:
                loaded = pickle.load(f)
                loaded['users_count'] = set(loaded.get('users_count', []))
                stats.update(loaded)
    except Exception as e:
        logger.error(f"Ошибка загрузки статистики: {e}")

def save_rates_history(rates: dict):
    try:
        rates_history.append({'date': datetime.now(), 'rates': rates.copy()})
        with open(HISTORY_FILE, 'wb') as f:
            pickle.dump(list(rates_history), f)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")

def load_rates_history():
    global rates_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'rb') as f:
                data = pickle.load(f)
                rates_history = deque(data, maxlen=30)
    except Exception as e:
        logger.error(f"Ошибка загрузки истории: {e}")

def save_photo_settings():
    try:
        with open(PHOTO_SETTINGS_FILE, 'wb') as f:
            pickle.dump(photo_settings, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения фото-настроек: {e}")

def load_photo_settings():
    global photo_settings
    try:
        if os.path.exists(PHOTO_SETTINGS_FILE):
            with open(PHOTO_SETTINGS_FILE, 'rb') as f:
                photo_settings.update(pickle.load(f))
    except Exception as e:
        logger.error(f"Ошибка загрузки фото-настроек: {e}")

def save_previous_rates(rates: dict):
    try:
        with open(PREVIOUS_RATES_FILE, 'wb') as f:
            pickle.dump(rates, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения курсов: {e}")

def load_previous_rates() -> dict:
    try:
        if os.path.exists(PREVIOUS_RATES_FILE):
            with open(PREVIOUS_RATES_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки курсов: {e}")
    return {}


def trend_emoji(current: float, previous: float) -> str:
    if previous == 0:
        return "🔄"
    if current > previous:
        return "📈"
    elif current < previous:
        return "📉"
    return "➖"

def fmt_rate(val: float) -> str:
    return f"{val:.4f}".replace('.', ',')

def fmt_change(current: float, previous: float) -> str:
    if previous == 0:
        return ""
    diff = current - previous
    sign = "+" if diff > 0 else ""
    return f"({sign}{diff:.4f})".replace('.', ',')

def safe_avg(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


async def fetch_exchange_rates() -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CBR_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ElementTree.fromstring(xml_data)
                    rates = {}
                    for valute in root.findall('.//Valute'):
                        code = valute.find('CharCode').text
                        if code in ('USD', 'EUR', 'CNY'):
                            value   = float(valute.find('Value').text.replace(',', '.'))
                            nominal = int(valute.find('Nominal').text)
                            rates[code] = round(value / nominal, 4)
                    return rates
                logger.error(f"ЦБ РФ вернул статус {resp.status}")
    except Exception as e:
        logger.error(f"Ошибка запроса к ЦБ РФ: {e}")
    return {}


def msg_rates(rates: dict, prev: dict, date: datetime) -> str:
    date_str = date.strftime("%d.%m.%Y")
    cny = rates.get('CNY', 0)
    usd = rates.get('USD', 0)
    eur = rates.get('EUR', 0)
    return (
        "Доброе утро\n"
        "\n"
        "Официальный курс валют на сегодня 🤑\n"
        "\n"
        f"          <b>{date_str}</b>\n"
        "\n"
        f"🇨🇳 CNY, 1 \u00a5   {fmt_rate(cny)} \u20bd {trend_emoji(cny, prev.get('CNY', 0))} {fmt_change(cny, prev.get('CNY', 0))}\n"
        f"🇺🇸 USD, 1 $   {fmt_rate(usd)} \u20bd {trend_emoji(usd, prev.get('USD', 0))} {fmt_change(usd, prev.get('USD', 0))}\n"
        f"🇪🇺 EUR, 1 \u20ac   {fmt_rate(eur)} \u20bd {trend_emoji(eur, prev.get('EUR', 0))} {fmt_change(eur, prev.get('EUR', 0))}"
    )


def msg_trends(history: deque) -> str:
    if not history:
        return "❌ Нет данных для отображения"
    recent = list(history)[-7:]
    lines = [
        "📊 <b>История курсов</b>",
        "",
        "<b>Дата       CNY      USD      EUR</b>",
        "─────────────────────────────",
    ]
    for item in recent:
        d   = item['date'].strftime("%d.%m")
        cny = item['rates'].get('CNY', 0)
        usd = item['rates'].get('USD', 0)
        eur = item['rates'].get('EUR', 0)
        lines.append(f"{d}     {cny:.2f}   {usd:.2f}   {eur:.2f}")
    if len(recent) >= 2:
        lines.append("")
        for code in ('CNY', 'USD', 'EUR'):
            first = recent[0]['rates'].get(code, 0)
            last  = recent[-1]['rates'].get(code, 0)
            diff  = last - first
            sign  = "+" if diff >= 0 else ""
            lines.append(f"{trend_emoji(last, first)} {code}: {sign}{diff:.4f} \u20bd за период")
    return "\n".join(lines)


def msg_analytics(history: deque) -> str:
    if len(history) < 2:
        return "❌ Недостаточно данных — нужно минимум 2 записи"
    recent = list(history)[-5:]

    def block(code: str, flag: str) -> list:
        values = [item['rates'].get(code, 0) for item in recent]
        return [
            f"{flag} <b>{code}</b>  {trend_emoji(values[-1], values[0])}",
            f"  Сейчас:   {fmt_rate(values[-1])} \u20bd",
            f"  Среднее:  {fmt_rate(safe_avg(values))} \u20bd",
            f"  Мин/Макс: {fmt_rate(min(values))} / {fmt_rate(max(values))} \u20bd",
        ]

    lines = ["📈 <b>Аналитика курсов</b> (последние 5 дней)", ""]
    lines += block('CNY', '🇨🇳')
    lines.append("")
    lines += block('USD', '🇺🇸')
    lines.append("")
    lines += block('EUR', '🇪🇺')
    return "\n".join(lines)


def msg_start() -> str:
    return (
        "👋 Добро пожаловать!\n"
        "\n"
        "💎 <b>NT Shipping Co</b> — курсы валют ЦБ РФ\n"
        "\n"
        "🇨🇳 CNY  🇺🇸 USD  🇪🇺 EUR\n"
        "\n"
        "📋 <b>Команды:</b>\n"
        "💰 /rates — текущий курс\n"
        "📊 /trends — история за 7 дней\n"
        "📈 /analytics — аналитика\n"
        "ℹ️ /about — о боте\n"
        "📚 /help — помощь\n"
        "\n"
        "⏰ Автоматическая рассылка в 08:00 МСК"
    )


def msg_help() -> str:
    return (
        "📚 <b>Помощь</b>\n"
        "\n"
        "📌 <b>Как добавить бота в канал:</b>\n"
        "1. Настройки канала\n"
        "2. Администраторы\n"
        "3. Добавить бота\n"
        "4. Разрешить отправку сообщений\n"
        "\n"
        "📋 <b>Команды:</b>\n"
        "💰 /rates — текущий курс\n"
        "📊 /trends — история за 7 дней\n"
        "📈 /analytics — аналитика\n"
        "👤 /about — о боте\n"
        "\n"
        "📸 <b>Иконки тренда:</b>\n"
        "📈 — курс вырос\n"
        "📉 — курс упал\n"
        "➖ — без изменений"
    )


def msg_about() -> str:
    return (
        "💎 <b>NT Shipping Co</b>\n"
        "\n"
        "🤖 Бот курсов валют v5.0\n"
        "📡 Источник: ЦБ РФ\n"
        "⏰ Рассылка: 08:00 МСК\n"
        "\n"
        "✅ Авторассылка в канал\n"
        "✅ История курсов\n"
        "✅ Аналитика трендов\n"
        "✅ Фото к сообщениям\n"
        "\n"
        "👨\u200d💻 @fuckForensics\n"
        "🌐 nt-shipping.ru"
    )


def msg_admin() -> str:
    photo_status = "✅ включено" if photo_settings['use_photo'] else "❌ выключено"
    return (
        "⚙️ <b>Админ-панель</b>\n"
        "\n"
        f"👥 Пользователей: {len(stats['users_count'])}\n"
        f"📨 Отправок: {stats['total_sent']}\n"
        f"🔄 Запросов: {stats['total_requests']}\n"
        f"📸 Фото: {photo_status}"
    )


def msg_stats() -> str:
    last = stats.get('last_update')
    last_str = last.strftime("%d.%m.%Y %H:%M") if last else "—"
    return (
        "📊 <b>Статистика</b>\n"
        "\n"
        f"👥 Пользователей: {len(stats['users_count'])}\n"
        f"📨 Отправок: {stats['total_sent']}\n"
        f"🔄 Запросов: {stats['total_requests']}\n"
        f"🕐 Последняя рассылка: {last_str}"
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Статистика",     callback_data="show_stats"),
        InlineKeyboardButton("📸 Настроить фото", callback_data="setup_photo"),
    )
    kb.add(
        InlineKeyboardButton("🧪 Тест рассылки",  callback_data="test_photo"),
        InlineKeyboardButton("❌ Выкл. фото",      callback_data="disable_photo"),
    )
    kb.add(
        InlineKeyboardButton("📋 Статус фото",    callback_data="check_photo"),
    )
    return kb


async def send_message_smart(chat_id, text: str):
    HTML = types.ParseMode.HTML
    try:
        if photo_settings['use_photo']:
            fid  = photo_settings.get('photo_file_id')
            path = photo_settings.get('photo_path')
            url  = photo_settings.get('photo_url')
            if fid:
                await bot.send_photo(chat_id=chat_id, photo=fid, caption=text, parse_mode=HTML)
                return
            if path and os.path.exists(path):
                with open(path, 'rb') as ph:
                    sent = await bot.send_photo(chat_id=chat_id, photo=ph, caption=text, parse_mode=HTML)
                photo_settings['photo_file_id'] = sent.photo[-1].file_id
                save_photo_settings()
                return
            if url:
                await bot.send_photo(chat_id=chat_id, photo=url, caption=text, parse_mode=HTML)
                return
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=HTML)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text=text + "\n\n⚠️ Фото недоступно", parse_mode=HTML)
        except Exception as e2:
            logger.error(f"Аварийная отправка не удалась: {e2}")


async def send_daily_rates():
    logger.info("Ежедневная рассылка...")
    prev  = load_previous_rates()
    rates = await fetch_exchange_rates()
    if not rates:
        logger.error("Не удалось получить курсы")
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="❌ Не удалось получить курсы валют. Проверьте соединение.",
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")
        return
    save_previous_rates(rates)
    save_rates_history(rates)
    stats['total_sent']  += 1
    stats['last_update']  = datetime.now()
    save_stats()
    await send_message_smart(CHAT_ID, msg_rates(rates, prev, datetime.now()))
    logger.info("Рассылка отправлена")


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    await message.reply(msg_start(), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    await message.reply(msg_help(), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    await message.reply(msg_about(), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['rates'])
async def cmd_rates(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    wait = await message.reply("🔄 Получаю курсы...", parse_mode=types.ParseMode.HTML)
    prev  = load_previous_rates()
    rates = await fetch_exchange_rates()
    try:
        await bot.delete_message(message.chat.id, wait.message_id)
    except Exception:
        pass
    if rates:
        save_previous_rates(rates)
        save_rates_history(rates)
        await send_message_smart(message.chat.id, msg_rates(rates, prev, datetime.now()))
    else:
        await message.reply("❌ Не удалось получить курсы. Попробуйте позже.", parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['trends'])
async def cmd_trends(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    await message.reply(msg_trends(rates_history), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['analytics'])
async def cmd_analytics(message: types.Message):
    if str(message.chat.id).startswith('-100'):
        return
    stats['users_count'].add(message.from_user.id)
    stats['total_requests'] += 1
    save_stats()
    await message.reply(msg_analytics(rates_history), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ Нет доступа")
        return
    await message.reply(msg_admin(), parse_mode=types.ParseMode.HTML, reply_markup=admin_keyboard())


@dp.message_handler(commands=['set_photo_path'])
async def cmd_set_photo_path(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    path = message.get_args().strip()
    if not path:
        await message.reply("❌ Укажите путь\nПример: /set_photo_path /home/user/photo.jpg")
        return
    if os.path.exists(path):
        photo_settings.update({'use_photo': True, 'photo_path': path, 'photo_url': '', 'photo_file_id': ''})
        save_photo_settings()
        await message.reply(f"✅ Фото установлено:\n<code>{path}</code>", parse_mode=types.ParseMode.HTML)
    else:
        await message.reply("❌ Файл не найден. Проверьте путь.")


@dp.message_handler(commands=['set_photo_url'])
async def cmd_set_photo_url(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    url = message.get_args().strip()
    if not url:
        await message.reply("❌ Укажите URL\nПример: /set_photo_url https://example.com/photo.jpg")
        return
    photo_settings.update({'use_photo': True, 'photo_url': url, 'photo_path': '', 'photo_file_id': ''})
    save_photo_settings()
    await message.reply("✅ URL фото сохранён")


@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        photo_settings.update({
            'use_photo':     True,
            'photo_file_id': message.photo[-1].file_id,
            'photo_path':    '',
            'photo_url':     ''
        })
        save_photo_settings()
        await message.reply("✅ Фото сохранено и будет использоваться при рассылке")


@dp.callback_query_handler(lambda c: c.data == 'show_stats')
async def cb_show_stats(cq: types.CallbackQuery):
    await bot.answer_callback_query(cq.id)
    await bot.send_message(cq.from_user.id, msg_stats(), parse_mode=types.ParseMode.HTML)


@dp.callback_query_handler(lambda c: c.data == 'setup_photo')
async def cb_setup_photo(cq: types.CallbackQuery):
    await bot.answer_callback_query(cq.id)
    await bot.send_message(
        cq.from_user.id,
        "📸 <b>Настройка фото</b>\n"
        "\n"
        "Выберите способ:\n"
        "1️⃣ Отправьте фото прямо боту\n"
        "2️⃣ /set_photo_path /путь/к/файлу.jpg\n"
        "3️⃣ /set_photo_url https://ссылка.на/фото.jpg",
        parse_mode=types.ParseMode.HTML
    )


@dp.callback_query_handler(lambda c: c.data == 'test_photo')
async def cb_test_photo(cq: types.CallbackQuery):
    await bot.answer_callback_query(cq.id, text="Отправляю тест...")
    prev  = load_previous_rates()
    rates = await fetch_exchange_rates()
    if rates:
        await send_message_smart(cq.from_user.id, msg_rates(rates, prev, datetime.now()))
    else:
        await bot.send_message(cq.from_user.id, "❌ Не удалось получить курсы")


@dp.callback_query_handler(lambda c: c.data == 'disable_photo')
async def cb_disable_photo(cq: types.CallbackQuery):
    photo_settings['use_photo'] = False
    save_photo_settings()
    await bot.answer_callback_query(cq.id, text="Фото отключено")
    await bot.send_message(cq.from_user.id, "❌ Фото отключено. Бот будет отправлять только текст.")


@dp.callback_query_handler(lambda c: c.data == 'check_photo')
async def cb_check_photo(cq: types.CallbackQuery):
    await bot.answer_callback_query(cq.id)
    status  = "✅ включено" if photo_settings['use_photo'] else "❌ выключено"
    fid     = photo_settings.get('photo_file_id') or "—"
    path    = photo_settings.get('photo_path')    or "—"
    url     = photo_settings.get('photo_url')     or "—"
    short   = (fid[:25] + "...") if fid != "—" else "—"
    await bot.send_message(
        cq.from_user.id,
        f"📸 <b>Статус фото</b>\n"
        f"\n"
        f"Режим: {status}\n"
        f"File ID: <code>{short}</code>\n"
        f"Путь: {path}\n"
        f"URL: {url}",
        parse_mode=types.ParseMode.HTML
    )


async def on_startup(dp):
    logger.info("Запуск бота...")
    load_photo_settings()
    load_rates_history()
    load_stats()
    scheduler.add_job(send_daily_rates, trigger="cron", hour=8, minute=0,
                      id="daily_rates", replace_existing=True)
    scheduler.start()
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"✅ <b>Бот запущен</b>\n"
                f"\n"
                f"⏰ Рассылка: 08:00 МСК\n"
                f"📡 Канал: {CHAT_ID}\n"
                f"📸 Фото: {'включено' if photo_settings['use_photo'] else 'выключено'}\n"
                f"👥 Пользователей: {len(stats['users_count'])}",
                parse_mode=types.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")


async def on_shutdown(dp):
    logger.info("Остановка бота...")
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
