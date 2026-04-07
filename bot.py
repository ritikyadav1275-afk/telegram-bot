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
    filters,
    CallbackQueryHandler
)

from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

ADMIN_ID = 947542421
FORCE_CHANNEL = "@Allmyfaul"

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

    await update.message.reply_text("👋 Welcome!", reply_markup=InlineKeyboardMarkup(keyboard))

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
    link = f"https://t.me/{bot.username}?start={code}"

    await msg.reply_text(f"✅ Link:\n{link}")

# ---------- BATCH ----------
batch_mode = {}

async def batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    batch_mode[update.effective_user.id] = []
    await update.message.reply_text("📦 Send files then type /done")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in batch_mode or not batch_mode[user_id]:
        await update.message.reply_text("❌ No files")
        return

    code = gen_code()

    files.insert_one({
        "code": code,
        "batch": batch_mode[user_id]
    })

    del batch_mode[user_id]

    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={code}"

    await update.message.reply_text(f"📦 Batch Link:\n{link}")

# ---------- HANDLE FILE IN BATCH ----------
async def handle_batch_files(update, context):
    user_id = update.effective_user.id

    if user_id not in batch_mode:
        return

    msg = update.message

    if msg.photo:
        batch_mode[user_id].append(("photo", msg.photo[-1].file_id))
    elif msg.video:
        batch_mode[user_id].append(("video", msg.video.file_id))
    elif msg.document:
        batch_mode[user_id].append(("document", msg.document.file_id))

# ---------- CALLBACK ----------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "upload":
        await query.message.reply_text("📤 Send file")
    elif query.data == "batch":
        await batch(update, context)
    elif query.data == "help":
        await query.message.reply_text("Send file to get link")

# ---------- JOIN BUTTON ----------
async def join_check(update, context):
    query = update.callback_query
    await query.answer()

    if await check_join(update, context):
        await query.message.delete()
        await query.message.reply_text("✅ Now use bot")
    else:
        await query.answer("❌ Join first", show_alert=True)

# ---------- ADMIN ----------
async def broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("Send message")

    context.user_data["broadcast"] = True

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

async def stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    total = users.count_documents({})
    await update.message.reply_text(f"👥 Users: {total}")

async def ban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    uid = int(context.args[0])
    banned.insert_one({"user_id": uid})
    await update.message.reply_text("Banned")

async def unban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    uid = int(context.args[0])
    banned.delete_one({"user_id": uid})
    await update.message.reply_text("Unbanned")

# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))

    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CallbackQueryHandler(join_check, pattern="check_join"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    app.add_handler(MessageHandler(filters.ALL, handle_batch_files))
    app.add_handler(MessageHandler(filters.ALL, save_file))

    Thread(target=run_web, daemon=True).start()
    app.run_polling()

if __name__ == "__main__":
    main()
