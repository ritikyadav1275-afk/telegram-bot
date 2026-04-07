import os
import random
import string
import asyncio
from flask import Flask
from threading import Thread

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from pymongo import MongoClient

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

ADMIN_ID = 947542421

# ================== DB ==================
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
collection = db["files"]

# ================== WEB ==================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running!"

def run_web():
    app_web.run(host='0.0.0.0', port=PORT)

# ================== UTIL ==================
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# ================== DELETE ==================
async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        data = collection.find_one({"code": code})

        if not data:
            await update.message.reply_text("❌ Invalid link")
            return

        # Batch
        if "batch" in data:
            await update.message.reply_text("⏳ Files will delete in 5 minutes")

            for file_id, file_type in data["batch"]:
                if file_type == "photo":
                    sent = await context.bot.send_photo(update.effective_chat.id, file_id)
                elif file_type == "video":
                    sent = await context.bot.send_video(update.effective_chat.id, file_id)
                else:
                    sent = await context.bot.send_document(update.effective_chat.id, file_id)

                asyncio.create_task(delete_later(context.bot, update.effective_chat.id, sent.message_id))
            return

        # Single file
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

    else:
        keyboard = [
            ["📤 Upload File"],
            ["📦 Batch Mode"],
            ["ℹ️ Help"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "👋 Welcome!\nChoose an option:",
            reply_markup=reply_markup
        )

# ================== MENU ==================
user_batch = {}

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📤 Upload File":
        await update.message.reply_text("📁 Send me any file")

    elif text == "📦 Batch Mode":
        if update.effective_user.id != ADMIN_ID:
            return
        user_batch[update.effective_user.id] = []
        await update.message.reply_text("📥 Send files then type /done")

    elif text == "ℹ️ Help":
        await update.message.reply_text(
            "📌 How to use:\n\n"
            "1. Send file → get link\n"
            "2. Batch Mode → multiple files\n"
            "3. Files auto delete in 5 minutes"
        )

# ================== SAVE FILE ==================
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

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

    collection.insert_one({
        "code": code,
        "file_id": file_id,
        "type": file_type
    })

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await msg.reply_text(f"✅ Saved!\n🔗 Link:\n{link}")

# ================== BATCH ==================
async def collect_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in user_batch:
        return

    msg = update.message

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

    user_batch[update.effective_user.id].append((file_id, file_type))

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    files = user_batch.get(update.effective_user.id)

    if not files:
        await update.message.reply_text("❌ No files")
        return

    code = gen_code()

    collection.insert_one({
        "code": code,
        "batch": files
    })

    del user_batch[update.effective_user.id]

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await update.message.reply_text(f"🔗 Batch Link:\n{link}")

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    app.add_handler(MessageHandler(filters.ALL, collect_batch))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        save_file
    ))

    Thread(target=run_web, daemon=True).start()

    print("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
