import os
import re
import logging
import asyncio
from functools import wraps

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream.others import AudioPiped
from shazamio import Shazam
import yt_dlp

# --- Config ---
BOT_TOKEN = "7438370540:AAHSz1YnnZDoS6tmdcw92CKU6L1vZoplFvQ"
API_ID = 25697537
API_HASH = "hash6c480f9f9b4759ed675181f80b114f45"
SESSION_NAME = "my_session"

ADMIN_IDS = [6565686047]  # Replace with your Telegram ID
USERS_FILE = "users.txt"

FORCED_CHANNELS = [
    {"chat_id": -1002277798669, "title": "Channel 1", "link": "https://t.me/+Tx0ogyhkN9NjZjc1"},
    {"chat_id": -100244338007243210, "title": "Channel 2", "link": "https://t.me/onling_earnig"},
    {"chat_id": -1002327629879, "title": "Channel 3", "link": "https://t.me/+BvaA4dMzwRtjOGM1"},
]

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Voice Clients ---
pyro_client = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)
pytgcalls_client = PyTgCalls(pyro_client)

# --- Utils ---
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE) as f:
        return {int(i.strip()) for i in f if i.strip().isdigit()}

def save_user(user_id: int):
    users = load_users()
    if user_id not in users:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")
        logger.info(f"New user: {user_id}")

async def force_join_prompt(update: Update):
    buttons = [
        [InlineKeyboardButton(text=ch["title"], url=ch["link"])]
        for ch in FORCED_CHANNELS
    ]
    await update.message.reply_text(
        "Please join all channels to use this bot:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def check_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for ch in FORCED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in ['left', 'kicked']:
                await force_join_prompt(update)
                return False
        except:
            await force_join_prompt(update)
            return False
    return True

# --- Decorators ---
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("Unauthorized")
            return
        return await func(update, context)
    return wrapper

# --- YouTube Downloader ---
def download_audio_from_youtube(url, filename="audio.mp3"):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': filename,
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_joined(update, context):
        return
    save_user(update.effective_user.id)
    await update.message.reply_text("Send an Instagram Reels link to get the music.")

async def handle_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_joined(update, context):
        return

    text = update.message.text
    match = re.search(r"https?://(?:www\.)?instagram\.com/reel/[^\s]+", text)
    if not match:
        await update.message.reply_text("Send a valid Instagram Reels link.")
        return

    reel_url = match.group(0)
    await update.message.reply_text("Downloading and analyzing the Reel...")

    video_path = "reel.mp4"
    os.system(f"yt-dlp -o {video_path} {reel_url}")

    if not os.path.exists(video_path):
        await update.message.reply_text("Failed to download Reel.")
        return

    # Identify music
    shazam = Shazam()
    out = await shazam.recognize_song(video_path)
    try:
        title = out['track']['title']
        subtitle = out['track']['subtitle']
        youtube_url = f"https://www.youtube.com/results?search_query={title}+{subtitle}"
        music_info = f"Title: {title}\nArtist: {subtitle}\nSearch: {youtube_url}"
    except:
        music_info = "Music not found."

    await context.bot.send_video(chat_id=update.effective_chat.id, video=open(video_path, 'rb'))
    await update.message.reply_text(music_info)

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    msg = " ".join(context.args)
    users = load_users()
    success = 0
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            success += 1
        except:
            continue

    await update.message.reply_text(f"Broadcast sent to {success} users.")

@admin_only
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = len(load_users())
    await update.message.reply_text(f"Total users: {count}")

@admin_only
async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /play <chat_id> <YouTube URL>")
        return

    chat_id = int(context.args[0])
    yt_url = context.args[1]

    audio_file = "stream.mp3"
    download_audio_from_youtube(yt_url, filename=audio_file)

    try:
        await pytgcalls_client.join_group_call(chat_id, AudioPiped(audio_file))
        await update.message.reply_text("Now streaming audio in voice chat!")
    except Exception as e:
        logger.error(f"Voice chat error: {e}")
        await update.message.reply_text("Streaming failed.")

# --- Voice Client ---
async def start_voice():
    await pyro_client.start()
    await pytgcalls_client.start()
    logger.info("Voice streaming client started")

# --- Main ---
async def main():
    await start_voice()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("usercount", user_count))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reel))

    logger.info("Bot is running")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())