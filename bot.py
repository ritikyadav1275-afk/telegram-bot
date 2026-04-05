import random
import string
import asyncio
import sqlite3
import os
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🌐 Web server (for uptime)
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is alive!"

def run():
    app_web.run(host='0.0.0.0', port=10000)

Thread(target=run).start()

# 💾 Database
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

def gen():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m:
        return

    file_id = None
    file_type = None

    if m.video:
        file_id = m.video.file_id
        file_type = "video"
    elif m.document:
        file_id = m.document.file_id
        file_type = "document"
    elif m.photo:
        file_id = m.photo[-1].file_id
        file_type = "photo"

    if file_id:
        code = gen()
        cursor.execute("INSERT INTO files VALUES (?, ?, ?)", (code, file_id, file_type))
        conn.commit()

        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"

        await m.reply_text(f"🔗 {link}")

async def delete_after(chat_id, message_id, context):
    await asyncio.sleep(300)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]

        cursor.execute("SELECT file_id, file_type FROM files WHERE code=?", (code,))
        result = cursor.fetchone()

        if result:
            file_id, file_type = result

            await update.message.reply_text(
                "⚠️ This file will be deleted in 5 minutes.\nSave or forward now!"
            )

            if file_type == "photo":
                sent = await update.message.reply_photo(file_id)
            elif file_type == "video":
                sent = await update.message.reply_video(file_id)
            else:
                sent = await update.message.reply_document(file_id)

            asyncio.create_task(delete_after(update.message.chat_id, sent.message_id, context))
        else:
            await update.message.reply_text("❌ Invalid link")
    else:
        await update.message.reply_text("Send file")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save))
app.add_handler(CommandHandler("start", start))

print("Bot running...")
app.run_polling()
