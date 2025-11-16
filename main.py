# main.py
import os
import json
from datetime import datetime
from flask import Flask
import telebot
from telebot import types
import threading

# ====== Настройки ======
TOKEN = "7974881474:AAHOzEfo2pOxDdznJK-ED9tGikw6Yl7dZY"
OWNER_ID = 1470389051
DATA_FILE = "reviews_data.json"
# =======================

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ====== База відгуків ======
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reviews_db = json.load(f)
else:
    reviews_db = {"admins": {}, "pending": {}}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews_db, f, ensure_ascii=False, indent=2)

def normalize_tag(tag: str) -> str:
    return tag.strip().lower()

def ensure_admin_exists(tag_raw: str):
    key = normalize_tag(tag_raw)
    if key not in reviews_db["admins"]:
        reviews_db["admins"][key] = {"display": tag_raw.strip(), "reviews": []}
        save_db()
    return key

def is_owner(uid):
    return int(uid) == OWNER_ID

# ====== /start ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⭐ Оставить отзыв", "📊 Репутация")
    if is_owner(message.from_user.id):
        kb.add("🛠️ Админ-меню")
    
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот отзывов и репутации 💌\n\n"
        "— «⭐ Оставить отзыв» чтобы оценить администратора.\n"
        "— «📊 Репутация» чтобы посмотреть оценки и отзывы.",
        reply_markup=kb
    )

# ====== Оставить отзыв ======
@bot.message_handler(func=lambda m: m.text == "⭐ Оставить отзыв")
def rate_start(message):
    bot.send_message(message.chat.id, "Напишите #тег администратора, например: #шерлок")
    bot.register_next_step_handler(message, rate_admin)

def rate_admin(message):
    tag = message.text.strip()
    if not tag.startswith("#"):
        bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите #тег, начиная с #, например #шерлок")
        return
    key = ensure_admin_exists(tag)
    kb = types.InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        kb.add(types.InlineKeyboardButton("⭐"*i, callback_data=f"rate|{key}|{i}"))
    bot.send_message(message.chat.id, f"Вы выбрали {tag}. Выберите количество звёзд:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rate|"))
def rate_callback(call):
    _, key, stars = call.data.split("|")
    stars = int(stars)
    reviews_db["pending"][str(call.from_user.id)] = {"key": key, "stars": stars}
    save_db()
    bot.send_message(call.message.chat.id, "Теперь напишите отзыв или '-' чтобы пропустить")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: str(m.from_user.id) in reviews_db["pending"])
def save_review(message):
    uid = str(message.from_user.id)
    p = reviews_db["pending"].pop(uid)
    key, stars = p["key"], p["stars"]
    text = "" if message.text == "-" else message.text
    entry = {
        "user": message.from_user.username or f"id{uid}",
        "stars": stars,
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    reviews_db["admins"][key]["reviews"].append(entry)
    save_db()
    bot.send_message(message.chat.id, f"Спасибо! Отзыв сохранён. {'⭐'*stars}")

# ====== Репутация ======
@bot.message_handler(func=lambda m: m.text == "📊 Репутация")
def show_rates(message):
    if not reviews_db["admins"]:
        bot.send_message(message.chat.id, "Пока нет отзывов.")
        return
    txt = ""
    for key, info in reviews_db["admins"].items():
        reviews = info["reviews"]
        if not reviews:
            continue
        avg = round(sum(r["stars"] for r in reviews) / len(reviews), 2)
        txt += f"{info['display']} — {'⭐'*int(avg)} ({avg})\n"
        for idx, r in enumerate(reviews):
            txt += f"   • {idx+1}. {r['user']} — {'⭐'*r['stars']} {r['text']}\n"
        txt += "\n"
    bot.send_message(message.chat.id, txt)

# ====== Админ-меню ======
@bot.message_handler(func=lambda m: m.text == "🛠️ Админ-меню" and is_owner(m.from_user.id))
def admin_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ Удалить отзыв", "⬅️ Назад")
    bot.send_message(message.chat.id, "Админ-меню:", reply_markup=kb)

# ====== Удаление отзывов ======
@bot.message_handler(func=lambda m: m.text == "❌ Удалить отзыв" and is_owner(m.from_user.id))
def delete_review_menu(message):
    if not reviews_db["admins"]:
        bot.send_message(message.chat.id, "Пока нет отзывов для удаления.")
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for key, info in reviews_db["admins"].items():
        if info["reviews"]:
            kb.add(info["display"])
    kb.add("⬅️ Назад")
    bot.send_message(message.chat.id, "Выберите администратора, у которого хотите удалить отзыв:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in [info["display"] for info in reviews_db["admins"].values()] and is_owner(m.from_user.id))
def select_admin_for_delete(message):
    admin_tag = message.text
    key = normalize_tag(admin_tag)
    reviews = reviews_db["admins"][key]["reviews"]
    if not reviews:
        bot.send_message(message.chat.id, "Нет отзывов для удаления.")
        return
    kb = types.InlineKeyboardMarkup()
    for idx, r in enumerate(reviews):
        kb.add(types.InlineKeyboardButton(f"{idx+1}. {r['user']} — {'⭐'*r['stars']}", callback_data=f"del|{key}|{idx}"))
    bot.send_message(message.chat.id, "Выберите отзыв для удаления:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def delete_review_callback(call):
    _, key, idx = call.data.split("|")
    idx = int(idx)
    review = reviews_db["admins"][key]["reviews"].pop(idx)
    save_db()
    bot.answer_callback_query(call.id, f"Отзыв от {review['user']} удален ✅")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

# ====== Flask для Keep Alive ======
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive! 🚀"

def run():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run).start()

# ====== Запуск бота ======
def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
