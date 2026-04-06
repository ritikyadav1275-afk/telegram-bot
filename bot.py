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

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# --- DATABASE SETUP ---
try:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client["telegram_bot"]
    collection = db["files"]
    # Verify connection
    client.admin.command('ping')
    logger.info("✅ MongoDB Connected Successfully")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Failed: {e}")

# --- WEB SERVER (Fixes Render Timeouts) ---
app_web = Flask(__name__)

@app_web.route('/')
def health_check():
    return "Bot is running", 200

def run_web():
    # Bind to 0.0.0.0 so Render can detect the live port
    app_web.run(host='0.0.0.0', port=PORT)

# --- UTILITIES ---
def generate_random_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def delete_message_later(bot, chat_id, message_id):
    await asyncio.sleep(300)  # Wait 5 minutes
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id}")
    except Exception:
        pass

# --- TELEGRAM HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user clicked a deep link (?start=CODE)
    if context.args:
        code = context.args[0]
        file_data = collection.find_one({"code": code})

        if not file_data:
            await update.message.reply_text("❌ Invalid or expired link.")
            return

        await update.message.reply_text("⏳ Sending file... It will be deleted in 5 minutes.")
        
        f_id = file_data["file_id"]
        f_type = file_data["type"]

        try:
            if f_type == "photo":
                sent_msg = await context.bot.send_photo(update.effective_chat.id, f_id)
            elif f_type == "video":
                sent_msg = await context.bot.send_video(update.effective_chat.id, f_id)
            else:
                sent_msg = await context.bot.send_document(update.effective_chat.id, f_id)

            # Fixed "sant" typo to "sent_msg"
            asyncio.create_task(
                delete_message_later(context.bot, update.effective_chat.id, sent_msg.message_id)
            )
        except Exception as e:
            logger.error(f"Failed to send file: {e}")
            await update.message.reply_text("❌ Error: Could not retrieve file.")
    else:
        await update.message.reply_text("👋 Hello! Send me a file (photo, video, or doc) to get a link.")

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    code = generate_random_code()
    
    # Save to MongoDB
    collection.insert_one({
        "code": code,
        "file_id": file_id,
        "type": file_type
    })

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    
    await msg.reply_text(f"✅ File Saved!\n🔗 Your Link:\n{link}")

# --- MAIN EXECUTION ---
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing in environment variables!")
        return

    # Initialize Bot Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        handle_file_upload
    ))

    # Start Flask in a background thread
    Thread(target=run_web, daemon=True).start()

    logger.info("🚀 Starting Bot Polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
