import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

ROOM_NAME = "Гаранинцы"

# Доступные часы
TIME_SLOTS = [
    "08:00–09:00",
    "09:00–10:00",
    "10:00–11:00",
    "11:00–12:00",
    "12:00–13:00",
    "13:00–14:00",
    "14:00–15:00",
]

DB_FILE = "bookings.db"


# =========================
# БАЗА ДАННЫХ
# =========================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(date, time_slot)
        )
    """)

    conn.commit()
    conn.close()


def get_booking(date, time_slot):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_id, username, name
        FROM bookings
        WHERE date = ? AND time_slot = ?
    """, (date, time_slot))

    result = cursor.fetchone()
    conn.close()

    return result


def create_booking(user_id, username, name, date, time_slot):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO bookings
            (user_id, username, name, date, time_slot, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            name,
            date,
            time_slot,
            datetime.now().isoformat()
        ))

        conn.commit()
        success = True

    except sqlite3.IntegrityError:
        success = False

    conn.close()

    return success


def get_user_bookings(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, date, time_slot, name
        FROM bookings
        WHERE user_id = ?
        ORDER BY date, time_slot
    """, (user_id,))

    result = cursor.fetchall()
    conn.close()

    return result


def delete_booking(booking_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM bookings
        WHERE id = ? AND user_id = ?
    """, (booking_id, user_id))

    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


# =========================
# КЛАВИАТУРЫ
# =========================

def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Забронировать", callback_data="book")],
        [InlineKeyboardButton("📋 Мои брони", callback_data="my_bookings")],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        f"🎭 <b>Бронирование аудитории «{ROOM_NAME}»</b>\n\n"
        "Здесь можно забронировать аудиторию для репетиции.\n\n"
        "🕐 Время работы: <b>08:00–15:00</b>\n"
        "⏱ Продолжительность: <b>1 час</b>\n\n"
        "Выберите действие:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================
# ПОКАЗ ДАТЫ
# =========================

async def show_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    today = datetime.now().strftime("%d.%m.%Y")

    keyboard = [
        [
            InlineKeyboardButton(
                f"📅 Сегодня — {today}",
                callback_data=f"date_{datetime.now().strftime('%Y-%m-%d')}"
            )
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back")
        ]
    ]

    await query.edit_message_text(
        "📅 <b>Выберите дату</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ПОКАЗ ВРЕМЕНИ
# =========================

async def show_times(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    date = query.data.replace("date_", "")

    context.user_data["booking_date"] = date

    keyboard = []

    for slot in TIME_SLOTS:

        booking = get_booking(date, slot)

        if booking:
            button_text = f"🔴 {slot} — занято"
            callback = "occupied"

        else:
            button_text = f"🟢 {slot} — свободно"
            callback = f"time_{slot}"

        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=callback)
        ])

    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="book")
    ])

    formatted_date = datetime.strptime(
        date, "%Y-%m-%d"
    ).strftime("%d.%m.%Y")

    await query.edit_message_text(
        f"📅 <b>{formatted_date}</b>\n\n"
        "Выберите время репетиции:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ВЫБОР ВРЕМЕНИ
# =========================

async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    slot = query.data.replace("time_", "")

    context.user_data["booking_time"] = slot

    await query.edit_message_text(
        f"🕐 Вы выбрали: <b>{slot}</b>\n\n"
        "Теперь напишите ваше <b>имя и фамилию</b>.\n\n"
        "Например:\n"
        "Иван Иванов",
        parse_mode="HTML"
    )

    context.user_data["waiting_for_name"] = True


# =========================
# ПОЛУЧЕНИЕ ИМЕНИ
# =========================

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("waiting_for_name"):
        return

    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(
            "Пожалуйста, напишите имя и фамилию."
        )
        return

    date = context.user_data.get("booking_date")
    slot = context.user_data.get("booking_time")

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Проверяем, не занял ли кто-то время
    if get_booking(date, slot):

        await update.message.reply_text(
            "❌ К сожалению, это время уже заняли.",
            reply_markup=main_keyboard()
        )

        context.user_data.clear()
        return

    success = create_booking(
        user_id,
        username,
        name,
        date,
        slot
    )

    if success:

        formatted_date = datetime.strptime(
            date, "%Y-%m-%d"
        ).strftime("%d.%m.%Y")

        await update.message.reply_text(
            f"✅ <b>Аудитория забронирована!</b>\n\n"
            f"🎭 Аудитория: <b>{ROOM_NAME}</b>\n"
            f"📅 Дата: <b>{formatted_date}</b>\n"
            f"🕐 Время: <b>{slot}</b>\n"
            f"👤 Имя: <b>{name}</b>\n\n"
            "Хорошей репетиции!",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )

    else:

        await update.message.reply_text(
            "❌ Это время только что занял другой пользователь.",
            reply_markup=main_keyboard()
        )

    context.user_data.clear()


# =========================
# МОИ БРОНИ
# =========================

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    bookings = get_user_bookings(user_id)

    if not bookings:

        await query.edit_message_text(
            "📋 <b>У вас пока нет бронирований.</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )

        return

    text = "📋 <b>Ваши бронирования:</b>\n\n"

    keyboard = []

    for booking in bookings:

        booking_id, date, slot, name = booking

        formatted_date = datetime.strptime(
            date, "%Y-%m-%d"
        ).strftime("%d.%m.%Y")

        text += (
            f"🎭 <b>{ROOM_NAME}</b>\n"
            f"📅 {formatted_date}\n"
            f"🕐 {slot}\n"
            f"👤 {name}\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"❌ Отменить {formatted_date} {slot}",
                callback_data=f"cancel_{booking_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="back")
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ОТМЕНА
# =========================

async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    booking_id = int(query.data.replace("cancel_", ""))

    user_id = update.effective_user.id

    deleted = delete_booking(
        booking_id,
        user_id
    )

    if deleted:

        await query.edit_message_text(
            "✅ Бронирование отменено.",
            reply_markup=main_keyboard()
        )

    else:

        await query.edit_message_text(
            "❌ Не удалось отменить бронирование.",
            reply_markup=main_keyboard()
        )


# =========================
# НАЗАД
# =========================

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        f"🎭 <b>Бронирование аудитории «{ROOM_NAME}»</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================
# ОБРАБОТЧИКИ КНОПОК
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    data = query.data

    if data == "book":
        await show_booking(update, context)

    elif data.startswith("date_"):
        await show_times(update, context)

    elif data.startswith("time_"):
        await choose_time(update, context)

    elif data == "my_bookings":
        await my_bookings(update, context)

    elif data.startswith("cancel_"):
        await cancel_booking(update, context)

    elif data == "back":
        await back(update, context)

    elif data == "occupied":
        await query.answer(
            "Это время уже занято.",
            show_alert=True
        )


# =========================
# ЗАПУСК
# =========================

def main():

    if not BOT_TOKEN:
        raise ValueError(
            "Не найден BOT_TOKEN. Добавьте токен в Replit Secrets."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_name
        )
    )

    print("Бот запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
