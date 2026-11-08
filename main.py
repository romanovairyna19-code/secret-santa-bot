import os
import sqlite3
import random
import logging
from telegram import Update
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
ContextTypes,
filters,
)
НАСТРОЙКИ
TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {
int(x.strip())
for x in os.environ.get("ADMIN_IDS", "").split(",")
if x.strip()
}
DB_PATH = os.environ.get("DB_PATH", "santa.db")
logging.basicConfig(level=logging.INFO)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS participants (
user_id INTEGER PRIMARY KEY,
name TEXT NOT NULL,
wishes TEXT NOT NULL
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS assignments (
giver INTEGER PRIMARY KEY,
receiver INTEGER NOT NULL
)
""")
db.execute("""
CREATE TABLE IF NOT EXISTS settings (
key TEXT PRIMARY KEY,
value TEXT
)
""")
db.commit()
states = {}
def setting(key, default="open"):
row = db.execute(
"SELECT value FROM settings WHERE key=?", (key,)
).fetchone()
return row[0] if row else default
def set_setting(key, value):
db.execute(
"INSERT OR REPLACE INTO settings VALUES (?, ?)",
(key, value)
)
db.commit()
def is_admin(user_id):
return user_id in ADMIN_IDS
def get_participants():
return db.execute(
"SELECT user_id, name, wishes FROM participants"
).fetchall()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user
existing = db.execute(
"SELECT name FROM participants WHERE user_id=?",
(user.id,)
).fetchone()
if existing:
    await update.message.reply_text(
        f"Привет, {existing[0]}! 🎅\n"
        "Ты уже зарегистрирован(а) в Secret Santa.\n\n"
        "Если хочешь изменить пожелания, напиши /editwishes."
    )
    return

if setting("registration") == "closed":
    await update.message.reply_text(
        "Регистрация уже закрыта. 🎄"
    )
    return

states[user.id] = "name"
await update.message.reply_text(
    "Добро пожаловать в Secret Santa | Our Team! 🎅\n\n"
    "Для регистрации напиши своё имя и фамилию."
)
async def editwishes(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
exists = db.execute(
"SELECT 1 FROM participants WHERE user_id=?",
(user_id,)
).fetchone()
if not exists:
    await update.message.reply_text(
        "Сначала зарегистрируйся командой /start."
    )
    return

if db.execute("SELECT 1 FROM assignments LIMIT 1").fetchone():
    await update.message.reply_text(
        "Жеребьёвка уже проведена. Изменить пожелания нельзя."
    )
    return

states[user_id] = "wishes"
await update.message.reply_text(
    "Напиши свои пожелания к подарку. 🎁"
)
async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
if states.get(user_id) != "wishes":
    await update.message.reply_text(
        "Сейчас пропускать нечего. Используй /start для регистрации."
    )
    return

await save_participant(update, user_id, "Пожеланий нет")
async def save_participant(update, user_id, wishes):
name = states.get(user_id + 0)  # Имя хранится отдельно ниже
participant_name = states.get(("name", user_id), "")
if not participant_name:
    row = db.execute(
        "SELECT name FROM participants WHERE user_id=?",
        (user_id,)
    ).fetchone()
    if row:
        participant_name = row[0]

if not participant_name:
    await update.message.reply_text(
        "Не удалось найти имя. Начни регистрацию заново: /start"
    )
    states.pop(user_id, None)
    return

db.execute(
    "INSERT OR REPLACE INTO participants VALUES (?, ?, ?)",
    (user_id, participant_name, wishes)
)
db.commit()

states.pop(user_id, None)
states.pop(("name", user_id), None)

await update.message.reply_text(
    f"Отлично, {participant_name}! 🎄\n\n"
    "Ты зарегистрирован(а)!\n"
    "Твои пожелания сохранены. Жди жеребьёвку! 🎁"
)
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
value = update.message.text.strip()
if not value:
    return

if states.get(user_id) == "name":
    if len(value) > 80:
        await update.message.reply_text(
            "Имя слишком длинное. Напиши покороче."
        )
        return

    states[user_id] = "wishes"
    states[("name", user_id)] = value

    await update.message.reply_text(
        f"Приятно познакомиться, {value}! ❤️\n\n"
        "Теперь напиши, что ты хотел(а) бы получить в подарок.\n"
        "Можно указать интересы, любимые вещи и идеи.\n\n"
        "Если пожеланий нет, напиши /skip."
    )
    return

if states.get(user_id) == "wishes":
    if len(value) > 1000:
        await update.message.reply_text(
            "Пожелания слишком длинные. Максимум 1000 символов."
        )
        return

    await save_participant(update, user_id, value)
    return

await update.message.reply_text(
    "Используй /start для регистрации или /editwishes для изменения пожеланий."
)
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
f"Твой Telegram ID: {update.effective_user.id}"
)
async def participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not is_admin(update.effective_user.id):
return
people = get_participants()
if not people:
    await update.message.reply_text("Пока никто не зарегистрировался.")
    return

result = "\n".join(
    f"{i}. {person[1]}"
    for i, person in enumerate(people, 1)
)
await update.message.reply_text(
    f"Участники Secret Santa ({len(people)}):\n\n{result}"
)
async def close_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not is_admin(update.effective_user.id):
return
set_setting("registration", "closed")
await update.message.reply_text("🔒 Регистрация закрыта!")
async def open_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not is_admin(update.effective_user.id):
return
set_setting("registration", "open")
await update.message.reply_text("🟢 Регистрация открыта!")
def make_draw(people):
ids = [person[0] for person in people]
# Пытаемся избежать не только своего имени,
# но и обмена подарками друг с другом.
for _ in range(20000):
    receivers = ids[:]
    random.shuffle(receivers)

    if any(a == b for a, b in zip(ids, receivers)):
        continue

    pairs = set(zip(ids, receivers))
    if any((b, a) in pairs for a, b in pairs):
        continue

    return dict(zip(ids, receivers))

# Запасной вариант: исключаем получение собственного имени.
for _ in range(20000):
    receivers = ids[:]
    random.shuffle(receivers)
    if all(a != b for a, b in zip(ids, receivers)):
        return dict(zip(ids, receivers))

return None
async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not is_admin(update.effective_user.id):
return
people = get_participants()

if len(people) < 3:
    await update.message.reply_text(
        "Для жеребьёвки нужно минимум 3 участника."
    )
    return

if db.execute("SELECT 1 FROM assignments LIMIT 1").fetchone():
    await update.message.reply_text(
        "Жеребьёвка уже проводилась! Повторный запуск запрещён."
    )
    return

result = make_draw(people)

if not result:
    await update.message.reply_text(
        "Не удалось провести жеребьёвку. Попробуй ещё раз."
    )
    return

by_id = {person[0]: person for person in people}

db.executemany(
    "INSERT INTO assignments VALUES (?, ?)",
    list(result.items())
)
db.commit()

delivered = 0
failed = 0

for giver_id, receiver_id in result.items():
    receiver = by_id[receiver_id]
    message = (
        "🎅 ТАЙНАЯ ЖЕРЕБЬЁВКА СОСТОЯЛАСЬ!\n\n"
        f"Ты — Тайный Санта для: {receiver[1]} 🎁\n\n"
        f"Пожелания получателя:\n{receiver[2]}\n\n"
        "Помни: сохраняй тайну до праздника! 🤫"
    )

    try:
        await context.bot.send_message(
            chat_id=giver_id,
            text=message
        )
        delivered += 1
    except Exception:
        failed += 1
        logging.exception("Не удалось отправить сообщение участнику")

await update.message.reply_text(
    "🎄 Жеребьёвка проведена!\n\n"
    f"Участников: {len(people)}\n"
    f"Сообщений отправлено: {delivered}\n"
    f"Не доставлено: {failed}\n\n"
    "Если сообщение не пришло, участнику нужно открыть бота "
    "и нажать /start."
)
