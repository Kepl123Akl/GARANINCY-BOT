import telebot
import datetime
import os
from dotenv import load_dotenv

# ==================== НАСТРОЙКИ ====================
load_dotenv()

bot = telebot.TeleBot(os.getenv("TOKEN"))

# Список всех записанных людей
booked_users = {}

# Записанные даты (calendar.id: (Имя, chat_id))
calendar = {}

# ================================================

def is_working_time():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start <= now <= end


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для бронирования аудитории.\n"
        "Пиши /book — и я покажу кнопки с временем."
    )


@bot.message_handler(commands=['book'])
def book(message):
    if not is_working_time():
        bot.send_message(message.chat.id, "❌ Запись недоступна: время за пределами 8:00–20:00.")
        return

    bot.send_message(message.chat.id, "📝 Напиши своё имя (например: Иван Иванов):")
    bot.register_next_step_handler(message, get_name)


def get_name(message):
    name = message.text.strip()
    booked_users[message.chat.id] = name

    keyboard = telebot.types.InlineKeyboardMarkup(row_width=3)
    times = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
    buttons = [telebot.types.InlineKeyboardButton(text=t, callback_data=f"book_{t}") for t in times]

    for i in range(0, len(buttons), 3):
        keyboard.add(*buttons[i:i+3])

    bot.send_message(
        message.chat.id,
        "📅 Выбери время (каждое окно — 1 час):\nС 08:00 до 19:00",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("book_"))
def handle_time_selection(call):
    time_str = call.data.split("_")[1]
    dt = datetime.datetime.strptime(time_str, "%H:%M").replace(
        year=datetime.datetime.now().year,
        month=datetime.datetime.now().month,
        day=datetime.datetime.now().day
    )
    calendar_id = dt.timestamp()

    if calendar_id in calendar:
        bot.answer_callback_query(call.id, "❌ Эта дата уже занята!", show_alert=True)
        return

    calendar[calendar_id] = (booked_users.get(call.from_user.id, "Неизвестно"), call.from_user.id)

    # === Сообщение ВСЕМ участникам чата ===
    busy_start = dt
    busy_end = dt + datetime.timedelta(hours=1)
    busy_text = f"🔴 <b>АУДИТОРИЯ ЗАНЯТА!</b>\n\n🔹 С {busy_start.strftime('%H:%M')} до {busy_end.strftime('%H:%M')} идёт репетиция.\n✅ Не подходите к дверям."
    try:
        bot.send_message(call.message.chat.id, busy_text, parse_mode="HTML")
    except Exception:
        pass

    bot.answer_callback_query(call.id, "✅ Запись подтверждена!")
    bot.edit_message_text(
        f"✅ Запись подтверждена!\n\nИмя: {calendar[calendar_id][0]}\nДата: {dt.strftime('%d.%m.%Y %H:%M')}\n\n🗓️ Календарь обновлён — это время теперь недоступно.",
        call.message.chat.id,
        call.message.message_id
    )


@bot.message_handler(commands=['rv'])
def send_rv(message):
    if not calendar:
        bot.send_message(message.chat.id, "📭 Пока никто ничего не забронировал.")
        return

    text = "📢 <b>Список всех бронирований</b>\n\n"
    for ts, (name, chat_id) in calendar.items():
        dt = datetime.datetime.fromtimestamp(ts)
        text += f"• {name} — {dt.strftime('%d.%m.%Y %H:%M')}\n"

    text += "\n<b>Все записи отправлены в личные чаты!</b>"

    for chat_id in list(calendar.values()):
        try:
            bot.send_message(chat_id[1], text, parse_mode="HTML")
        except Exception:
            pass

    bot.send_message(message.chat.id, "✅ Сообщение с полным списком отправлено всем!")


@bot.message_handler(commands=['delete'])
def delete_all(message):
    if not calendar:
        bot.send_message(message.chat.id, "📭 Нет записей для отмены.")
        return

    for ts, (_, chat_id) in calendar.items():
        try:
            dt = datetime.datetime.fromtimestamp(ts)
            bot.send_message(chat_id, f"❌ Ваша запись на {dt.strftime('%d.%m.%Y %H:%M')} была отменена администратором.")
        except Exception:
            pass

    calendar.clear()
    booked_users.clear()
    bot.send_message(message.chat.id, "✅ Все записи успешно отменены.")


if __name__ == "__main__":
    print("✅ Бот запущен и работает в группах и каналах!")
    bot.polling(none_stop=True)
