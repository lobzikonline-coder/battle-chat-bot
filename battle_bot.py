import logging
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

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


# 🔹 Render порт-listener (щоб Web Service не падав)
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


BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = ZoneInfo("Europe/Uzhgorod")
POST_AT = time(21, 0, tzinfo=TZ)

counts_by_chat = defaultdict(lambda: defaultdict(int))
last_leader_by_chat = {}

logging.basicConfig(level=logging.INFO)


def user_key(update: Update) -> str:
    u = update.effective_user
    if u.username:
        return f"@{u.username}"
    return u.full_name


async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
thread_id = update.message.message_thread_id

await update.message.reply_text(
    f"chat_id: {chat_id}\n"
    f"thread_id: {thread_id}"
)


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await post_report(context, update.effective_chat.id)


async def count_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and not update.effective_user.is_bot:
        chat_id = update.effective_chat.id
        user = user_key(update)
        counts_by_chat[chat_id][user] += 1


async def post_report(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    data = counts_by_chat.get(chat_id, {})
    if not data:
        return

    top = sorted(data.items(), key=lambda x: x[1], reverse=True)[:5]
    leader = top[0][0]

    last = last_leader_by_chat.get(chat_id)
    if last is None:
        status_line = "🆕 Новий чемпіон."
    elif last == leader:
        status_line = "🛡 Захистив трон."
    else:
        status_line = "🔄 Зміна лідера."

    last_leader_by_chat[chat_id] = leader

    titles = ["👑 ТРОН", "⚡ ПРЕТЕНДЕНТ", "🔥 У БОРОТЬБІ", "🚀 ДОГАНЯЄ", "🎯 НА ХВОСТІ"]

    message = "⚔ БИТВА АКТИВНОСТІ • 21:00\n\n"
    for i, (name, cnt) in enumerate(top):
        message += f"{titles[i]} — {name} ({cnt})\n"

    message += (
        f"\nСьогодні для 👑 потрібно було: {top[0][1]} повідомлень.\n\n"
        f"{status_line}\n"
        "Завтра — новий раунд."
    )

    await context.bot.send_message(chat_id=chat_id, text=message)
    counts_by_chat[chat_id].clear()


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(counts_by_chat.keys()):
        await post_report(context, chat_id)


def main():
    # 🔹 запускаємо порт-listener окремим потоком
    threading.Thread(target=start_port_listener, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, count_all))

    app.job_queue.run_daily(daily_job, time=POST_AT)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
