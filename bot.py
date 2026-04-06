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
PORT = int(os.environ.get("PORT", 10000))

# --- DB SETUP ---
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = client["telegram_bot"]
collection = db["files"]

# --- WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Online"
def run_web(): app.run(host='0.0.0.0', port=PORT)

# --- LOGIC ---
async def delete_later(bot, chat_id, msg_id):
    await asyncio.sleep(300)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        data = collection.find_one({"code": context.args[0]})
        if data:
            await update.message.reply_text("⏳ Deleting in 5 mins")
            if data["type"] == "photo": s = await context.bot.send_photo(update.chat_id, data["file_id"])
            elif data["type"] == "video": s = await context.bot.send_video(update.chat_id, data["file_id"])
            else: s = await context.bot.send_document(update.chat_id, data["file_id"])
            asyncio.create_task(delete_later(context.bot, update.chat_id, s.message_id))
        else: await update.message.reply_text("❌ Link Invalid")
    else: await update.message.reply_text("👋 Send a file!")

def main():
    # Verify DB connection on start
    try:
        client.admin.command('ping')
        logger.info("✅ DB Connected")
    except Exception as e:
        logger.error(f"❌ DB Error: {e}")

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, save_file))
    
    Thread(target=run_web, daemon=True).start()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
