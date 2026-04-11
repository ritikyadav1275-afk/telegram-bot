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

TOKEN = "YOUR_BOT_TOKEN"
SHORTENER_API = "YOUR_API_KEY"

logging.basicConfig(level=logging.INFO)

user_files = {}

# 🔗 Safe Shortener
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

# 🚀 Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    # If link opened
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

# 📤 Handle file
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document

    if not file:
        await update.message.reply_text("❌ Send a valid file")
        return

    file_id = file.file_id
    user_files[file_id] = file_id

    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start={file_id}"

    short_link = shorten_url(deep_link)

    await update.message.reply_text(
        f"✅ Saved!\n💰 Download Link:\n{short_link}"
    )

# 🔘 Buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "upload":
        await query.message.reply_text("📤 Send your file now")

    elif query.data == "batch":
        await query.message.reply_text("📦 Batch mode coming soon")

    elif query.data == "help":
        await query.message.reply_text("ℹ️ Send any file to get link")

# ▶️ Run
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
app.add_handler(CallbackQueryHandler(button_handler))

print("🚀 Bot running...")
app.run_polling()
