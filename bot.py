import os
import asyncio
import logging
import random
import string
import requests
from flask import Flask
from threading import Thread

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)

from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

ADMIN_ID = 947542421
FORCE_CHANNEL = "@Allmyfaul"

# 💰 SHORTENER API
SHORTENER_API = "1b1f76293dbbf0c942d52b625"

client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
files = db["files"]
users = db["users"]
banned = db["banned"]

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Running"

def run_web():
    app_web.run(host="0.0.0.0", port=10000)

def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# ---------- SHORTENER ----------
def shorten_link(url):
    try:
        api_url = f"https://shrinkme.io/api?api={SHORTENER_API}&url={url}"
        res = requests.get(api_url).json()

        if res.get("status") == "success":
            return res.get("shortenedUrl")
        return url
    except:
        return url

# ---------- FORCE JOIN ----------
async def check_join(update, context):
    try:
        member = await context.bot.get_chat_member(FORCE_CHANNEL, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ---------- AUTO DELETE ----------
async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if banned.find_one({"user_id": user_id}):
        await update.message.reply_text("🚫 You are banned")
        return

    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id})

    # FORCE JOIN
    if not await check_join(update, context):
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}")],
            [InlineKeyboardButton("✅ Joined", callback_data="check_join")]
        ]
        await update.message.reply_text("🚫 Join channel first", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # LINK OPEN
    if context.args:
        code = context.args[0]
        data = files.find_one({"code": code})

        if not data:
            await update.message.reply_text("❌ Invalid link")
            return

        await update.message.reply_text("⏳ File will delete in 5 minutes")

        if data["type"] == "photo":
            sent = await context.bot.send_photo(update.effective_chat.id, data["file_id"])
        elif data["type"] == "video":
            sent = await context.bot.send_video(update.effective_chat.id, data["file_id"])
        else:
            sent = await context.bot.send_document(update.effective_chat.id, data["file_id"])

        asyncio.create_task(delete_later(context.bot, update.effective_chat.id, sent.message_id))
        return

    # MENU
    keyboard = [
        [InlineKeyboardButton("📤 Upload", callback_data="upload")],
        [InlineKeyboardButton("📦 Batch", callback_data="batch")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])

    await update.message.reply_text("🚀 Welcome!", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- SAVE FILE ----------
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if msg.photo:
        file_id = msg.photo[-1].file_id
        ftype = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        ftype = "video"
    elif msg.document:
        file_id = msg.document.file_id
        ftype = "document"
    else:
        return

    code = gen_code()

    files.insert_one({"code": code, "file_id": file_id, "type": ftype})

    bot = await context.bot.get_me()
    original_link = f"https://t.me/{bot.username}?start={code}"

    # 💰 SHORTENED LINK
    short_link = shorten_link(original_link)

    await msg.reply_text(f"💰 Download Link:\n{short_link}")

# ---------- CALLBACK BUTTONS ----------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id

    if query.data == "upload":
        await query.edit_message_text("📤 Send file")

    elif query.data == "batch":
        await query.edit_message_text("📦 Send files (basic batch)")

    elif query.data == "help":
        await query.edit_message_text("Send file → get link → earn 💰")

    elif query.data == "admin_panel" and uid == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📊 Users", callback_data="users")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]
        ]
        await query.edit_message_text("👑 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "users":
        total = users.count_documents({})
        await query.edit_message_text(f"👥 Users: {total}")

    elif query.data == "broadcast":
        context.user_data["broadcast"] = True
        await query.edit_message_text("Send message")

# ---------- JOIN CHECK ----------
async def join_check(update, context):
    query = update.callback_query
    await query.answer()

    if await check_join(update, context):
        await query.message.delete()
        await query.message.reply_text("✅ Now use bot")
    else:
        await query.answer("❌ Join first", show_alert=True)

# ---------- BROADCAST ----------
async def handle_broadcast(update, context):
    if not context.user_data.get("broadcast"):
        return

    count = 0
    for u in users.find():
        try:
            await context.bot.send_message(u["user_id"], update.message.text)
            count += 1
        except:
            pass

    context.user_data["broadcast"] = False
    await update.message.reply_text(f"Sent {count}")

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CallbackQueryHandler(join_check, pattern="check_join"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    app.add_handler(MessageHandler(filters.ALL, save_file))

    Thread(target=run_web, daemon=True).start()

    print("🚀 Bot Started")
    app.run_polling()

if __name__ == "__main__":
    main()
