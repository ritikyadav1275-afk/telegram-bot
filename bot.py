import os
import random
import string
import asyncio
import logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from pymongo import MongoClient
from telegram.error import BadRequest

# -------- LOGGING --------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------- ENV --------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# -------- MongoDB --------
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
collection = db["files"]

# -------- Flask (Keep Alive) --------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running"

def run_web():
    app_web.run(host='0.0.0.0', port=PORT)

# -------- Utils --------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# -------- Delete after 5 min --------
async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted message {message_id}")
    except BadRequest:
        pass
    except Exception as e:
        logger.error(f"Delete error: {e}")

# -------- Save File --------
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return

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

    collection.insert_one({
        "code": code,
        "file_id": file_id,
        "type": file_type
    })

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await msg.reply_text(f"🔗 Your link:\n{link}")

# -------- Start Command --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        data = collection.find_one({"code": code})

        if not data:
            await update.message.reply_text("❌ Invalid or expired link")
            return

        file_id = data["file_id"]
        file_type = data["type"]

        await update.message.reply_text("⏳ This file will delete in 5 minutes")

        try:
            if file_type == "photo":
                sent = await context.bot.send_photo(update.effective_chat.id, file_id)
            elif file_type == "video":
                sent = await context.bot.send_video(update.effective_chat.id, file_id)
            else:
                sent = await context.bot.send_document(update.effective_chat.id, file_id)
            
            # Typo fixed here (sent, not sant)
            asyncio.create_task(
                delete_later(context.bot, update.effective_chat.id, sent.message_id)
            )

        except Exception as e:
            logger.error(f"Send error: {e}")
            await update.message.reply_text("❌ Failed to send file")
    else:
        await update.message.reply_text("👋 Send me a file to get link")

# -------- Main --------
def main():
    if not BOT_TOKEN or not MONGO_URL:
        logger.error("Environment variables BOT_TOKEN or MONGO_URL are missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        save_file
    ))

    # Keep alive thread
    Thread(target=run_web, daemon=True).start()

    logger.info("Bot started successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
