import os
import random
import string
import asyncio
import sqlite3
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

# -------- Flask --------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running"

def run_web():
    app_web.run(host='0.0.0.0', port=PORT)

# -------- Database --------
conn = sqlite3.connect("files.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
    code TEXT PRIMARY KEY,
    file_id TEXT,
    file_type TEXT
)
""")
conn.commit()

# -------- Utils --------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# -------- Delete --------
async def delete_later(bot, chat_id, message_id):
    await asyncio.sleep(300)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        pass
    except Exception as e:
        print(e)

# -------- Save file --------
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

    cursor.execute(
        "INSERT INTO files (code, file_id, file_type) VALUES (?, ?, ?)",
        (code, file_id, file_type)
    )
    conn.commit()

    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={code}"

    await msg.reply_text(f"Link:\n{link}")

# -------- Start --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Send file to get link")
        return

    code = context.args[0]

    cursor.execute("SELECT file_id, file_type FROM files WHERE code=?", (code,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("Invalid link")
        return

    file_id, file_type = result

    try:
        if file_type == "photo":
            sent = await context.bot.send_photo(update.effective_chat.id, file_id)
        elif file_type == "video":
            sent = await context.bot.send_video(update.effective_chat.id, file_id)
        else:
            sent = await context.bot.send_document(update.effective_chat.id, file_id)
    except Exception:
        await update.message.reply_text("Failed to send file")
        return

    # Delete after 5 minutes
    asyncio.create_task(
        delete_later(context.bot, update.effective_chat.id, sent.message_id)
    )

# -------- Main --------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        save_file
    ))

    Thread(target=run_web, daemon=True).start()

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
