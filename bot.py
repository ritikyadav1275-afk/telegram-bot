import os, random, string, asyncio, logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
# Render provides the PORT automatically
PORT = int(os.environ.get("PORT", 10000))

# --- DATABASE ---
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
collection = db["files"]

# --- WEB SERVER (Fixes the Timeout) ---
app = Flask(__name__)
@app.route('/')
def home(): return "OK"

def run_flask():
    # Use 0.0.0.0 to allow Render to bind to the port
    app.run(host='0.0.0.0', port=PORT)

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        data = collection.find_one({"code": context.args[0]})
        if data:
            if data["type"] == "photo": await context.bot.send_photo(update.chat_id, data["file_id"])
            elif data["type"] == "video": await context.bot.send_video(update.chat_id, data["file_id"])
            else: await context.bot.send_document(update.chat_id, data["file_id"])
        else: await update.message.reply_text("❌ Link Invalid")
    else: await update.message.reply_text("👋 Send a file!")

async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo: fid, ft = msg.photo[-1].file_id, "photo"
    elif msg.video: fid, ft = msg.video.file_id, "video"
    elif msg.document: fid, ft = msg.document.file_id, "doc"
    else: return
    
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    collection.insert_one({"code": code, "file_id": fid, "type": ft})
    me = await context.bot.get_me()
    await msg.reply_text(f"🔗 Link:\nhttps://t.me/{me.username}?start={code}")

def main():
    # 1. Start Flask first so Render sees a live port immediately
    Thread(target=run_flask, daemon=True).start()
    
    # 2. Start the Bot
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, save_file))
    
    logger.info("🚀 Bot and Web Server started...")
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
