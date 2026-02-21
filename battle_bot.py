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

BOT_TOKEN = "7957872868:AAEKNNix_70UF6CwqQh-49M1SCt
im fNhBg4"
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
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

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

    message += f"\nСьогодні для 👑 потрібно було: {top[0][1]} повідомлень.\n\n{status_line}\nЗавтра — новий раунд."

    await context.bot.send_message(chat_id=chat_id, text=message)
    counts_by_chat[chat_id].clear()

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(counts_by_chat.keys()):
        await post_report(context, chat_id)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, count_all))

    app.job_queue.run_daily(daily_job, time=POST_AT)

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
