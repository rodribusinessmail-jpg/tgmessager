"""
Telegram Scheduler Bot - Complete Edition
- Sendet Nachrichten in deinem Namen
- Pagination fuer Chats (8 pro Seite)
- Bestaetigung nach jedem Senden
- Railway-ready
"""

import os, json, asyncio, logging, threading
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telethon import TelegramClient
from telethon.tl.types import Chat, Channel
import schedule, time, qrcode

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID    = int(os.getenv("API_ID", "0"))
API_HASH  = os.getenv("API_HASH", "")
PHONE     = os.getenv("PHONE", "")
OWNER_ID  = int(os.getenv("OWNER_ID", "0"))

DATA_FILE      = Path("data.json")
SESSION_FILE   = "user_session"
CHATS_PER_PAGE = 8

ASK_NAME, ASK_TEXT, ASK_TIME, ASK_DAYS, ASK_CHATS, CONFIRM, ASK_2FA = range(7)

DAYS_DE = {
    "mon": "Montag", "tue": "Dienstag", "wed": "Mittwoch",
    "thu": "Donnerstag", "fri": "Freitag", "sat": "Samstag", "sun": "Sonntag"
}
ALL_DAYS = list(DAYS_DE.keys())

# ── Data ──────────────────────────────────────────────────────────────────────

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"messages": [], "chats": []}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Telethon ──────────────────────────────────────────────────────────────────

tg_loop = asyncio.new_event_loop()
tg_client = None
tg_connected = False

threading.Thread(
    target=lambda: (asyncio.set_event_loop(tg_loop), tg_loop.run_forever()),
    daemon=True
).start()

def tg_run(coro, timeout=30):
    return asyncio.run_coroutine_threadsafe(coro, tg_loop).result(timeout=timeout)

def make_client():
    return TelegramClient(
        SESSION_FILE, API_ID, API_HASH, loop=tg_loop,
        connection_retries=3, retry_delay=2, timeout=20
    )

async def _init_client():
    global tg_client, tg_connected
    tg_client = make_client()
    await tg_client.connect()
    if await tg_client.is_user_authorized():
        tg_connected = True
        return True
    return False

async def _get_chats():
    chats = []
    async for d in tg_client.iter_dialogs(limit=300):
        e = d.entity
        t = "private"
        if isinstance(e, Chat): t = "group"
        elif isinstance(e, Channel): t = "channel" if e.broadcast else "supergroup"
        chats.append({"id": d.id, "name": d.name, "type": t})
    return chats

async def _send_msg(chat_id, text):
    await tg_client.send_message(chat_id, text)

# ── Guards ────────────────────────────────────────────────────────────────────

def owner_only(func):
    async def wrapper(update: Update, ctx):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Kein Zugriff.")
            return
        return await func(update, ctx)
    return wrapper

def owner_cb(func):
    async def wrapper(update: Update, ctx):
        if update.effective_user.id != OWNER_ID:
            await update.callback_query.answer("Kein Zugriff.")
            return
        return await func(update, ctx)
    return wrapper

# ── Scheduler ─────────────────────────────────────────────────────────────────

_bot_app = None

def resolve_vars(text):
    n = datetime.now()
    days_de = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
    return (text
        .replace("{datum}", n.strftime("%d.%m.%Y"))
        .replace("{uhrzeit}", n.strftime("%H:%M"))
        .replace("{wochentag}", days_de[n.weekday()]))

def notify(text):
    if _bot_app:
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                _bot_app.bot.send_message(
                    chat_id=OWNER_ID, text=text, parse_mode="Markdown"
                ),
                loop
            )
        except Exception as e:
            logger.error(f"Notify error: {e}")

def do_send(msg):
    if not tg_connected:
        logger.warning(f"Nicht verbunden - '{msg['name']}' uebersprungen")
        notify("Nicht verbunden - '" + msg['name'] + "' konnte nicht gesendet werden!")
        return

    text = resolve_vars(msg["text"])
    sent, failed = [], []

    for chat in msg.get("targets", []):
        try:
            tg_run(_send_msg(chat["id"], text))
            sent.append(chat["name"])
            logger.info(f"Sent '{msg['name']}' to {chat['name']}")
        except Exception as e:
            failed.append(chat["name"] + " (" + str(e) + ")")

    report = "*" + msg['name'] + "* gesendet!\n\n"
    if sent:
        report += "Erfolgreich:\n" + "\n".join("  * " + c for c in sent)
    if failed:
        report += "\n\nFehlgeschlagen:\n" + "\n".join("  * " + c for c in failed)
    report += "\n\n" + datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    notify(report)

    data = load_data()
    for m in data["messages"]:
        if m["id"] == msg["id"]:
            m["last_sent"] = datetime.now().isoformat()
    save_data(data)

DAYS_SCHED = {
    "mon": schedule.every().monday,
    "tue": schedule.every().tuesday,
    "wed": schedule.every().wednesday,
    "thu": schedule.every().thursday,
    "fri": schedule.every().friday,
    "sat": schedule.every().saturday,
    "sun": schedule.every().sunday,
}

def rebuild_schedule():
    schedule.clear()
    data = load_data()
    for msg in data["messages"]:
        if not msg.get("active", True):
            continue
        t = msg.get("time", "08:00")
        parts = t.split(":")
        t = str(int(parts[0])).zfill(2) + ":" + str(int(parts[1])).zfill(2)
        for day in msg.get("days", ALL_DAYS):
            if day in DAYS_SCHED:
                DAYS_SCHED[day].at(t).do(do_send, msg)
    logger.info("Schedule rebuilt - " + str(len(data["messages"])) + " Nachrichten")

def schedule_loop():
    while True:
        schedule.run_pending()
        time.sleep(10)

threading.Thread(target=schedule_loop, daemon=True).start()

# ── QR Login ──────────────────────────────────────────────────────────────────

def make_qr_image(url):
    qr = qrcode.QRCode(box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    pil = img.get_image() if hasattr(img, 'get_image') else img
    pil.save(bio, format="PNG")
    bio.seek(0)
    return bio

async def qr_login_task(chat_id, bot, ctx):
    global tg_client, tg_connected
    try:
        tg_client = make_client()
        tg_run(tg_client.connect())

        if tg_run(tg_client.is_user_authorized()):
            tg_connected = True
            me = tg_run(tg_client.get_me())
            await bot.send_message(
                chat_id,
                "Bereits eingeloggt als " + me.first_name + "!"
            )
            rebuild_schedule()
            return

        qr = tg_run(tg_client.qr_login(), timeout=15)
        img = make_qr_image(qr.url)
        await bot.send_photo(
            chat_id=chat_id, photo=img,
            caption="QR-Code scannen:\n\nTelegram App -> Einstellungen -> Geraete -> Geraet verbinden"
        )

        for attempt in range(6):
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    asyncio.wait_for(qr.wait(), timeout=25), tg_loop
                )
                fut.result(timeout=30)
                tg_connected = True
                me = tg_run(tg_client.get_me())
                await bot.send_message(
                    chat_id,
                    "Eingeloggt als " + me.first_name + "! Nutze /add um loszulegen"
                )
                rebuild_schedule()
                return
            except Exception as e:
                err = str(e)
                if "SESSION_PASSWORD_NEEDED" in err or "password" in err.lower():
                    ctx.user_data["needs_2fa"] = True
                    await bot.send_message(
                        chat_id,
                        "QR gescannt! Bitte jetzt dein 2FA-Passwort eingeben:"
                    )
                    return
                try:
                    tg_run(qr.recreate(), timeout=10)
                    img = make_qr_image(qr.url)
                    await bot.send_photo(
                        chat_id, img,
                        caption="Neuer QR-Code - bitte nochmal scannen (Versuch " + str(attempt+2) + "/6)"
                    )
                except:
                    break

        await bot.send_message(chat_id, "Timeout. Bitte /login nochmal versuchen.")
    except Exception as e:
        await bot.send_message(chat_id, "Fehler: " + str(e) + "\nBitte /login nochmal.")

# ── Commands ──────────────────────────────────────────────────────────────────

@owner_only
async def cmd_start(update: Update, ctx):
    status = "Verbunden" if tg_connected else "Nicht verbunden - /login"
    data = load_data()
    active = sum(1 for m in data["messages"] if m.get("active", True))
    await update.message.reply_text(
        "Telegram Scheduler\n\n"
        "Status: " + status + "\n"
        "Aktive Nachrichten: " + str(active) + "\n\n"
        "/login - Verbinden\n"
        "/add - Neue Nachricht\n"
        "/list - Nachrichten\n"
        "/chats - Chats laden\n"
        "/status - Status\n"
        "/help - Hilfe"
    )

@owner_only
async def cmd_status(update: Update, ctx):
    if tg_connected:
        me = tg_run(tg_client.get_me())
        await update.message.reply_text(
            "Verbunden als " + me.first_name + "\n+" + str(me.phone)
        )
    else:
        await update.message.reply_text("Nicht verbunden. /login")

@owner_only
async def cmd_help(update: Update, ctx):
    await update.message.reply_text(
        "Hilfe\n\n"
        "Variablen:\n"
        "{datum} - 01.04.2026\n"
        "{uhrzeit} - 08:00\n"
        "{wochentag} - Montag\n\n"
        "Befehle:\n"
        "/start /login /add /list /chats /status"
    )

@owner_only
async def cmd_login(update: Update, ctx):
    if tg_connected:
        await update.message.reply_text("Bereits verbunden!")
        return ConversationHandler.END
    await update.message.reply_text("Starte QR-Login...")
    asyncio.get_event_loop().create_task(
        qr_login_task(update.effective_chat.id, ctx.bot, ctx)
    )
    return ASK_2FA

async def handle_2fa(update: Update, ctx):
    global tg_connected
    if not ctx.user_data.get("needs_2fa"):
        return ASK_2FA
    pw = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    try:
        tg_run(tg_client.sign_in(password=pw))
        tg_connected = True
        me = tg_run(tg_client.get_me())
        ctx.user_data["needs_2fa"] = False
        await update.effective_chat.send_message(
            "Eingeloggt als " + me.first_name + "! Nutze /add"
        )
        rebuild_schedule()
        return ConversationHandler.END
    except:
        await update.effective_chat.send_message("Falsches Passwort! Nochmal eingeben:")
        return ASK_2FA

async def cancel(update: Update, ctx):
    await update.message.reply_text("Abgebrochen.")
    return ConversationHandler.END

@owner_only
async def cmd_chats(update: Update, ctx):
    if not tg_connected:
        await update.message.reply_text("Zuerst /login!")
        return
    await update.message.reply_text("Lade alle Chats...")
    chats = tg_run(_get_chats(), timeout=60)
    data = load_data()
    data["chats"] = chats
    save_data(data)
    await update.message.reply_text(str(len(chats)) + " Chats geladen!")

# ── Add Flow ──────────────────────────────────────────────────────────────────

@owner_only
async def cmd_add(update: Update, ctx):
    if not tg_connected:
        await update.message.reply_text("Zuerst /login!")
        return ConversationHandler.END
    ctx.user_data["msg"] = {}
    await update.message.reply_text(
        "Neue Nachricht\n\nSchritt 1/5: Name eingeben (z.B. Guten Morgen)"
    )
    return ASK_NAME

async def ask_name(update: Update, ctx):
    ctx.user_data["msg"]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Schritt 2/5: Nachrichtentext\n\nVariablen: {datum} {uhrzeit} {wochentag}"
    )
    return ASK_TEXT

async def ask_text(update: Update, ctx):
    ctx.user_data["msg"]["text"] = update.message.text.strip()
    await update.message.reply_text(
        "Schritt 3/5: Uhrzeit\n\nFormat: HH:MM (z.B. 08:00)"
    )
    return ASK_TIME

async def ask_time(update: Update, ctx):
    t = update.message.text.strip()
    try:
        h, m = t.split(":")
        assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        ctx.user_data["msg"]["time"] = str(int(h)).zfill(2) + ":" + str(int(m)).zfill(2)
    except:
        await update.message.reply_text("Falsches Format! Bitte HH:MM eingeben (z.B. 08:00)")
        return ASK_TIME
    ctx.user_data["selected_days"] = list(ALL_DAYS)
    await update.message.reply_text(
        "Schritt 4/5: Wochentage waehlen",
        reply_markup=days_keyboard(list(ALL_DAYS))
    )
    return ASK_DAYS

def days_keyboard(selected):
    rows = []
    row = []
    for k, v in DAYS_DE.items():
        icon = "+" if k in selected else "o"
        row.append(InlineKeyboardButton(icon + " " + v, callback_data="day_" + k))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("Alle", callback_data="days_all"),
        InlineKeyboardButton("Werktage", callback_data="days_work"),
        InlineKeyboardButton("Wochenende", callback_data="days_weekend"),
    ])
    rows.append([InlineKeyboardButton("Weiter ->", callback_data="days_done")])
    return InlineKeyboardMarkup(rows)

async def handle_days(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    d = q.data
    sel = ctx.user_data.get("selected_days", list(ALL_DAYS))

    if d == "days_all":
        sel = list(ALL_DAYS)
    elif d == "days_work":
        sel = ALL_DAYS[:5]
    elif d == "days_weekend":
        sel = ALL_DAYS[5:]
    elif d == "days_done":
        if not sel:
            await q.answer("Mindestens einen Tag!", show_alert=True)
            return ASK_DAYS
        ctx.user_data["msg"]["days"] = sel
        ctx.user_data["selected_chats"] = []
        ctx.user_data["chat_page"] = 0
        data = load_data()
        chats = data.get("chats", [])
        if not chats:
            chats = tg_run(_get_chats(), timeout=60)
            data["chats"] = chats
            save_data(data)
        ctx.user_data["all_chats"] = chats
        await q.edit_message_text(
            "Schritt 5/5: Chats auswaehlen\n\nSeite 1/" + str(max(1, (len(chats) + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE)),
            reply_markup=chats_keyboard(chats, [], 0)
        )
        return ASK_CHATS
    elif d.startswith("day_"):
        k = d[4:]
        if k in sel:
            sel.remove(k)
        else:
            sel.append(k)

    ctx.user_data["selected_days"] = sel
    try:
        await q.edit_message_reply_markup(days_keyboard(sel))
    except:
        pass
    return ASK_DAYS

def chats_keyboard(chats, selected_ids, page):
    icons = {"private": "P", "group": "G", "supergroup": "G", "channel": "C"}
    total = len(chats)
    total_pages = max(1, (total + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE)
    start = page * CHATS_PER_PAGE
    end = min(start + CHATS_PER_PAGE, total)

    rows = []
    for chat in chats[start:end]:
        icon = "[x]" if chat["id"] in selected_ids else "[ ]"
        name = chat["name"][:32]
        rows.append([InlineKeyboardButton(
            icon + " " + name,
            callback_data="chat_" + str(chat["id"])
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("< Zurueck", callback_data="page_" + str(page - 1)))
    nav.append(InlineKeyboardButton(
        str(page + 1) + "/" + str(total_pages),
        callback_data="page_info"
    ))
    if end < total:
        nav.append(InlineKeyboardButton("Weiter >", callback_data="page_" + str(page + 1)))
    rows.append(nav)
    rows.append([InlineKeyboardButton(
        "Fertig (" + str(len(selected_ids)) + " ausgewaehlt)",
        callback_data="chats_done"
    )])
    return InlineKeyboardMarkup(rows)

async def handle_chats(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    d = q.data

    chats = ctx.user_data.get("all_chats", [])
    selected = ctx.user_data.get("selected_chats", [])
    page = ctx.user_data.get("chat_page", 0)

    if d == "page_info":
        return ASK_CHATS

    elif d.startswith("page_"):
        page = int(d[5:])
        ctx.user_data["chat_page"] = page
        try:
            await q.edit_message_reply_markup(chats_keyboard(chats, selected, page))
        except:
            pass
        return ASK_CHATS

    elif d.startswith("chat_"):
        chat_id = int(d[5:])
        if chat_id in selected:
            selected.remove(chat_id)
        else:
            selected.append(chat_id)
        ctx.user_data["selected_chats"] = selected
        try:
            await q.edit_message_reply_markup(chats_keyboard(chats, selected, page))
        except:
            pass
        return ASK_CHATS

    elif d == "chats_done":
        if not selected:
            await q.answer("Mindestens einen Chat!", show_alert=True)
            return ASK_CHATS

        selected_objs = [c for c in chats if c["id"] in selected]
        ctx.user_data["msg"]["targets"] = selected_objs

        msg = ctx.user_data["msg"]
        days_text = ", ".join(DAYS_DE.get(x, x) for x in msg["days"])
        chats_text = "\n".join("  - " + c["name"] for c in selected_objs)

        confirm = (
            "Zusammenfassung:\n\n"
            "Name: " + msg["name"] + "\n"
            "Text: " + msg["text"] + "\n"
            "Uhrzeit: " + msg["time"] + "\n"
            "Tage: " + days_text + "\n"
            "Chats:\n" + chats_text + "\n\n"
            "Alles korrekt?"
        )
        await q.edit_message_text(
            confirm,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Speichern", callback_data="confirm_yes"),
                InlineKeyboardButton("Abbrechen", callback_data="confirm_no"),
            ]])
        )
        return CONFIRM

    return ASK_CHATS

async def handle_confirm(update: Update, ctx):
    q = update.callback_query
    await q.answer()

    if q.data == "confirm_yes":
        msg = ctx.user_data["msg"]
        data = load_data()
        msg["id"] = max((m.get("id", 0) for m in data["messages"]), default=0) + 1
        msg["active"] = True
        msg["created"] = datetime.now().isoformat()
        data["messages"].append(msg)
        save_data(data)
        rebuild_schedule()
        await q.edit_message_text(
            "Gespeichert! '" + msg["name"] + "' wird ab jetzt automatisch gesendet um " + msg["time"] + " Uhr"
        )
    else:
        await q.edit_message_text("Abgebrochen.")

    ctx.user_data.clear()
    return ConversationHandler.END

# ── List & Manage ─────────────────────────────────────────────────────────────

@owner_only
async def cmd_list(update: Update, ctx):
    data = load_data()
    msgs = data.get("messages", [])
    if not msgs:
        await update.message.reply_text("Keine Nachrichten. /add um eine zu erstellen.")
        return

    for msg in msgs:
        active = msg.get("active", True)
        days = ", ".join(DAYS_DE.get(d, d) for d in msg.get("days", []))
        chats = ", ".join(c["name"] for c in msg.get("targets", []))
        last = msg.get("last_sent", "Noch nie")
        if last != "Noch nie":
            try:
                last = datetime.fromisoformat(last).strftime("%d.%m %H:%M")
            except:
                pass

        status = "Aktiv" if active else "Pausiert"
        text = (
            status + " - " + msg["name"] + "\n"
            "Uhrzeit: " + msg["time"] + "\n"
            "Tage: " + days + "\n"
            "Chats: " + chats + "\n"
            "Zuletzt: " + last
        )
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Pausieren" if active else "Aktivieren",
                    callback_data="tog_" + str(msg["id"])
                ),
                InlineKeyboardButton("Jetzt senden", callback_data="now_" + str(msg["id"])),
                InlineKeyboardButton("Loeschen", callback_data="del_" + str(msg["id"])),
            ]])
        )

@owner_cb
async def handle_actions(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_", 1)
    action = parts[0]
    mid = int(parts[1])

    data = load_data()
    msg = next((m for m in data["messages"] if m["id"] == mid), None)
    if not msg:
        await q.answer("Nicht gefunden!", show_alert=True)
        return

    if action == "tog":
        msg["active"] = not msg.get("active", True)
        save_data(data)
        rebuild_schedule()
        status = "Aktiviert" if msg["active"] else "Pausiert"
        await q.answer(status)
        await q.edit_message_reply_markup(InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Pausieren" if msg["active"] else "Aktivieren",
                callback_data="tog_" + str(mid)
            ),
            InlineKeyboardButton("Jetzt senden", callback_data="now_" + str(mid)),
            InlineKeyboardButton("Loeschen", callback_data="del_" + str(mid)),
        ]]))

    elif action == "now":
        threading.Thread(target=do_send, args=(msg,), daemon=True).start()
        await q.answer("Wird gesendet!", show_alert=True)

    elif action == "del":
        data["messages"] = [m for m in data["messages"] if m["id"] != mid]
        save_data(data)
        rebuild_schedule()
        await q.edit_message_text("'" + msg["name"] + "' geloescht.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _bot_app

    try:
        ok = tg_run(_init_client())
        if ok:
            rebuild_schedule()
            logger.info("Session wiederhergestellt")
    except Exception as e:
        logger.error("Session: " + str(e))

    app = Application.builder().token(BOT_TOKEN).build()
    _bot_app = app

    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login)],
        states={
            ASK_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_2fa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            ASK_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_text)],
            ASK_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_time)],
            ASK_DAYS:  [CallbackQueryHandler(handle_days, pattern="^(day_|days_)")],
            ASK_CHATS: [CallbackQueryHandler(handle_chats, pattern="^(chat_|page_|chats_)")],
            CONFIRM:   [CallbackQueryHandler(handle_confirm, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(login_conv)
    app.add_handler(add_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("chats", cmd_chats))
    app.add_handler(CallbackQueryHandler(handle_actions, pattern="^(tog_|now_|del_)"))

    logger.info("Bot gestartet!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
