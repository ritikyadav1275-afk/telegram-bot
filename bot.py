import os
import random
import string
import asyncio
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

# -------- ENV --------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
PORT = int(os.environ.get("PORT", 10000))

# -------- MongoDB --------
client = MongoClient(MONGO_URL)
db = client["telegram_bot"]
collection = db["files"]

# -------- Flask --------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot running"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

# -------- Utils --------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# -------- TEMP STORAGE (for batch) --------
user_files = {}

# -------- Save File --------
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = update.effective_user.id

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

    if user_id not in user_files:
        user_files[user_id] = []

    user_files[user_id].append({
        "file_id": file_id,
        "type": file_type
    })

    await msg.reply_text("✅ File added! Send more or type /done")

# -------- DONE (Generate Batch Link) --------
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_files or not user_files[user_id]:
        await update.message.reply_text("❌ No files added")
        return

    code = gen_code()

    collection.insert_one({
        "code": code,
        "files": user_files[user_id]
    })

    user_files[user_id] = []

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await update.message.reply_text(f"🔗 Batch Link:\n{link}")

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]

        data = collection.find_one({"code": code})

        if not data:
            await update.message.reply_text("❌ Invalid link")
            return

        await update.message.reply_text("⏳ Files will delete in 5 minutes")

        # MULTIPLE FILES
        if "files" in data:
            for file in data["files"]:
                try:
                    if file["type"] == "photo":
                        sent = await context.bot.send_photo(update.effective_chat.id, file["file_id"])
                    elif file["type"] == "video":
                        sent = await context.bot.send_video(update.effective_chat.id, file["file_id"])
                    else:
                        sent = await context.bot.send_document(update.effective_chat.id, file["file_id"])

                    asyncio.create_task(
                        delete_later(context.bot, update.effective_chat.id, sent.message_id)
                    )

                except Exception as e:
                    print(e)

        else:
            await update.message.reply_text("❌ No files found")

    else:
        await update.message.reply_text("👋 Send files then type /done")

# -------- MAIN --------
def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return

    if not MONGO_URL:
        print("MONGO_URL missing")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done))

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        save_file
    ))

    Thread(target=run_web, daemon=True).start()

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
