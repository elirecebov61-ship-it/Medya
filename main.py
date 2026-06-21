import logging
import os
import time
from contextlib import contextmanager

from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import Message
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Ayarlar ─────────────────────────────────────────────────────────────────
TOKEN          = os.environ["BOT_TOKEN"]
API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
DATABASE_URL   = os.environ["DATABASE_URL"]
FOUNDER_ID     = 8391851739

# Botun çalışacağı grup ID'leri
GROUP_IDS = {
    -1003980408859,
}

# ── Veritabanı ────────────────────────────────────────────────────────────
db_pool = None


def get_pool():
    global db_pool
    if db_pool is None:
        for attempt in range(10):
            try:
                db_pool = pool.ThreadedConnectionPool(2, 10, DATABASE_URL)
                return db_pool
            except Exception as e:
                logger.warning(f"Pool hatası ({attempt+1}/10): {e}")
                time.sleep(3)
        raise Exception("DB pool oluşturulamadı!")
    return db_pool


@contextmanager
def get_conn():
    p = get_pool()
    conn = p.getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS locked_chats (
                    chat_id TEXT PRIMARY KEY
                );
            """)


# ── Cache ─────────────────────────────────────────────────────────────────
cache_locked = set()
cache_ready  = False


def load_cache():
    global cache_locked, cache_ready
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM locked_chats")
            cache_locked = {r[0] for r in cur.fetchall()}
    cache_ready = True
    logger.info(f"Cache yüklendi: {len(cache_locked)} kilitli grup")


def is_locked(chat_id) -> bool:
    return str(chat_id) in cache_locked


def lock_chat(chat_id):
    cid = str(chat_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO locked_chats (chat_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (cid,)
            )
    cache_locked.add(cid)


def unlock_chat(chat_id):
    cid = str(chat_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM locked_chats WHERE chat_id=%s", (cid,))
    cache_locked.discard(cid)


# ── Pyrogram (userbot) — sadece medya silme için ────────────────────────────
pyro = Client(
    "media_guard",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    sleep_threshold=60,
    in_memory=True,
)


@pyro.on_message(filters.group)
async def delete_media(client: Client, message: Message):
    if message.chat.id not in GROUP_IDS:
        return
    if not cache_ready:
        return
    if not is_locked(message.chat.id):
        return

    media = (
        message.photo or
        message.video or
        message.document or
        message.audio or
        message.voice or
        message.video_note or
        message.sticker or
        message.animation
    )
    if media:
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Silme hatası: {e}")


# ── Bot API (python-telegram-bot) — komutlara cevap için ───────────────────
def ensure_group(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("🚫 Bu komut sadece gruplarda çalışır!")
            return
        return await func(update, ctx)
    return wrapper


async def is_admin_or_founder(update: Update) -> bool:
    user = update.effective_user
    if user.id == FOUNDER_ID:
        return True
    member = await update.effective_chat.get_member(user.id)
    return member.status in ("administrator", "creator")


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Merhaba! Ben bir *medya kilit botuyum*.\n\n"
        "📌 Komutlar:\n"
        "• `/lock` — Medya paylaşımını kapatır (foto, video, sticker, GIF, ses, belge)\n"
        "• `/unlock` — Medya paylaşımını açar\n"
        "• `/durum` — Mevcut kilit durumunu gösterir\n\n"
        "⚠️ Komutları sadece grup yöneticileri kullanabilir.",
        parse_mode="Markdown"
    )


@ensure_group
async def cmd_lock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in GROUP_IDS:
        await update.message.reply_text("🚫 Bot bu grupta aktif değil.")
        return
    if not await is_admin_or_founder(update):
        await update.message.reply_text("🚫 Bu komutu sadece yöneticiler kullanabilir!")
        return
    lock_chat(update.effective_chat.id)
    await update.message.reply_text(
        "🔒 Medya paylaşımı kapatıldı!\n"
        "Artık fotoğraf, video, sticker, GIF, ses ve belge mesajları otomatik silinecek."
    )


@ensure_group
async def cmd_unlock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in GROUP_IDS:
        await update.message.reply_text("🚫 Bot bu grupta aktif değil.")
        return
    if not await is_admin_or_founder(update):
        await update.message.reply_text("🚫 Bu komutu sadece yöneticiler kullanabilir!")
        return
    unlock_chat(update.effective_chat.id)
    await update.message.reply_text("🔓 Medya paylaşımı açıldı! Medya mesajları artık silinmeyecek.")


@ensure_group
async def cmd_durum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    durum = "🔒 Kapalı (medya siliniyor)" if is_locked(update.effective_chat.id) else "🔓 Açık (medya silinmiyor)"
    await update.message.reply_text(f"📡 Medya Durumu: {durum}")


async def post_init(app: Application):
    init_db()
    load_cache()

    await pyro.start()
    logger.info("Pyrogram başladı!")

    # KRİTİK ADIM: yeni session, restart sonrası grup hakkında bilgi
    # (access_hash) içermiyor. get_chat çağırmadan gerçek zamanlı mesajlar
    # bazen kaçırılabiliyor. Bu yüzden başlangıçta her grubu mutlaka tanıtıyoruz.
    for gid in GROUP_IDS:
        try:
            chat = await pyro.get_chat(gid)
            logger.info(f"Grup tanındı: {chat.title} ({gid})")
        except Exception as e:
            logger.warning(f"Grup tanınamadı {gid}: {e}")


async def post_shutdown(app: Application):
    try:
        await pyro.stop()
    except Exception:
        pass


def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("lock",   cmd_lock))
    app.add_handler(CommandHandler("unlock", cmd_unlock))
    app.add_handler(CommandHandler("durum",  cmd_durum))

    logger.info("Bot başladı...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
