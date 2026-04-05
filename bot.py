 import os
import random
import string
import asyncio
from flask import Flask
from threading import Thread

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ✅ Get token from Render ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ✅ Flask server (to keep alive on Render)
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    app_web.run(host='0.0.0.0', port=10000)

Thread(target=run_web).start()

# ✅ Generate random code
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

# ✅ Save + return link
async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg:
        return

    file_id = None

    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.video:
        file_id = msg.video.file_id
    elif msg.document:
        file_id = msg.document.file_id

    if file_id:
        code = gen_code()
        context.bot_data[code] = file_id

        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"

        await msg.reply_text(f"🔗 Your link:\n{link}")

# ✅ Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        file_id = context.bot_data.get(code)

        if file_id:
            await update.message.reply_text("⚠️ This file will delete in 5 min")

            sent = await update.message.reply_document(file_id)

            async def delete_later():
                await asyncio.sleep(300)
                try:
                    await context.bot.delete_message(chat_id=sent.chat.id, message_id=sent.message_id)
                except:
                    pass

            asyncio.create_task(delete_later())
        else:
            await update.message.reply_text("❌ Invalid link")
    else:
        await update.message.reply_text("Send me a file")

# ✅ Main
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, save))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
