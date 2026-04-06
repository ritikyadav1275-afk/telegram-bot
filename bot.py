import os
import random
import string
import asyncio
import logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# --- DATABASE ---
try:
    client = MongoClient(MONGO_URL)
    db = client["telegram_bot"]
    collection = db["files"]
    logger.info("✅ MongoDB Connected")
except Exception as e:
    logger.error(f"❌ DB Error: {e}")

# --- WEB SERVER (Fixes Render Timeout) ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is Live", 200

def run_web():
    app.run(host='0.0.0.0', port=PORT)

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        file_data = collection.find_one({"code": context.args[0]})
        if file_data:
            f_id, f_type = file_data["file_id"], file_data["type"]
            if f_type == "photo": await context.bot.send_photo(update.chat_id, f_id)
            elif f_type == "video": await context.bot.send_video(update.chat_id, f_id)
            else: await context.bot.send_document(update.chat_id, f_id)
        else:
            await update.message.reply_text("❌ Invalid link.")
    else:
        await update.message.reply_text("👋 Send a file to get a link!")

async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo: fid, ft = msg.photo[-1].file_id, "photo"
    elif msg.video: fid, ft = msg.video.file_id, "video"
    elif msg.document: fid, ft = msg.document.file_id, "document"
    else: return

    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    collection.insert_one({"code": code, "file_id": fid, "type": ft})
    
    bot_info = await context.bot.get_me()
    await msg.reply_text(f"✅ Saved! Link: https://t.me/{bot_info.username}?start={code}")

def main():
    Thread(target=run_web, daemon=True).start()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_upload))
    
    logger.info("🚀 Bot starting...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
