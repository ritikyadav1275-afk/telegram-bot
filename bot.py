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
# Ensure these match your Render Environment Variables exactly
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# --- DATABASE ---
try:
    client = MongoClient(MONGO_URL)
    db = client["telegram_bot"]
    collection = db["files"]
    client.admin.command('ping')
    logger.info("✅ MongoDB Connected")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Error: {e}")

# --- WEB SERVER (Fixes Render "Timed Out" Error) ---
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is Live", 200

def run_web():
    # Bind to 0.0.0.0 so Render can detect the port
    app.run(host='0.0.0.0', port=PORT)

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        file_data = collection.find_one({"code": code})
        
        if file_data:
            f_id = file_data["file_id"]
            f_type = file_data["type"]
            
            await update.message.reply_text("⏳ Sending file...")
            
            if f_type == "photo":
                await context.bot.send_photo(update.chat_id, f_id)
            elif f_type == "video":
                await context.bot.send_video(update.chat_id, f_id)
            else:
                await context.bot.send_document(update.chat_id, f_id)
        else:
            await update.message.reply_text("❌ Invalid or expired link.")
    else:
        await update.message.reply_text("👋 Hello! Send me a file to get a link.")

async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Generate unique 8-character code
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Save to MongoDB
    collection.insert_one({
        "code": code,
        "file_id": file_id,
        "type": file_type
    })

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    await msg.reply_text(f"✅ File Saved!\n🔗 Link: {link}")

def main():
    # Start the Web Server in a background thread
    Thread(target=run_web, daemon=True).start()
    
    # Initialize the Bot
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_upload))
    
    logger.info("🚀 Bot starting...")
    # drop_pending_updates prevents the bot from crashing on old data
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
