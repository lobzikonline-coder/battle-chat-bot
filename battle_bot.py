import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# Render keep-alive (простий HTTP сервер)
# =========================
def start_port_listener():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            return  # щоб не спамило логами

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


# =========================
# CONFIG
# =========================
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables!")

# Куди постимо звіт (твоя “одна гілка”)
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1001825943882"))
TARGET_THREAD_ID = int(os.getenv("TARGET_THREAD_ID", "47455"))

# Час щоденного звіту
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Uzhgorod"))
POST_AT = time(
    int(os.getenv("POST_HOUR", "21")),
    int(os.getenv("POST_MINUTE", "0")),
    tzinfo=TZ
)

# Файл картинки (має бути в репозиторії)
PODIUM_IMAGE = os.getenv("PODIUM_IMAGE", "zimin_cargo_podium.png")

# =========================
# STORAGE (рахуємо по всіх чатах, один загальний рейтинг)
# =========================
counts_global = defaultdict(int)  # { "username/fullname": count }
last_leader = None


def user_key(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "Unknown"
    if u.username:
        return f"@{u.username}"
    # full_name може бути None — підстрахуємося
    return (u.full_name or "Unknown").strip()


async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує chat_id і thread_id поточної точки"""
    chat_id = update.effective_chat.id if update.effective_chat else None
    thread_id = getattr(update.message, "message_thread_id", None) if update.message else None

    await update.message.reply_text(
        f"chat_id: {chat_id}\nthread_id: {thread_id}"
    )


async def count_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рахує всі повідомлення за день по всіх чатах."""
    if not update.effective_user:
        return
    # не рахуємо ботів
    if update.effective_user.is_bot:
        return
    # інколи update.message може бути None (наприклад, service updates)
    if not update.message:
        return

    key = user_key(update)
    counts_global[key] += 1


def build_status_line(new_leader: str) -> str:
    global last_leader
    if last_leader is None:
        last_leader = new_leader
        return "🆕 Новий чемпіон."
    if last_leader == new_leader:
        return "🛡️ Захистив трон."
    last_leader = new_leader
    return "🔁 Зміна лідера."


async def post_report(context: ContextTypes.DEFAULT_TYPE):
    """Формує і відправляє щоденний звіт в ОДНУ гілку, потім обнуляє."""
    if not counts_global:
        # Навіть якщо ніхто не писав — можна не постити взагалі.
        # Якщо хочеш постити "0" — скажи, зроблю.
        return

    top = sorted(counts_global.items(), key=lambda x: x[1], reverse=True)
    leader_name, leader_cnt = top[0]
    status_line = build_status_line(leader_name)

    medals = ["🥇", "🥈", "🥉"]

    message = ""
    message += "🇨🇳 Zimin Cargo • Склад закрито\n\n"
    message += "Обʼєм повідомлень пораховано.\n"
    message += "Вага зафіксована.\n\n"

    for i, (name, cnt) in enumerate(top[:3]):
        message += f"{medals[i]} {name} — {cnt}\n"

    message += f"\nСьогоднішній максимум — {leader_cnt} повідомлень.\n\n"
    message += "Підсумок формується щодня о 21:00.\n"
    message += "Рахуються всі повідомлення за день.\n\n"
    message += "Завтра склад відкривається з нуля.\n"
    message += "І обʼєм знову вирішує.\n\n"
    message += f"{status_line}"

    # Надсилаємо фото + caption
    try:
        with open(PODIUM_IMAGE, "rb") as photo:
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=photo,
                caption=message,
                message_thread_id=TARGET_THREAD_ID,
            )
    except FileNotFoundError:
        # Якщо картинки нема — просто відправляємо текстом (щоб звіт не зірвався)
        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=message,
            message_thread_id=TARGET_THREAD_ID,
        )

    # ОБНУЛЯЄМО НА НОВИЙ ДЕНЬ
    counts_global.clear()


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручний запуск звіту (/report)"""
    await post_report(context)


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    """Щоденний джоб о 21:00"""
    await post_report(context)


def main():
    # Keep-alive для Render
    threading.Thread(target=start_port_listener, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("report", report_cmd))

    # Рахуємо ВСІ повідомлення (текст/медіа/стікери — все)
    app.add_handler(MessageHandler(filters.ALL, count_all))

    # Щоденний звіт
    app.job_queue.run_daily(daily_job, time=POST_AT)

    # Старт
    # drop_pending_updates=True прибирає “хвіст” апдейтів після перезапуску
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
