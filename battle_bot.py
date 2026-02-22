import os
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

# =========================
# НАЛАШТУВАННЯ (ТВОЇ ДАНІ)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Куди САМЕ писати щоденний звіт (одна конкретна "гілка"/топік у групі)
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID", "-1001825943882"))
REPORT_THREAD_ID = int(os.getenv("REPORT_THREAD_ID", "47455"))

# Час звіту
TZ = ZoneInfo(os.getenv("TZ", "Europe/Uzhgorod"))
POST_AT = time(21, 0, tzinfo=TZ)

# URL твого Render-сервісу (важливо для webhook!)
# Приклад: https://battle-chat-bot.onrender.com
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

# Якщо хочеш картинку-шаблон у звіт:
# 1) закинь картинку в репозиторій як report_template.png (в корінь поруч з battle_bot.py)
# 2) увімкни USE_REPORT_IMAGE=1
USE_REPORT_IMAGE = os.getenv("USE_REPORT_IMAGE", "0") == "1"

# =========================
# ЛОГИ
# =========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("battle-bot")

# =========================
# ПАМʼЯТЬ (рахуємо за день)
# =========================
# Рахуємо ВСІ повідомлення в будь-яких гілках/топіках.
# Якщо у тебе 1 група з темами — цього достатньо.
counts_global = defaultdict(int)  # user -> count


def user_key(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "Unknown"
    if u.username:
        return f"@{u.username}"
    return (u.full_name or "Unknown").strip()


async def count_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рахує кожне повідомлення (крім ботів)."""
    if not update.effective_user or update.effective_user.is_bot:
        return

    chat = update.effective_chat
    if not chat:
        return

    # Рахуємо тільки групи/супергрупи (щоб приватні чати не лізли в рейтинг)
    if chat.type not in ("group", "supergroup"):
        return

    user = user_key(update)
    counts_global[user] += 1


def build_report_text(top_items: list[tuple[str, int]]) -> str:
    # Твій стиль: стримано, товарно, але з мотивацією
    # Без команд, без зайвих знаків
    header = "🇨🇳 Zimin Cargo • Склад закрито\n\n"
    header += "Обʼєм повідомлень пораховано.\n"
    header += "Вага зафіксована.\n\n"

    podium = ""
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (name, cnt) in enumerate(top_items):
        medal = medals[i] if i < len(medals) else "•"
        podium += f"{medal} {name} — {cnt}\n"

    max_cnt = top_items[0][1] if top_items else 0

    footer = "\n"
    footer += f"Сьогоднішній максимум — {max_cnt} повідомлень.\n\n"
    footer += "Підсумок формується щодня о 21:00.\n"
    footer += "Рахуються всі повідомлення за день.\n\n"
    footer += "Завтра склад відкривається з нуля.\n"
    footer += "І обʼєм знову вирішує."

    return header + podium + footer


async def post_report(app: Application):
    """Надіслати звіт в ОДНУ конкретну гілку + обнулити лічильники."""
    if not counts_global:
        # Нема активності — можна або мовчати, або дати короткий "склад пустий"
        text = (
            "🇨🇳 Zimin Cargo • Склад закрито\n\n"
            "Сьогодні склад був тихий.\n"
            "Обʼєм майже нульовий.\n\n"
            "Завтра відкриваємось з нуля.\n"
            "І обʼєм знову вирішує."
        )
        await app.bot.send_message(
            chat_id=REPORT_CHAT_ID,
            message_thread_id=REPORT_THREAD_ID,
            text=text,
        )
        return

    top = sorted(counts_global.items(), key=lambda x: x[1], reverse=True)[:5]
    text = build_report_text(top)

    if USE_REPORT_IMAGE and PUBLIC_URL:
        # Надсилаємо картинку як "шапку" + текст
        # Картинка лежить у репі як report_template.png і віддається через /report.png
        photo_url = f"{PUBLIC_URL}/report.png"
        await app.bot.send_photo(
            chat_id=REPORT_CHAT_ID,
            message_thread_id=REPORT_THREAD_ID,
            photo=photo_url,
            caption=text,
        )
    else:
        await app.bot.send_message(
            chat_id=REPORT_CHAT_ID,
            message_thread_id=REPORT_THREAD_ID,
            text=text,
        )

    counts_global.clear()


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await post_report(context.application)


# =========================
# WEBHOOK HANDLERS (Render)
# =========================
from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder
from telegram.ext.webhookhandler import WebhookHandler
from aiohttp import web


async def health(request):
    return web.Response(text="OK", content_type="text/plain")


async def report_image(request):
    # Віддаємо локальну картинку-шаблон (якщо ти її додаси в репозиторій)
    # Файл: report_template.png
    path = os.path.join(os.path.dirname(__file__), "report_template.png")
    if not os.path.exists(path):
        return web.Response(status=404, text="No template image")
    return web.FileResponse(path)


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Add it in Render Environment Variables.")

    request = HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=30, pool_timeout=30)
    application = Application.builder().token(BOT_TOKEN).request(request).build()

    # Команди для діагностики (можеш не використовувати; на роботу звіту не впливає)
    async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Працюю ✅")

    async def testreport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await post_report(context.application)

    application.add_handler(CommandHandler("ping", ping_cmd))
    application.add_handler(CommandHandler("testreport", testreport_cmd))

    # Рахуємо всі повідомлення
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, count_all))

    # Щоденний звіт о 21:00
    application.job_queue.run_daily(daily_job, time=POST_AT)

    return application


async def main():
    if not PUBLIC_URL:
        raise RuntimeError("PUBLIC_URL is empty. Add it in Render Environment Variables.")

    port = int(os.environ.get("PORT", "10000"))
    application = build_app()

    # aiohttp server
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/report.png", report_image)

    webhook_path = "/telegram"
    webhook_url = f"{PUBLIC_URL}{webhook_path}"

    # Telegram webhook handler
    webhook_handler = WebhookHandler(application, webhook_path)
    webhook_handler.register(app)

    # Set webhook (важливо: remove old webhook/polling conflicts)
    await application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)

    await application.initialize()
    await application.start()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    log.info("Webhook listening on %s, health: %s", port, PUBLIC_URL)

    # тримаємо процес живим
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
