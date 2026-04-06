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
from telegram.error import BadRequest

# -------- LOGGING --------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------- ENV VARS --------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# -------- DATABASE --------
try:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client["telegram_bot"]
    collection = db["files"]
    # Check connection
    client.admin.command('ping')
    logger.info("✅ MongoDB Connected!")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Error: {e}")

# -------- FLASK --------
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot is running"
def run_web(): app_web.run(host='0.0.0.0', port=PORT)

# -------- UTILS --------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300) # 5 minutes
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception: pass

# -------- HANDLERS --------
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file_id = None
    f_type = None

    if msg.photo:
        file_id = msg.photo[-1].file_id
        f_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        f_type = "video"
    elif msg.document:
        file_id = msg.document.file_id
        f_type = "doc"
    else: return

    code = gen_code()
    collection.insert_one({"code": code, "file_id": file_id, "type": f_type})
    
    bot_me = await context.bot.get_me()
    link = f"https://t.me/{bot_me.username}?start={code}"
    await msg.reply_text(f"🔗 Your Permanent Link:\n{link}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        data = collection.find_one({"code": code})
        
        if data:
            await update.message.reply_text("⏳ Deleting in 5 mins...")
            f_id, f_type = data["file_id"], data["type"]
            
            if f_type == "photo":
                sent = await context.bot.send_photo(update.effective_chat.id, f_id)
            elif f_type == "video":
                sent = await context.bot.send_video(update.effective_chat.id, f_id)
            else:
                sent = await context.bot.send_document(update.effective_chat.id, f_id)
            
            asyncio.create_task(delete_later(context.bot, update.effective_chat.id, sent.message_id))
        else:
            await update.message.reply_text("❌ Link expired or invalid.")
    else:
        await update.message.reply_text("👋 Send me a file to generate a link!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, save_file))
    
    Thread(target=run_web, daemon=True).start()
    logger.info("🚀 Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
