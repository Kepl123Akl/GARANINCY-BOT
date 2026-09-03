import os
import sqlite3
import datetime
import telebot

from telebot import types
from dotenv import load_dotenv
from zoneinfo import ZoneInfo


# ============================================================
# НАСТРОЙКИ
# ============================================================

load_dotenv()

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError(
        "❌ TOKEN не найден!\n"
        "Добавь переменную TOKEN в настройках BotHost."
    )

bot = telebot.TeleBot(TOKEN)

# Часовой пояс Екатеринбурга
TIMEZONE = ZoneInfo("Asia/Yekaterinburg")

# Время работы аудитории
START_HOUR = 8
END_HOUR = 20

# Бронируем на ближайший месяц
BOOKING_DAYS = 30

# Файл базы данных
DATABASE = "bookings.db"


# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def get_db():
    connection = sqlite3.connect(
        DATABASE,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = get_db()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            UNIQUE(booking_date, hour)
        )
    """)

    connection.commit()
    connection.close()


init_database()


# ============================================================
# СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

# user_id -> имя
waiting_for_name = {}

# user_id -> выбранная дата
selected_dates = {}


# ============================================================
# ВРЕМЯ
# ============================================================

def get_now():
    return datetime.datetime.now(TIMEZONE)


def get_today():
    return get_now().date()


def date_to_string(date):
    return date.strftime("%Y-%m-%d")


def string_to_date(value):
    return datetime.datetime.strptime(
        value,
        "%Y-%m-%d"
    ).date()


# ============================================================
# ПРОВЕРКА БРОНИ
# ============================================================

def is_booked(date, hour):

    connection = get_db()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM bookings
        WHERE booking_date = ?
        AND hour = ?
        """,
        (date_to_string(date), hour)
    )

    result = cursor.fetchone()

    connection.close()

    return result is not None


# ============================================================
# СОЗДАНИЕ БРОНИ
# ============================================================

def create_booking(
    date,
    hour,
    name,
    user_id,
    chat_id
):

    connection = get_db()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO bookings
            (
                booking_date,
                hour,
                name,
                user_id,
                chat_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                date_to_string(date),
                hour,
                name,
                user_id,
                chat_id,
                get_now().isoformat()
            )
        )

        connection.commit()

        success = True

    except sqlite3.IntegrityError:

        success = False

    finally:

        connection.close()

    return success


# ============================================================
# ПОЛУЧЕНИЕ ВСЕХ БРОНЕЙ
# ============================================================

def get_all_bookings():

    connection = get_db()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM bookings
        ORDER BY booking_date ASC, hour ASC
        """
    )

    result = cursor.fetchall()

    connection.close()

    return result


# ============================================================
# УДАЛЕНИЕ ВСЕХ БРОНЕЙ
# ============================================================

def delete_all_bookings():

    connection = get_db()

    cursor = connection.cursor()

    cursor.execute("DELETE FROM bookings")

    connection.commit()

    connection.close()


# ============================================================
# КЛАВИАТУРА ДАТ
# ============================================================

def create_date_keyboard():

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    today = get_today()

    buttons = []

    for day_number in range(BOOKING_DAYS):

        date = today + datetime.timedelta(
            days=day_number
        )

        date_text = date.strftime("%d.%m")

        weekday = [
            "Пн",
            "Вт",
            "Ср",
            "Чт",
            "Пт",
            "Сб",
            "Вс"
        ][date.weekday()]

        button = types.InlineKeyboardButton(
            text=f"{weekday} {date_text}",
            callback_data=f"date:{date_to_string(date)}"
        )

        buttons.append(button)

    for i in range(0, len(buttons), 2):

        keyboard.add(
            *buttons[i:i + 2]
        )

    return keyboard


# ============================================================
# КЛАВИАТУРА ВРЕМЕНИ
# ============================================================

def create_time_keyboard(date):

    keyboard = types.InlineKeyboardMarkup(row_width=3)

    buttons = []

    for hour in range(
        START_HOUR,
        END_HOUR
    ):

        # Если время уже занято — кнопку не показываем
        if is_booked(date, hour):
            continue

        button = types.InlineKeyboardButton(
            text=f"{hour:02d}:00",
            callback_data=(
                f"time:{date_to_string(date)}:{hour}"
            )
        )

        buttons.append(button)

    for i in range(0, len(buttons), 3):

        keyboard.add(
            *buttons[i:i + 3]
        )

    # Кнопка назад
    keyboard.add(
        types.InlineKeyboardButton(
            text="⬅️ Выбрать другую дату",
            callback_data="back_dates"
        )
    )

    return keyboard


# ============================================================
# /START
# ============================================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.send_message(
        message.chat.id,

        "👋 <b>Привет!</b>\n\n"
        "Я бот для бронирования аудитории.\n\n"

        "📅 /book — забронировать аудиторию\n"
        "📋 /rv — список бронирований\n"
        "❌ /delete — отменить все бронирования",

        parse_mode="HTML"
    )


# ============================================================
# /BOOK
# ============================================================

@bot.message_handler(commands=["book"])
def book(message):

    bot.send_message(
        message.chat.id,

        "📅 <b>Выберите дату</b>\n\n"
        "Можно бронировать на ближайший месяц.",

        parse_mode="HTML",

        reply_markup=create_date_keyboard()
    )


# ============================================================
# ВЫБОР ДАТЫ
# ============================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("date:")
)
def select_date(call):

    try:

        date_string = call.data.split(":", 1)[1]

        date = string_to_date(
            date_string
        )

    except Exception:

        bot.answer_callback_query(
            call.id,
            "❌ Ошибка даты.",
            show_alert=True
        )

        return

    # Проверяем, что дата входит в разрешённый диапазон

    today = get_today()

    last_day = today + datetime.timedelta(
        days=BOOKING_DAYS - 1
    )

    if date < today or date > last_day:

        bot.answer_callback_query(
            call.id,
            "❌ Эта дата недоступна.",
            show_alert=True
        )

        return

    selected_dates[call.from_user.id] = date

    keyboard = create_time_keyboard(date)

    # Проверяем наличие свободных времён

    if not keyboard.keyboard or (
        len(keyboard.keyboard) == 1
        and keyboard.keyboard[0][0].callback_data == "back_dates"
    ):

        bot.answer_callback_query(
            call.id,
            "На эту дату всё занято.",
            show_alert=True
        )

        return

    bot.answer_callback_query(
        call.id
    )

    try:

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,

            text=(
                "⏰ <b>Выберите время</b>\n\n"
                f"📅 {date.strftime('%d.%m.%Y')}\n\n"
                "Доступное время: 08:00–20:00."
            ),

            parse_mode="HTML",

            reply_markup=keyboard
        )

    except Exception:

        bot.send_message(
            call.message.chat.id,

            (
                "⏰ <b>Выберите время</b>\n\n"
                f"📅 {date.strftime('%d.%m.%Y')}"
            ),

            parse_mode="HTML",

            reply_markup=keyboard
        )


# ============================================================
# НАЗАД К ДАТАМ
# ============================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "back_dates"
)
def back_dates(call):

    bot.answer_callback_query(
        call.id
    )

    try:

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,

            text=(
                "📅 <b>Выберите дату</b>\n\n"
                "Доступно бронирование на ближайший месяц."
            ),

            parse_mode="HTML",

            reply_markup=create_date_keyboard()
        )

    except Exception:
        pass


# ============================================================
# ВЫБОР ВРЕМЕНИ
# ============================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("time:")
)
def select_time(call):

    try:

        _, date_string, hour_string = call.data.split(":")

        date = string_to_date(
            date_string
        )

        hour = int(hour_string)

    except Exception:

        bot.answer_callback_query(
            call.id,
            "❌ Ошибка времени.",
            show_alert=True
        )

        return

    # Проверяем время

    if hour < START_HOUR or hour >= END_HOUR:

        bot.answer_callback_query(
            call.id,
            "❌ Это время недоступно.",
            show_alert=True
        )

        return

    # Проверяем, не забронировал ли кто-то раньше

    if is_booked(date, hour):

        bot.answer_callback_query(
            call.id,
            "❌ Это время уже занято!",
            show_alert=True
        )

        # Обновляем клавиатуру

        try:

            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,

                reply_markup=create_time_keyboard(date)
            )

        except Exception:
            pass

        return

    # Сохраняем выбранную дату и время

    selected_dates[call.from_user.id] = (
        date,
        hour
    )

    bot.answer_callback_query(
        call.id
    )

    bot.send_message(
        call.message.chat.id,

        (
            "📝 <b>Введите ваше имя</b>\n\n"
            f"📅 {date.strftime('%d.%m.%Y')}\n"
            f"⏰ {hour:02d}:00–{hour + 1:02d}:00"
        ),

        parse_mode="HTML"
    )

    bot.register_next_step_handler(
        call.message,
        receive_name
    )


# ============================================================
# ПОЛУЧЕНИЕ ИМЕНИ
# ============================================================

def receive_name(message):

    user_id = message.from_user.id

    if not message.text:

        bot.send_message(
            message.chat.id,
            "❌ Пожалуйста, отправьте имя текстом."
        )

        return

    name = message.text.strip()

    if not name:

        bot.send_message(
            message.chat.id,
            "❌ Имя не может быть пустым."
        )

        return

    if user_id not in selected_dates:

        bot.send_message(
            message.chat.id,
            "❌ Бронирование устарело. Используйте /book."
        )

        return

    selected = selected_dates[user_id]

    if not isinstance(selected, tuple):

        bot.send_message(
            message.chat.id,
            "❌ Ошибка бронирования. Используйте /book."
        )

        return

    date, hour = selected

    # Ещё раз проверяем бронь
    if is_booked(date, hour):

        bot.send_message(
            message.chat.id,
            "❌ К сожалению, это время уже заняли."
        )

        return

    # Создаём бронь

    success = create_booking(
        date=date,
        hour=hour,
        name=name,
        user_id=user_id,
        chat_id=message.chat.id
    )

    if not success:

        bot.send_message(
            message.chat.id,
            "❌ Это время только что занял другой пользователь."
        )

        return

    # Удаляем временное состояние

    selected_dates.pop(
        user_id,
        None
    )

    end_hour = hour + 1

    # ============================================
    # ПОДТВЕРЖДЕНИЕ
    # ============================================

    bot.send_message(
        message.chat.id,

        (
            "✅ <b>БРОНИРОВАНИЕ ПОДТВЕРЖДЕНО!</b>\n\n"

            f"👤 Имя: <b>{name}</b>\n"
            f"📅 Дата: <b>{date.strftime('%d.%m.%Y')}</b>\n"
            f"⏰ Время: <b>{hour:02d}:00–{end_hour:02d}:00</b>\n\n"

            "🔴 Это время теперь занято."
        ),

        parse_mode="HTML"
    )

    # ============================================
    # СООБЩЕНИЕ В ГРУППУ
    # ============================================

    try:

        bot.send_message(
            message.chat.id,

            (
                "🔴 <b>АУДИТОРИЯ ЗАНЯТА</b>\n\n"

                f"👤 {name}\n"
                f"📅 {date.strftime('%d.%m.%Y')}\n"
                f"⏰ {hour:02d}:00–{end_hour:02d}:00\n\n"

                "Не занимайте это время."
            ),

            parse_mode="HTML"
        )

    except Exception:
        pass


# ============================================================
# /RV
# ============================================================

@bot.message_handler(commands=["rv"])
def reservations(message):

    all_bookings = get_all_bookings()

    if not all_bookings:

        bot.send_message(
            message.chat.id,
            "📭 <b>Бронирований пока нет.</b>",
            parse_mode="HTML"
        )

        return

    text = "📢 <b>СПИСОК БРОНИРОВАНИЙ</b>\n\n"

    for booking in all_bookings:

        date = string_to_date(
            booking["booking_date"]
        )

        hour = booking["hour"]

        text += (
            f"👤 {booking['name']}\n"
            f"📅 {date.strftime('%d.%m.%Y')}\n"
            f"⏰ {hour:02d}:00–{hour + 1:02d}:00\n"
            "━━━━━━━━━━━━━━\n"
        )

    # Собираем уникальные чаты
    chat_ids = set()

    for booking in all_bookings:

        chat_ids.add(
            booking["chat_id"]
        )

    # Отправляем всем пользователям/чатам

    for chat_id in chat_ids:

        try:

            bot.send_message(
                chat_id,
                text,
                parse_mode="HTML"
            )

        except Exception:
            pass

    # Сообщение тому, кто вызвал /rv

    bot.send_message(
        message.chat.id,
        "✅ Список бронирований отправлен."
    )


# ============================================================
# /DELETE
# ============================================================

@bot.message_handler(commands=["delete"])
def delete_all(message):

    all_bookings = get_all_bookings()

    if not all_bookings:

        bot.send_message(
            message.chat.id,
            "📭 Бронирований нет."
        )

        return

    # Уведомляем пользователей

    sent_chats = set()

    for booking in all_bookings:

        chat_id = booking["chat_id"]

        if chat_id in sent_chats:
            continue

        sent_chats.add(chat_id)

        date = string_to_date(
            booking["booking_date"]
        )

        hour = booking["hour"]

        try:

            bot.send_message(
                chat_id,

                (
                    "❌ <b>ВАША БРОНЬ ОТМЕНЕНА</b>\n\n"
                    f"📅 {date.strftime('%d.%m.%Y')}\n"
                    f"⏰ {hour:02d}:00–{hour + 1:02d}:00\n\n"
                    "Администратор отменил все бронирования."
                ),

                parse_mode="HTML"
            )

        except Exception:
            pass

    # Удаляем все записи

    delete_all_bookings()

    bot.send_message(
        message.chat.id,

        (
            "✅ <b>ВСЕ БРОНИРОВАНИЯ ОТМЕНЕНЫ</b>\n\n"
            "Все временные интервалы снова доступны."
        ),

        parse_mode="HTML"
    )


# ============================================================
# ОБРАБОТКА ОШИБОК POLLING
# ============================================================

print("========================================")
print("🤖 БОТ ЗАПУЩЕН")
print("📅 Бронирование: ближайшие 30 дней")
print("⏰ Время аудитории: 08:00–20:00")
print("🌍 Часовой пояс: Asia/Yekaterinburg")
print("💾 База данных: SQLite")
print("========================================")


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
