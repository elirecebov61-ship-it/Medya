"""
Telegram Userbot + Bot Hibrit Sistemi (Railway sürümü)
----------------------------------------------------------
Mantık:
  - USERBOT (senin hesabın, SESSION_STRING ile): grupta medya geldiğinde
    siler, /lock veya /unlock yazdığında o komut mesajını siler.
  - BOT (BotFather token ile, BOT_TOKEN): kullanıcıya görünen metin
    cevaplarını ("Kilit aktif edildi" gibi) gönderir.

KOMUTLAR (sadece SEN, hesap sahibi, grupta yazınca çalışır):
  /lock    -> kilidi açar, sonrasında gelen TÜM medyalar (kendi gönderdiğin
              dahil) otomatik silinir
  /unlock  -> kilidi kapatır

GEREKEN ORTAM DEĞİŞKENLERİ (Railway > Variables):
  API_ID          -> my.telegram.org
  API_HASH        -> my.telegram.org
  SESSION_STRING  -> generate_session.py ile üretilir (userbot hesabı)
  BOT_TOKEN       -> @BotFather'dan alınan token (yeni bir bot oluştur)

NOT: BOT_TOKEN ile oluşturduğun botu da gruba EKLEMEN gerekir, aksi halde
     bot grupta mesaj gönderemez (admin olması gerekmiyor, sadece üye olması
     yeterli, çünkü silme işini userbot yapıyor).
"""

import asyncio
import json
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not SESSION_STRING:
    raise SystemExit(
        "HATA: SESSION_STRING ortam değişkeni boş veya tanımlı değil.\n"
        "generate_session.py çıktısını TEK SATIR halinde, boşluk/tırnak olmadan yapıştır."
    )

if not BOT_TOKEN:
    raise SystemExit(
        "HATA: BOT_TOKEN ortam değişkeni boş veya tanımlı değil.\n"
        "@BotFather'dan yeni bir bot oluştur ve token'ı BOT_TOKEN olarak ekle."
    )

STATE_FILE = "lock_state.json"

user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient("bot_session", API_ID, API_HASH)


def load_locked_chats():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_locked_chats(chats):
    with open(STATE_FILE, "w") as f:
        json.dump(list(chats), f)


locked_chats = load_locked_chats()


@user_client.on(events.NewMessage(outgoing=True))
async def command_handler(event):
    if not event.text:
        return
    text = event.text.strip().lower()

    if text == "/lock":
        locked_chats.add(event.chat_id)
        save_locked_chats(locked_chats)
        try:
            await event.delete()
        except Exception as e:
            print(f"komut silme hatası: {e}")
        try:
            await bot_client.send_message(
                event.chat_id,
                "🔒 Kilit aktif edildi. Bu sohbete gelen tüm medyalar otomatik silinecek.",
            )
        except Exception as e:
            print(f"bot mesaj gönderme hatası: {e}")

    elif text == "/unlock":
        try:
            await event.delete()
        except Exception as e:
            print(f"komut silme hatası: {e}")

        if event.chat_id in locked_chats:
            locked_chats.discard(event.chat_id)
            save_locked_chats(locked_chats)
            msg = "🔓 Kilit kaldırıldı. Medya paylaşımına artık izin veriliyor."
        else:
            msg = "ℹ️ Bu sohbette kilit zaten aktif değildi."

        try:
            await bot_client.send_message(event.chat_id, msg)
        except Exception as e:
            print(f"bot mesaj gönderme hatası: {e}")


@user_client.on(events.NewMessage())
async def media_killer(event):
    if event.chat_id not in locked_chats:
        return

    if event.media:
        print(f"[MEDYA SİLİNİYOR] chat_id={event.chat_id}")
        try:
            await event.delete()
        except Exception as e:
            print(f"silme hatası: {e}")


async def main():
    print("Userbot ve bot başlatılıyor...")
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)
    print("Hazır. /lock ve /unlock komutlarını kullanabilirsin.")
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


asyncio.run(main())
