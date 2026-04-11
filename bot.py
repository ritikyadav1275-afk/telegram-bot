import logging
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = "8776336091:AAGgrJn6bUaPJbo2QsPkM62irHFGfGpCFNk"
SHORTENER_API = "YOUR_API_KEY"

logging.basicConfig(level=logging.INFO)

user_files = {}

def shorten_url(url):
    try:
        api_url = f"https://shrinkme.io/api?api={SHORTENER_API}&url={url}"
        res = requests.get(api_url).json()
        if res.get("status") == "success":
            return res.get("shortenedUrl")
        else:
            return url
    except:
        return url

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args:
        file_id = args[0]
        if file_id in user_files:
            sent = await update.message.reply_document(user_files[file_id])
            await asyncio.sleep(300)
            await sent.delete()
            await update.message.reply_text("⏳ File deleted!")
        return

    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data="upload")],
        [InlineKeyboardButton("📦 Batch Mode", callback_data="batch")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]

    await update.message.reply_text(
        "👋 Welcome!\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document

    if not file:
        await update.message.reply_text("❌ Send a file")
        return

    file_id = file.file_id
    user_files[file_id] = file_id

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={file_id}"

    short = shorten_url(link)

    await update.message.reply_text(f"✅ Saved!\n💰 Link:\n{short}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "upload":
        await query.message.reply_text("📤 Send your file now")

    elif query.data == "batch":
        await query.message.reply_text("📦 Coming soon")

    elif query.data == "help":
        await query.message.reply_text("ℹ️ Just send file to get link")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
app.add_handler(CallbackQueryHandler(button_handler))

print("🚀 Running...")
app.run_polling()
