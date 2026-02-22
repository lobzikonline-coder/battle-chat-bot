import os
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo
from collections import defaultdict

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from aiohttp import web


# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID", "0"))
REPORT_THREAD_ID = int(os.getenv("REPORT_THREAD_ID", "0"))
COUNT_CHAT_ID = os.getenv("COUNT_CHAT_ID")  # якщо хочеш рахувати тільки в одному чаті
PORT = int(os.getenv("PORT", "10000"))

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# шлях до картинки
REPORT_IMAGE_PATH = "assets/zimin_cargo.png"

# =========================
# STORAGE
# =========================
counts = defaultdict(int)
names = {}
current_day = None


def today_str():
    return datetime.now(KYIV_TZ).strftime("%Y-%m-%d")


def display_name(update: Update):
    user = update.effective_user
    if not user:
        return "Unknown"
    if user.username:
        return f"@{user.username}"
    return (user.first_name or "") + (" " + user.last_name if user.last_name else "")


def should_count(update: Update):
    if COUNT_CHAT_ID is None:
        return True
    return str(update.effective_chat.id) == COUNT_CHAT_ID


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_day

    if not update.message or not update.effective_user:
        return

    today = today_str()

    if current_day is None:
        current_day = today
    elif current_day != today:
        counts.clear()
        names.clear()
        current_day = today

    if not should_count(update):
        return

    uid = update.effective_user.id
    counts[uid] += 1
    names[uid] = display_name(update)


def build_podium_text(top3):
    medals = ["🥇", "🥈", "🥉"]

    lines = []
    for i in range(3):
        if i < len(top3):
            uid, c = top3[i]
            nm = names.get(uid, f"id{uid}")
            lines.append(f"{medals[i]} {nm} — {c}")
        else:
            lines.append(f"{medals[i]} —")

    max_val = top3[0][1] if top3 else 0

    return (
        "🇨🇳 <b>Zimin Cargo</b>\n"
        "<b>Склад закрито</b>\n\n"
        "Обʼєм повідомлень пораховано.\n"
        "Вага зафіксована.\n\n"
        f"{lines[0]}\n"
        f"{lines[1]}\n"
        f"{lines[2]}\n\n"
        f"Сьогоднішній максимум — <b>{max_val}</b> повідомлень.\n\n"
        "Завтра склад відкривається з нуля.\n"
        "І обʼєм знову вирішує."
    )


async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    global current_day

    sorted_users = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    top3 = sorted_users[:3]

    text = build_podium_text(top3)

    if REPORT_CHAT_ID == 0:
        return

    if os.path.exists(REPORT_IMAGE_PATH):
        with open(REPORT_IMAGE_PATH, "rb") as f:
            await context.bot.send_photo(
                chat_id=REPORT_CHAT_ID,
                message_thread_id=REPORT_THREAD_ID if REPORT_THREAD_ID != 0 else None,
                photo=f,
                caption=text,
                parse_mode="HTML",
            )
    else:
        await context.bot.send_message(
            chat_id=REPORT_CHAT_ID,
            message_thread_id=REPORT_THREAD_ID if REPORT_THREAD_ID != 0 else None,
            text=text,
            parse_mode="HTML",
        )

    counts.clear()
    names.clear()
    current_day = today_str()


async def test_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_report(context)
    await update.message.reply_text("Звіт відправлено.")


# =========================
# RENDER WEB SERVER
# =========================
async def health(request):
    return web.Response(text="OK")


async def run_web_server():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[WEB] Listening on {PORT}")


# =========================
# MAIN
# =========================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_message))
    application.add_handler(CommandHandler("testreport", test_report))

    # щодня о 21:00 по Києву
    application.job_queue.run_daily(
        send_daily_report,
        time=time(21, 0, tzinfo=KYIV_TZ),
        name="daily_podium",
    )

    await run_web_server()

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)

    print("[BOT] Started")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
