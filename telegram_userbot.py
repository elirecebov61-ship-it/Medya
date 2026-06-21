"""
Telegram Userbot - Medya Kilit Sistemi (Railway sürümü)
----------------------------------------------------------
/lock  yazdığında, o sohbette gönderilen TÜM medya mesajları
       (foto, video, sticker, GIF, dosya vb.) anında otomatik silinir.
/unlock yazdığında kilit kaldırılır.

NOT: Bu script SENİN kendi Telegram hesabınla çalışır (userbot, bot değil).
     /lock ve /unlock komutlarını SADECE hesap sahibi (sen) yazabilir,
     çünkü komutlar "outgoing" (kendi gönderdiğin) mesaj olarak filtrelenir.

NOT 2: Grup üyelerinin medyasını silebilmek için o grupta "mesaj silme"
       yetkisine (admin) sahip olman gerekir.

Railway'de ortam değişkenleri (Environment Variables) olarak ayarla:
    API_ID         -> my.telegram.org'dan
    API_HASH       -> my.telegram.org'dan
    SESSION_STRING -> generate_session.py çalıştırarak elde edilir
"""

import json
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()

if not SESSION_STRING:
    raise SystemExit(
        "HATA: SESSION_STRING ortam değişkeni boş veya tanımlı değil.\n"
        "Railway > Variables bölümünde SESSION_STRING'in dolu olduğundan emin ol,\n"
        "generate_session.py çıktısını TEK SATIR halinde, boşluk/tırnak olmadan yapıştır."
    )

STATE_FILE = "lock_state.json"

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


def load_locked_chats():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_locked_chats(chats):
    with open(STATE_FILE, "w") as f:
        json.dump(list(chats), f)


locked_chats = load_locked_chats()


@client.on(events.NewMessage(pattern=r"^/lock$", outgoing=True))
async def lock_handler(event):
    locked_chats.add(event.chat_id)
    save_locked_chats(locked_chats)
    await event.edit("🔒 Kilit aktif edildi. Bu sohbete gelen tüm medyalar otomatik silinecek.")


@client.on(events.NewMessage(pattern=r"^/unlock$", outgoing=True))
async def unlock_handler(event):
    if event.chat_id in locked_chats:
        locked_chats.discard(event.chat_id)
        save_locked_chats(locked_chats)
        await event.edit("🔓 Kilit kaldırıldı. Medya paylaşımına artık izin veriliyor.")
    else:
        await event.edit("ℹ️ Bu sohbette kilit zaten aktif değildi.")


@client.on(events.NewMessage())
async def media_killer(event):
    if event.chat_id not in locked_chats:
        return

    if event.out:
        return

    if event.media:
        try:
            await event.delete()
        except Exception:
            pass


print("Userbot başlatılıyor...")
client.start()
print("Userbot aktif. /lock ve /unlock komutlarını kullanabilirsin.")
client.run_until_disconnected()

