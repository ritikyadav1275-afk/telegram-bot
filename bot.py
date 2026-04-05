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
    ContextTypes,
    PicklePersistence
)
from telegram.error import BadRequest

# -------- CONFIG --------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

# -------- LOGGING --------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------- FLASK (KEEP ALIVE) --------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is running"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

# -------- UTIL --------
def gen_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

# -------- AUTO DELETE --------
async def delete_later(bot, chat_id, message_id):
    try:
        await asyncio.sleep(300)

        await asyncio.wait_for(
            bot.delete_message(chat_id=chat_id, message_id=message_id),
            timeout=10
        )

        logger.info(f"Deleted message {message_id}")

    except asyncio.CancelledError:
        return

    except asyncio.TimeoutError:
        logger.warning(f"Timeout deleting {message_id}")

    except BadRequest as e:
        error_text = str(e).lower()

        if "message to delete not found" in error_text:
            return
        if "message can't be deleted" in error_text:
            return

        logger.error(f"Telegram error: {e}")

    except Exception as e:
        logger.error(f"General error: {e}")

# -------- SAVE FILE --------
async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

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

    # Save in persistent storage
    context.bot_data[code] = {
        "file_id": file_id,
        "type": file_type
    }

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"

    await msg.reply_text(f"🔗 Your link:\n{link}")

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0]
        data = context.bot_data.get(code)

        if data:
            file_id = data["file_id"]
            file_type = data["type"]

            try:
                caption = "⚠️ This file will delete in 5 minutes"

                if file_type == "photo":
                    sent = await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=file_id,
                        caption=caption
                    )

                elif file_type == "video":
                    sent = await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=file_id,
                        caption=caption
                    )

                else:
                    sent = await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=file_id,
                        caption=caption
                    )

            except Exception as e:
                logger.error(f"Send failed: {e}")
                await update.message.reply_text("❌ Failed to send file")
                return

            asyncio.create_task(
                delete_later(context.bot, update.effective_chat.id, sent.message_id)
            )

        else:
            await update.message.reply_text("❌ Invalid or expired link")

    else:
        await update.message.reply_text("👋 Send me a file to get link")

# -------- MAIN --------
def main():
    persistence = PicklePersistence(filepath="my_bot_storage")

    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .persistence(persistence) \
        .build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
            save
        )
    )

    Thread(target=run_web, daemon=True).start()

    logger.info("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
