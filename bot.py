import os
import asyncio
import logging
import random
import string
from flask import Flask
from threading import Thread

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from pymongo import MongoClient

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO)

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = 947542421  # your id

# ---------- DB ----------
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
files = db["files"]
users = db["users"]

# ---------- FLASK ----------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Running"

def run_web():
    app_web.run(host="0.0.0.0", port=10000)

# ---------- UTILS ----------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# ---------- AUTO DELETE ----------
async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

# ---------- START (MERGED) ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # save user
    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id})

    # 👉 LINK OPEN
    if context.args:
        code = context.args[0]

        data = files.find_one({"code": code})

        if not data:
            await update.message.reply_text("❌ Invalid link")
            return

        file_id = data["file_id"]
        file_type = data["type"]

        await update.message.reply_text("⏳ File will delete in 5 minutes")

        if file_type == "photo":
            sent = await context.bot.send_photo(update.effective_chat.id, file_id)
        elif file_type == "video":
            sent = await context.bot.send_video(update.effective_chat.id, file_id)
        else:
            sent = await context.bot.send_document(update.effective_chat.id, file_id)

        asyncio.create_task(delete_later(context.bot, update.effective_chat.id, sent.message_id))
        return

    # 👉 NORMAL MENU
    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data="upload")],
        [InlineKeyboardButton("📦 Batch Mode", callback_data="batch")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]

    await update.message.reply_text(
        "👋 Welcome!\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- SAVE FILE ----------
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    file_id = None
    file_type = None

    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"
    else:
        return

    code = gen_code()

    files.insert_one({
        "code": code,
        "file_id": file_id,
        "type": file_type
    })

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await msg.reply_text(f"✅ Saved!\n🔗 Link:\n{link}")

# ---------- BROADCAST ----------
broadcast_mode = {}

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    broadcast_mode[update.effective_user.id] = True
    await update.message.reply_text("📢 Send message to broadcast")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in broadcast_mode:
        return

    all_users = users.find()
    count = 0

    for user in all_users:
        try:
            await context.bot.send_message(user["user_id"], update.message.text)
            count += 1
        except:
            pass

    broadcast_mode.pop(user_id)

    await update.message.reply_text(f"✅ Sent to {count} users")

# ---------- MAIN ----------
def main():
    if not BOT_TOKEN or not MONGO_URL:
        print("Missing ENV")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ✅ CORRECT ORDER
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        save_file
    ))

    Thread(target=run_web, daemon=True).start()

    print("🚀 Bot Started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
