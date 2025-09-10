import os
import platform
import uuid
import html
import logging
import asyncio
import shutil
import random
import tempfile
import instaloader
import yt_dlp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Filter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.types import ReactionTypeEmoji
from aiogram.exceptions import TelegramBadRequest
import subprocess
from shazamio import Shazam
from pathlib import Path

# ========== Config ==========
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if platform.system() == "Windows":
    SESSION_FILES = [
        (os.path.expanduser(r"~/.config/instaloader/session-mirjalolinsta1"), "mirjalolinsta1"),
        (os.path.expanduser(r"~/.config/instaloader/session-mirjalolinsta"), "mirjalolinsta"),
        (os.path.expanduser(r"~/.config/instaloader/session-uztelecomtv072"), "uztelecomtv072"),
        (os.path.expanduser(r"~/.config/instaloader/session-mirjalolinsta2"), "mirjalolinsta2"),
        (os.path.expanduser(r"~/.config/instaloader/session-mirjalolinsta3"), "mirjalolinsta3"),
        (os.path.expanduser(r"~/.config/instaloader/session-notultrapubg.fan"), "notultrapubg.fan"),
    ]
else:
    SESSION_FILES = [
        ("/home/robber/.config/instaloader/session-mirjalolinsta1", "mirjalolinsta1"),
        ("/home/robber/.config/instaloader/session-mirjalolinsta", "mirjalolinsta"),
        ("/home/robber/.config/instaloader/session-uztelecomtv072", "uztelecomtv072"),
        ("/home/robber/.config/instaloader/session-mirjalolinsta2", "mirjalolinsta2"),
        ("/home/robber/.config/instaloader/session-mirjalolinsta3", "mirjalolinsta3"),
        ("/home/robber/.config/instaloader/session-notultrapubg.fan", "notultrapubg.fan"),
    ]

# FFmpeg va FFprobe yo'llari
FFMPEG_PATH = "/home/robber/tizim/ffmpeg"
FFPROBE_PATH = "/home/robber/tizim/ffprobe"

# Shazam konfiguratsiyasi
MAX_SECONDS = 30
SAMPLE_RATE = 44100
CHANNELS = 1

# FFprobe mavjudligini tekshirish
def check_ffmpeg_tools():
    """FFmpeg va FFprobe dasturlari mavjudligini tekshiradi."""
    try:
        subprocess.run([FFMPEG_PATH, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([FFPROBE_PATH, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("✅ FFmpeg va FFprobe topildi.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"❌ FFmpeg yoki FFprobe topilmadi yoki ishlamayapti: {e}")
        return False

# Boshlanishda tekshirish
if not check_ffmpeg_tools():
    raise SystemExit("❌ FFmpeg/FFprobe kerak. Iltimos, o'rnating va yo'llarni to'g'rilang.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
BASE_DOWNLOAD_FOLDER = "downloads"
os.makedirs(BASE_DOWNLOAD_FOLDER, exist_ok=True)
USER_AGENT = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'
loaded_sessions = []
for session_file_path, username in SESSION_FILES:
    if os.path.exists(session_file_path):
        try:
            temp_loader = instaloader.Instaloader(
                save_metadata=False,
                download_video_thumbnails=False
            )
            temp_loader.context._session.headers.update({'User-Agent': USER_AGENT})
            temp_loader.load_session_from_file(username, session_file_path)
            loaded_sessions.append((temp_loader, username, session_file_path))
            logging.info(f"Instagram sessiyasi yuklandi: {username} ({session_file_path})")
        except Exception as e:
            logging.warning(f"Instagram sessiya faylini yuklashda xatolik {session_file_path}: {e}")
            continue
if not loaded_sessions:
    raise Exception("❌ Hech qanday Instagram session fayli ishlamadi.")
logging.basicConfig(level=logging.INFO)

# ========== Foydalanuvchi uchun papka va loader yaratish ==========
def get_user_folder(chat_id: int) -> str:
    """Foydalanuvchi uchun maxsus papka yaratadi va yo'lini qaytaradi."""
    user_folder = os.path.join(BASE_DOWNLOAD_FOLDER, str(chat_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_insta_loader(chat_id: int):
    """Foydalanuvchi uchun maxsus Instaloader nusxasini yaratadi (tasodifiy sessiya bilan)."""
    user_folder = get_user_folder(chat_id)
    random_loader, random_username, random_path = random.choice(loaded_sessions)
    logging.info(f"Foydalanuvchi {chat_id} uchun tasodifiy sessiya tanlandi: {random_username}")
    loader = instaloader.Instaloader(
        dirname_pattern=user_folder,
        save_metadata=False,
        download_video_thumbnails=False
    )
    loader.context._session.headers.update({'User-Agent': USER_AGENT})
    if random_loader.context.is_logged_in:
        loader.context._session.cookies.update(random_loader.context._session.cookies)
        base_headers = random_loader.context._session.headers.copy()
        if 'User-Agent' in base_headers:
            del base_headers['User-Agent']
        loader.context._session.headers.update(base_headers)
        loader.context._session.headers.update({'User-Agent': USER_AGENT})
    else:
        loader.context._session.headers.update({'User-Agent': USER_AGENT})
    return loader

# ========== YouTube formatlari ==========
user_cache = {}

def get_user_cache(chat_id: int):
    """Foydalanuvchi keshini olish yoki yaratish."""
    if chat_id not in user_cache:
        user_cache[chat_id] = {}
    return user_cache

def get_formats(url: str):
    current_user_agent = USER_AGENT
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'user_agent': current_user_agent
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        for f in info['formats']:
            if f.get('format_id') and f.get('vcodec') != 'none':
                fmt_id = f['format_id']
                ext = f.get('ext')
                height = f.get('height')
                fps = f.get('fps')
                filesize = f.get('filesize')
                note = f.get('format_note') or ''
                resolution = f"{height}p" if height else 'unknown'
                fps_info = f"{fps}fps" if fps else ''
                size = f"{round(filesize / 1024 / 1024, 2)}MB" if filesize else 'Unknown size'
                desc = f"{ext} | {resolution} {fps_info} | {size} {note}"
                formats.append((fmt_id, desc))
        formats.append(("bestaudio", "🎵 MP3 format (audio only)"))
        title = info.get('title', 'Nomaʼlum')
        thumbnail_url = None
        thumbnails = info.get('thumbnails')
        if thumbnails:
            thumbnail_url = thumbnails[-1].get('url')
        if not thumbnail_url:
            thumbnail_url = info.get('thumbnail')
        return title, formats, thumbnail_url

# ========== Xabar matnini yangilash (xatolarga chidamli) ==========
async def safe_edit_message_text(message: types.Message, text: str, **kwargs):
    """Xabarni yangilashda 'message is not modified' xatosini oldini oladi."""
    try:
        current_text = getattr(message, 'text', None)
        current_caption = getattr(message, 'caption', None)
        if text == current_text or text == current_caption:
            logging.debug("Xabar matni o'zgarmagan, yangilash kerak emas.")
            return message
        return await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            logging.debug("Xabar allaqachon shu matnga ega. Yangilash kerak emas.")
            return message
        else:
            logging.warning(f"Xabarni yangilashda kutilmagan xatolik: {e}")
            raise
    except Exception as e:
        logging.error(f"Xabarni yangilashda umumiy xatolik: {e}")
        raise

# ========== YouTube yuklab olish va yuborish (progress bar YO'Q, tezroq) ==========
async def download_and_send(chat_id: int, url: str, format_id: str, bot_message: types.Message):
    loop = asyncio.get_running_loop()
    user_folder = get_user_folder(chat_id)
    current_user_agent = USER_AGENT

    def download():
        ydl_opts = {
            'format': format_id + "+bestaudio/best" if format_id != "bestaudio" else 'bestaudio',
            'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4' if format_id != "bestaudio" else 'mp3',
            'ffmpeg_location': FFMPEG_PATH,
            'socket_timeout': 60,
            'retries': 10,
            'http_chunk_size': 10485760,
            'user_agent': current_user_agent,
            'concurrent_fragment_downloads': 10,
            'buffersize': 1024 * 1024,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info, ydl.prepare_filename(info)

    try:
        await safe_edit_message_text(bot_message, "📥 Yuklanmoqda...")
        info, file_path = await loop.run_in_executor(None, download)
    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ YouTube yuklab olishda xatolik: {e}")
        return

    try:
        await safe_edit_message_text(bot_message, "📤 Yuborilmoqda...")
        file_size = os.path.getsize(file_path)
        input_file = FSInputFile(file_path)
        if file_size > 2048 * 1024 * 1024:
            await bot.send_message(chat_id, "❌ Fayl juda katta (2048MB dan katta).")
            os.remove(file_path)
            try:
                os.rmdir(user_folder)
            except OSError:
                pass
            return
        title = info.get('title', 'Nomaʼlum')
        uploader = info.get('uploader', 'Nomaʼlum')
        view_count = info.get('view_count') or 0
        like_count = info.get('like_count') or 0
        resolution = info.get('height') or '???'
        ext = info.get('ext') or '???'
        size_mb = round(file_size / 1024 / 1024, 2)
        duration = info.get('duration')
        if isinstance(duration, (int, float)):
            minutes = int(duration) // 60
            seconds = int(duration) % 60
            duration_text = f"{minutes} daq {seconds} soniya"
        else:
            duration_text = "???"
        caption = (
            f"🎬 <b>{html.escape(title)}</b>\n"
            f"📺 Kanal: <b>{html.escape(uploader)}</b>\n"
            f"👁 Ko‘rishlar: <b>{view_count:,}</b>\n"
            f"👍 Layklar: <b>{like_count:,}</b>\n"
            f"⏱ Davomiyligi: {duration_text}\n"
            f"📁 Format: <code>{ext}</code>\n"
            f"📏 Sifat: <b>{resolution}p</b>\n"
            f"💾 Hajmi: {size_mb} MB"
        )
        if format_id == "bestaudio":
            sent_message = await bot.send_audio(chat_id, input_file, caption=caption, parse_mode="HTML")
        else:
            sent_message = await bot.send_video(chat_id, input_file, caption=caption, parse_mode="HTML")
        await safe_add_reaction(bot, sent_message.chat.id, sent_message.message_id, emoji="❤️", is_big=True)

        # Shazam tugmachasini yaratish (faqat video fayllar uchun)
        if format_id != "bestaudio":
            shazam_button = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Musiqani aniqlash", callback_data=f"shazam:{sent_message.message_id}")]
                ]
            )
            await bot.send_message(chat_id, "🎵 Videodagi musiqani aniqlashni xohlaysizmi?", reply_markup=shazam_button, reply_to_message_id=sent_message.message_id)

        os.remove(file_path)
        try:
            os.rmdir(user_folder)
        except OSError:
            pass
    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ YouTube fayl yuborishda xatolik: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        try:
            os.rmdir(user_folder)
        except OSError:
            pass

# ========== Instagram yuklash ==========
async def download_instagram_for_user(chat_id: int, url: str, loading_msg: types.Message):
    """Foydalanuvchi uchun Instagram kontentini yuklaydi (tasodifiy sessiya bilan)."""
    user_loader = get_user_insta_loader(chat_id)
    user_folder = get_user_folder(chat_id)
    shortcode = None
    if "/p/" in url:
        shortcode = url.split("/p/")[1].split("/")[0]
    elif "/reel/" in url:
        shortcode = url.split("/reel/")[1].split("/")[0]
    elif "/tv/" in url:
        shortcode = url.split("/tv/")[1].split("/")[0]
    else:
        return None, "❌ Instagram link noto'g'ri yoki qo'llab-quvvatlanmaydi."

    try:
        await safe_edit_message_text(loading_msg, "📥 Instagram media yuklanmoqda...")
        post = instaloader.Post.from_shortcode(user_loader.context, shortcode)
        user_loader.download_post(post, target=user_folder)
        await safe_edit_message_text(loading_msg, "📤 Instagram media yuborilmoqda...")
        files = os.listdir(user_folder)
        media_files = [os.path.join(user_folder, f) for f in files if f.endswith(('.jpg', '.mp4'))]
        return media_files, None
    except Exception as e:
        try:
            await safe_edit_message_text(loading_msg, f"❌ Instagram yuklashda xatolik: {e}")
        except:
            pass
        return None, f"❌ Instagram yuklashda xatolik: {e}"

# ========== Media fayllarni guruhlab yuborish ==========
async def send_media_group(chat_id: int, media_files: list, loading_msg: types.Message):
    """Media fayllarni 10 tadan guruhlab yuboradi."""
    try:
        sent_messages = []
        for i in range(0, len(media_files), 10):
            batch = media_files[i:i+10]
            media_group = []
            for file_path in batch:
                input_file = FSInputFile(file_path)
                if file_path.endswith('.mp4'):
                    media_group.append(InputMediaVideo(media=input_file))
                else:
                    media_group.append(InputMediaPhoto(media=input_file))
            if media_group:
                sent_group = await bot.send_media_group(chat_id, media_group)
                sent_messages.extend(sent_group)
        await loading_msg.delete()
        if sent_messages:
            first_message = sent_messages[0]
            await safe_add_reaction(bot, first_message.chat.id, first_message.message_id, emoji="❤️", is_big=True)
            # Shazam tugmachasini yaratish (faqat video fayllar uchun)
            if any(f.endswith('.mp4') for f in media_files):
                shazam_button = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔍 Musiqani aniqlash", callback_data=f"shazam:{first_message.message_id}")]
                    ]
                )
                await bot.send_message(chat_id, "🎵 Videodagi musiqani aniqlashni xohlaysizmi?", reply_markup=shazam_button, reply_to_message_id=first_message.message_id)
    except Exception as e:
        try:
           await safe_edit_message_text(loading_msg, f"⚠️ Media guruhini yuborishda xatolik: {e}")
        except:
            pass
        logging.error(f"Media guruhini yuborishda xatolik: {e}")
    finally:
        user_folder = os.path.dirname(media_files[0]) if media_files else None
        if user_folder:
            try:
                shutil.rmtree(user_folder)
            except Exception as e:
                logging.error(f"❌ Foydalanuvchi papkasini tozalashda xatolik ({user_folder}): {e}")

# ========== Shazam funksiyasi (ffmpeg bilan audio ajratish va aniqlash) ==========
async def extract_audio_ffmpeg(input_path: str, output_path: str, max_seconds: int = MAX_SECONDS):
    """FFmpeg bilan audio ni WAV (mono, 44.1kHz) formatiga o‘tkazadi."""
    cmd = [
        FFMPEG_PATH, "-y",
        "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-t", str(max_seconds),
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-sample_fmt", "s16",
        str(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        logging.error("ffmpeg failed: %s", res.stderr.decode(errors='ignore'))
        raise RuntimeError("ffmpeg bilan audio konvertatsiya bo‘lmadi")

async def recognize_audio_bytes(audio_bytes: bytes):
    """Shazam orqali audio ni aniqlaydi (recognize metodidan foydalaniladi)."""
    shazam_client = Shazam()
    try:
        return await shazam_client.recognize(audio_bytes)
    except Exception as e:
        logging.exception("Shazam recognition failed: %s", e)
        raise

async def recognize_music_from_file(file_path: str, chat_id: int, original_message_id: int):
    """Fayl ichidan musiqani aniqlab, YouTube'da qidiruv natijalarini yuboradi."""
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="shazam_bot_"))
        input_file_path = tmp_dir / "input"
        shutil.copy(file_path, input_file_path)

        wav_path = tmp_dir / "out.wav"
        try:
            await extract_audio_ffmpeg(str(input_file_path), str(wav_path), MAX_SECONDS)
        except Exception as e:
            await bot.send_message(chat_id, "❌ Audio konvertatsiya qilinmadi. ffmpeg o‘rnatilganini tekshiring.", reply_to_message_id=original_message_id)
            return

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        try:
            result = await recognize_audio_bytes(audio_bytes)
        except Exception as e:
            await bot.send_message(chat_id, "❌ Musiqa aniqlashda xatolik yuz berdi.", reply_to_message_id=original_message_id)
            return

        track = result.get("track") if isinstance(result, dict) else None
        if not track:
            await bot.send_message(chat_id, "❌ Musiqa topilmadi — boshqa qismini yuboring.", reply_to_message_id=original_message_id)
            return

        title = track.get("title", "Noma'lum")
        subtitle = track.get("subtitle", "Noma'lum ijrochi")
        search_query = f"{title} {subtitle}"

        # YouTube'da qidiruv
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'default_search': 'ytsearch10',
            'user_agent': USER_AGENT,
            'extract_flat': 'in_playlist',
        }
        search_query_yt = f"ytsearch10:{search_query} music"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(search_query_yt, download=False)

        if not search_result or 'entries' not in search_result:
            await bot.send_message(chat_id, "❌ Hech narsa topilmadi.", reply_to_message_id=original_message_id)
            return

        entries = search_result['entries']
        if not entries:
            await bot.send_message(chat_id, "❌ Hech narsa topilmadi.", reply_to_message_id=original_message_id)
            return

        # Qidiruv natijalarini sahifalab ko'rsatish
        user_specific_cache = get_user_cache(chat_id)
        user_specific_cache['music_search'] = {
            'entries': entries,
            'reply_to_message_id': original_message_id
        }
        
        page_size = 10
        current_page = 0
        total_pages = (len(entries) + page_size - 1) // page_size
        
        if total_pages == 0:
             await bot.send_message(chat_id, "❌ Hech narsa topilmadi.", reply_to_message_id=original_message_id)
             return
             
        processing_msg = await bot.send_message(chat_id, "🔍 Qidiruv natijalari tayyorlanmoqda...")
        await send_music_page(chat_id, entries, current_page, total_pages, processing_msg, original_message_id)

    except Exception as e:
        logging.exception("Shazamda xatolik:")
        await bot.send_message(chat_id, f"⚠️ Xatolik: {e}", reply_to_message_id=original_message_id)
    finally:
        if tmp_dir and tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except Exception as e:
                logging.warning(f"Vaqtincha katalogni o'chirishda xatolik: {e}")

# ========== Shazam filter ==========
class ShazamFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text:
            return False
        if len(message.text.strip()) < 3:
            return False
        if message.text.startswith('/'):
            return False
        if "youtube.com" in message.text or "youtu.be" in message.text or "instagram.com" in message.text:
            return False
        return True

# ========== Bot komandalar ==========
async def safe_add_reaction(bot, chat_id: int, message_id: int, emoji: str = "❤️", is_big: bool = False):
    """
    Xavfsiz tarzda xabarga reaksiya qo'shadi, xatoliklarga chidamli.
    """
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
            is_big=is_big
        )
        logging.info(f"Reaksiya '{emoji}' (is_big={is_big}) xabarga qo'shildi: chat_id={chat_id}, message_id={message_id}")
    except TelegramBadRequest as e:
        error_message = str(e).lower()
        logging.warning(f"Reaksiya qo'shishda xatolik (chat_id={chat_id}, message_id={message_id}): {e}")
        if "reaction_invalid" in error_message and is_big:
            try:
                await bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=message_id,
                    reaction=[ReactionTypeEmoji(emoji=emoji)],
                    is_big=False
                )
                logging.info(f"Reaksiya '{emoji}' (is_big=False) alternativ ravishda qo'shildi: chat_id={chat_id}, message_id={message_id}")
            except TelegramBadRequest as e2:
                 logging.warning(f"is_big=False bilan ham reaksiya qo'shish muvaffaqiyatsiz: {e2}")
                 try:
                     fallback_emoji = "👍"
                     await bot.set_message_reaction(
                         chat_id=chat_id,
                         message_id=message_id,
                         reaction=[ReactionTypeEmoji(emoji=fallback_emoji)],
                         is_big=False
                     )
                     logging.info(f"Fallback reaksiya '{fallback_emoji}' xabarga qo'shildi: chat_id={chat_id}, message_id={message_id}")
                 except Exception as e3:
                     logging.error(f"Fallback reaksiya ham muvaffaqiyatsiz: {e3}. Reaksiya qo'shish to'liq bekor qilindi.")
        else:
            logging.error(f"Boshqa TelegramBadRequest xatoligi: {e}")
    except Exception as e:
        logging.error(f"Reaksiya qo'shishda kutilmagan xatolik (chat_id={chat_id}, message_id={message_id}): {e}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await safe_add_reaction(bot, message.chat.id, message.message_id, emoji="❤️", is_big=True)
    try:
        sent_message = await message.answer(
            "👋 Salom!\n"
            "Men YouTube va Instagram videolarini yuklab bera olaman.\n"
            "YouTube uchun link yuboring, keyin formatni tanlang (video yoki audio).\n"
            "Instagram uchun post/reel/tv link yuboring.\n"
            "Oddiy matnli xabar yuborsangiz, uni Shazam orqali YouTube'da qidiraman.\n"
            "Masalan:\n"
            "YouTube: https://youtu.be/XXXXXX\n"
            "Instagram: https://www.instagram.com/p/XXXXXX/\n"
            "Oddiy habar: Balti - Ya Lili"
        )
        await safe_add_reaction(bot, sent_message.chat.id, sent_message.message_id, emoji="❤️", is_big=True)
    except Exception as e:
        logging.warning(f"Bot xabariga effekt qo'shishda xatolik: {e}")

@dp.message(ShazamFilter())
async def shazam_text_handler(message: types.Message):
    """Oddiy matnli xabarlarni Shazam qidiruvi sifatida qayta ishlash."""
    query = message.text.strip()
    chat_id = message.chat.id
    await safe_add_reaction(bot, message.chat.id, message.message_id, emoji="❤️", is_big=False)
    processing_msg = await message.answer("🔍 Musiqa qidirilmoqda...")
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'default_search': 'ytsearch10',
            'user_agent': USER_AGENT,
            'extract_flat': 'in_playlist',
        }
        search_query = f"ytsearch10:{query} music"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(search_query, download=False)
        if not search_result or 'entries' not in search_result:
            await safe_edit_message_text(processing_msg, "❌ Hech narsa topilmadi.")
            return
        entries = search_result['entries']
        if not entries:
            await safe_edit_message_text(processing_msg, "❌ Hech narsa topilmadi.")
            return
        user_specific_cache = get_user_cache(chat_id)
        music_search_id = str(uuid.uuid4())
        user_specific_cache['music_search'] = {
            'entries': entries,
            'page_size': 5,
            'reply_to_message_id': message.message_id
        }
        page_size = 5
        current_page = 0
        total_pages = (len(entries) + page_size - 1) // page_size
        if total_pages == 0:
            await safe_edit_message_text(processing_msg, "❌ Hech narsa topilmadi.")
            return
        await send_music_page(chat_id, entries, current_page, total_pages, processing_msg, message.message_id)
    except Exception as e:
        logging.exception("YouTube qidiruvida xatolik:")
        await safe_edit_message_text(processing_msg, f"⚠️ Qidiruvda xatolik: {e}")

async def send_music_page(chat_id: int, entries: list, page: int, total_pages: int, processing_msg: types.Message, reply_to_message_id: int):
    page_size = 10
    start_index = page * page_size
    end_index = min(start_index + page_size, len(entries))
    page_entries = entries[start_index:end_index]
    if not page_entries:
        await safe_edit_message_text(processing_msg, "❌ Ushbu sahifada hech narsa yo'q.")
        return
    text_lines = [f"🎵 <b>Qidiruv natijalari:</b> <i>{len(entries)} topildi</i>\n"]
    buttons = []
    for i, entry in enumerate(page_entries):
        index = start_index + i + 1
        title = entry.get('title', 'Noma\'lum')
        duration = entry.get('duration')
        if isinstance(duration, (int, float)):
            minutes = int(duration) // 60
            seconds = int(duration) % 60
            duration_text = f"{minutes}:{seconds:02d}"
        else:
            duration_text = "???"
        text_lines.append(f"{index}. <b>{html.escape(title)}</b> ({duration_text})")
        callback_data = f"music:{entry.get('id', 'unknown')}:{page}"
        buttons.append([InlineKeyboardButton(text=str(index), callback_data=callback_data)])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"music_prev:{page}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"music_next:{page}:{total_pages}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    text = "\n".join(text_lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await safe_edit_message_text(processing_msg, text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            raise e

@dp.message(F.voice | F.audio | F.video | F.video_note | F.document)
async def handle_media(message: types.Message):
    """Shazam orqali media fayllarni qayta ishlash."""
    await message.chat.do("typing")
    tmp_dir = Path(tempfile.mkdtemp(prefix="shazam_bot_"))
    try:
        input_file_path = tmp_dir / "input"
        # Media obyektini aniqlash
        media = message.voice or message.audio or message.video or message.video_note or message.document
        if not media:
            await message.reply("❌ Media topilmadi.")
            return
        # ✅ Bot bilan faylni yuklash
        await bot.download(file=media, destination=input_file_path)
        wav_path = tmp_dir / "out.wav"
        try:
            await extract_audio_ffmpeg(input_file_path, wav_path, MAX_SECONDS)
        except Exception:
            await message.reply("❌ Audio konvertatsiya qilinmadi. ffmpeg o‘rnatilganini tekshiring.")
            return
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
        await message.chat.do("typing")
        try:
            result = await recognize_audio_bytes(audio_bytes)
        except Exception:
            await message.reply("❌ Musiqa aniqlashda xatolik yuz berdi.")
            return
        track = result.get("track") if isinstance(result, dict) else None
        if not track:
            await message.reply("❌ Musiqa topilmadi — boshqa qismini yuboring.")
            return
        title = track.get("title", "Noma'lum")
        subtitle = track.get("subtitle", "Noma'lum ijrochi")
        search_query = f"{title} {subtitle}"

        # YouTube'da qidiruv
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'default_search': 'ytsearch10',
            'user_agent': USER_AGENT,
            'extract_flat': 'in_playlist',
        }
        search_query_yt = f"ytsearch10:{search_query} music"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(search_query_yt, download=False)

        if not search_result or 'entries' not in search_result:
            await message.reply("❌ Hech narsa topilmadi.")
            return

        entries = search_result['entries']
        if not entries:
            await message.reply("❌ Hech narsa topilmadi.")
            return

        # Qidiruv natijalarini sahifalab ko'rsatish
        user_specific_cache = get_user_cache(message.chat.id)
        user_specific_cache['music_search'] = {
            'entries': entries,
            'reply_to_message_id': message.message_id
        }
        
        page_size = 10
        current_page = 0
        total_pages = (len(entries) + page_size - 1) // page_size
        
        if total_pages == 0:
             await message.reply("❌ Hech narsa topilmadi.")
             return
             
        processing_msg = await message.reply("🔍 Qidiruv natijalari tayyorlanmoqda...")
        await send_music_page(message.chat.id, entries, current_page, total_pages, processing_msg, message.message_id)

    finally:
        for p in tmp_dir.iterdir():
            p.unlink(missing_ok=True)
        tmp_dir.rmdir()

@dp.message()
async def message_handler(message: types.Message):
    url = message.text.strip()
    chat_id = message.chat.id
    await safe_add_reaction(bot, message.chat.id, message.message_id, emoji="❤️", is_big=False)
    if "youtube.com" in url or "youtu.be" in url:
        loading_msg = await message.answer("🎬 YouTube video formatlari olinmoqda...")
        try:
            title, formats, thumbnail_url = await asyncio.to_thread(get_formats, url)
            logging.info(f"DEBUG: Olingan formatlar soni: {len(formats)}")
            if not formats:
                await safe_edit_message_text(loading_msg, "❌ Formatlar topilmadi.")
                logging.warning("DEBUG: Formatlar ro'yxati bo'sh")
                return
            unique_id = str(uuid.uuid4())
            user_specific_cache = get_user_cache(chat_id)
            user_specific_cache[unique_id] = {'url': url}
            buttons = []
            row = []
            for i, (fmt_id, desc) in enumerate(formats, start=1):
                callback = f"yt:{chat_id}:{unique_id}:{fmt_id}"
                row.append(InlineKeyboardButton(text=desc[:64], callback_data=callback))
                if i % 2 == 0:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            escaped_title = html.escape(title)
            logging.info(f"DEBUG: loading_msg ID: {loading_msg.message_id}")
            if thumbnail_url:
                caption_text = (
                    f"🎥 <b>{escaped_title}</b>\n"
                    f"👇 Quyidagi sifatlardan birini tanlang:"
                )
                try:
                    sent_msg = await message.answer_photo(
                        photo=thumbnail_url,
                        caption=caption_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logging.info(f"DEBUG: Thumbnail yuborildi, sent_msg ID: {sent_msg.message_id}")
                    await loading_msg.delete()
                    logging.info("DEBUG: loading_msg (formatlar olinmoqda) o'chirildi")
                except Exception as e:
                    logging.error(f"DEBUG: Thumbnail yuborishda xatolik: {e}")
                    await safe_edit_message_text(loading_msg,
                        f"🎥 <b>{escaped_title}</b> uchun format tanlang:",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logging.info("DEBUG: loading_msg tahrirlandi, o'chirilmadi")
            else:
                await safe_edit_message_text(loading_msg,
                    f"🎥 <b>{escaped_title}</b> uchun format tanlang:",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                logging.info("DEBUG: loading_msg tahrirlandi (thumbnail yo'q), o'chirilmadi")
        except Exception as e:
            logging.exception(f"DEBUG: YouTube formatlarini olishda kutilmagan xatolik: {e}")
            await safe_edit_message_text(loading_msg, f"⚠️ YouTube formatlarini olishda kutilmagan xatolik.")
            return
        return
    if "instagram.com" in url:
        loading_msg = await message.answer("🔄 Instagram media topilmoqda...")
        media_files, error = await download_instagram_for_user(chat_id, url, loading_msg)
        if error:
            return
        if not media_files:
            try:
                os.rmdir(get_user_folder(chat_id))
            except OSError:
                pass
            return
        await send_media_group(chat_id, media_files, loading_msg)
        return

@dp.callback_query(lambda c: c.data and c.data.startswith("yt:"))
async def yt_download_callback(callback_query: CallbackQuery):
    try:
        parts = callback_query.data.split(":", 3)
        if len(parts) != 4:
             raise ValueError("Invalid callback data format")
        _, chat_id_str, unique_id, format_id = parts
        chat_id = int(chat_id_str)
    except (ValueError, IndexError):
        await callback_query.answer("❌ Noto‘g‘ri formatda ma'lumot.", show_alert=True)
        return
    user_specific_cache = get_user_cache(chat_id)
    if unique_id not in user_specific_cache:
        await callback_query.answer("❌ Sessiya muddati o'tgan. Qaytadan yuboring.", show_alert=True)
        return
    url = user_specific_cache[unique_id]['url']
    if callback_query.message.chat.id != chat_id:
         await callback_query.answer("❌ Bu so'rov boshqa foydalanuvchiga tegishli.", show_alert=True)
         return
    await callback_query.answer("⏳ Yuklab olish boshlandi...")
    bot_message = await bot.send_message(chat_id, "📥 Yuklanmoqda...")
    asyncio.create_task(download_and_send(chat_id, url, format_id, bot_message))
    try:
        await callback_query.message.delete()
        logging.info("DEBUG: Sifat tanlash xabari (tugmachalar bilan) o'chirildi")
    except Exception as e:
        logging.warning(f"Sifat tanlash xabarini o'chirishda xatolik: {e}")
        try:
             try:
                 await safe_edit_message_text(callback_query.message, "📥 YouTube yuklab olish boshlandi...")
             except TelegramBadRequest as e:
                 if "message is not modified" not in str(e).lower():
                     raise
             logging.info("DEBUG: Sifat tanlash xabari tahrirlandi")
        except Exception as e2:
             logging.warning(f"Sifat tanlash xabarini tahrirlashda xatolik: {e2}")

@dp.callback_query(lambda c: c.data and c.data.startswith("shazam:"))
async def shazam_callback_handler(callback_query: CallbackQuery):
    await callback_query.answer()
    try:
        _, message_id_str = callback_query.data.split(":", 1)
        message_id = int(message_id_str)
    except (ValueError, IndexError):
        await callback_query.message.answer("❌ Noto'g'ri ma'lumot.")
        return
    chat_id = callback_query.message.chat.id
    try:
        target_message = callback_query.message
        if not (target_message.video or target_message.audio or target_message.voice or target_message.document):
            if target_message.reply_to_message:
                target_message = target_message.reply_to_message
            else:
                try:
                    target_message = await bot.get_message(chat_id, message_id)
                    if not target_message:
                        raise ValueError("Xabar topilmadi")
                except:
                    await callback_query.message.answer("❌ Asl media xabarini topib bo'lmadi. Iltimos, videoni qaytadan yuklab, shazam tugmasini bosing.")
                    return
    except Exception as e:
        await callback_query.message.answer(f"❌ Xabarni topishda xatolik: {e}")
        return
    file_path = None
    try:
        if target_message.video:
            file_id = target_message.video.file_id
        elif target_message.audio:
            file_id = target_message.audio.file_id
        elif target_message.voice:
            file_id = target_message.voice.file_id
        elif target_message.document:
            file_id = target_message.document.file_id
        else:
            await callback_query.message.answer("❌ Xabardagi media fayl topilmadi.")
            return
        file = await bot.get_file(file_id)
        file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.tmp")
        await bot.download_file(file.file_path, file_path)
        await recognize_music_from_file(file_path, chat_id, callback_query.message.message_id)
    except Exception as e:
        logging.exception("Shazam callbackda xatolik:")
        await callback_query.message.answer(f"⚠️ Xatolik: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

@dp.callback_query(lambda c: c.data and c.data.startswith("music:"))
async def music_download_callback(callback_query: CallbackQuery):
    await callback_query.answer()
    try:
        parts = callback_query.data.split(":", 2)
        if len(parts) < 2:
            raise ValueError("Invalid callback data format")
        _, video_id = parts[0], parts[1]
        url = f"https://www.youtube.com/watch?v={video_id}"
        chat_id = callback_query.message.chat.id
        bot_message = await bot.send_message(chat_id, "📥 Yuklanmoqda...")
        def download():
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(get_user_folder(chat_id), '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_PATH,
                'socket_timeout': 60,
                'retries': 10,
                'http_chunk_size': 10485760,
                'user_agent': USER_AGENT,
                'concurrent_fragment_downloads': 10,
                'buffersize': 1024 * 1024,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl.prepare_filename(info)
        try:
            info, file_path = await asyncio.to_thread(download)
        except Exception as e:
            await safe_edit_message_text(bot_message, f"⚠️ Musiqa yuklab olishda xatolik: {e}")
            return
        try:
            await safe_edit_message_text(bot_message, "📤 Yuborilmoqda...")
            file_size = os.path.getsize(file_path)
            input_file = FSInputFile(file_path)
            if file_size > 2048 * 1024 * 1024:
                await bot.send_message(chat_id, "❌ Fayl juda katta (2048MB dan katta).")
                os.remove(file_path)
                try:
                    os.rmdir(get_user_folder(chat_id))
                except OSError:
                    pass
                return
            title = info.get('title', 'Nomaʼlum')
            uploader = info.get('uploader', 'Nomaʼlum')
            duration = info.get('duration')
            if isinstance(duration, (int, float)):
                minutes = int(duration) // 60
                seconds = int(duration) % 60
                duration_text = f"{minutes} daq {seconds} soniya"
            else:
                duration_text = "???"
            ext = info.get('ext') or '???'
            size_mb = round(file_size / 1024 / 1024, 2)
            caption = (
                f"🎵 <b>{html.escape(title)}</b>\n"
                f"🎤 Ijrochi: <b>{html.escape(uploader)}</b>\n"
                f"⏱ Davomiyligi: {duration_text}\n"
                f"📁 Format: <code>{ext}</code>\n"
                f"💾 Hajmi: {size_mb} MB"
            )
            sent_message = await bot.send_audio(chat_id, input_file, caption=caption, parse_mode="HTML")
            await safe_add_reaction(bot, sent_message.chat.id, sent_message.message_id, emoji="❤️", is_big=True)
            os.remove(file_path)
            try:
                os.rmdir(get_user_folder(chat_id))
            except OSError:
                pass
        except Exception as e:
            await bot.send_message(chat_id, f"⚠️ Musiqa fayl yuborishda xatolik: {e}")
            if os.path.exists(file_path):
                os.remove(file_path)
            try:
                os.rmdir(get_user_folder(chat_id))
            except OSError:
                pass
    except Exception as e:
        logging.exception("Musiqa yuklab olish callbackda xatolik:")
        await callback_query.message.answer(f"⚠️ Xatolik: {e}")

@dp.callback_query(lambda c: c.data and (c.data.startswith("music_prev:") or c.data.startswith("music_next:")))
async def music_pagination_callback(callback_query: CallbackQuery):
    await callback_query.answer()
    try:
        chat_id = callback_query.message.chat.id
        user_specific_cache = get_user_cache(chat_id)
        if 'music_search' not in user_specific_cache:
            await callback_query.message.answer("❌ Qidiruv natijalari topilmadi. Qaytadan qidiring.")
            return
        search_data = user_specific_cache['music_search']
        entries = search_data['entries']
        page_size = 10
        total_pages = (len(entries) + page_size - 1) // page_size
        current_page = 0
        reply_to_message_id = search_data.get('reply_to_message_id', callback_query.message.message_id)
        if callback_query.data.startswith("music_prev:"):
            try:
                _, page_str = callback_query.data.split(":", 1)
                current_page = int(page_str) - 1
                if current_page < 0:
                    current_page = 0
            except (ValueError, IndexError):
                current_page = 0
        elif callback_query.data.startswith("music_next:"):
            try:
                _, page_str, total_pages_str = callback_query.data.split(":", 2)
                current_page = int(page_str) + 1
                if current_page >= total_pages:
                    current_page = total_pages - 1
            except (ValueError, IndexError):
                current_page = 0
        await send_music_page(chat_id, entries, current_page, total_pages, callback_query.message, reply_to_message_id)
    except Exception as e:
        logging.exception("Sahifalash callbackda xatolik:")
        await callback_query.message.answer(f"⚠️ Xatolik: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())