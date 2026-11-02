"""حلقه‌ی اصلی بات. (مسئول: بات و زیرساخت؛ گفت‌وگو: گفت‌وگو و تجربه‌ی کاربر)
اجرا:  python bot.py   (پس از تنظیم BALE_BOT_TOKEN)"""
import threading
import config
import db
import messages
from bale_client import BaleClient, inline_keyboard
from reminder_worker import run_forever
from schedule import now_utc


def handle_message(client, conn, msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    user = db.get_or_create_user(conn, chat_id)
    if text.startswith("/start"):
        kb = inline_keyboard([[(messages.BTN_CONSENT, "consent:yes")]])
        client.send_message(chat_id, messages.WELCOME, reply_markup=kb)
    elif text.startswith("/delete_me"):
        db.delete_user_data(conn, chat_id)
        client.send_message(chat_id, messages.DELETED)
    elif not user["consent_at"]:
        client.send_message(chat_id, messages.CONSENT_NEEDED)
    elif text.startswith("/meds"):
        meds = db.list_meds(conn, user["id"])
        body = "\n".join(f"• {m['name']} ({m['times_per_day']} بار در روز)" for m in meds) or messages.NO_MEDS
        client.send_message(chat_id, body)
    elif text.startswith("/add"):
        # TODO(هفته ۳، گفت‌وگو و تجربه‌ی کاربر): جریان گام‌به‌گام ثبت دارو (state machine)
        client.send_message(chat_id, "ثبت دارو به‌زودی اضافه می‌شود.")
    else:
        client.send_message(chat_id, messages.HELP)


def handle_callback(client, conn, cb):
    data = cb.get("data", "")
    chat_id = cb["message"]["chat"]["id"]
    now = now_utc()
    kind, _, arg = data.partition(":")
    if kind == "consent":
        db.give_consent(conn, chat_id)
        client.send_message(chat_id, messages.CONSENT_OK)
    elif kind == "taken":
        db.set_status(conn, int(arg), "taken", now)
        client.send_message(chat_id, messages.TAKEN_THANKS)
    elif kind == "skip":
        db.set_status(conn, int(arg), "skipped", now)
        client.send_message(chat_id, messages.SKIPPED)
    elif kind == "snooze":
        db.snooze(conn, int(arg), now, config.SNOOZE_MINUTES)
        client.send_message(chat_id, messages.SNOOZED.format(minutes=config.SNOOZE_MINUTES))
    client.answer_callback(cb["id"])


def main():
    client = BaleClient()
    conn = db.connect()
    threading.Thread(target=run_forever, args=(client, db.connect()), daemon=True).start()
    offset = None
    while True:
        for upd in client.get_updates(offset=offset):
            offset = upd["update_id"] + 1
            if "message" in upd:
                handle_message(client, conn, upd["message"])
            elif "callback_query" in upd:
                handle_callback(client, conn, upd["callback_query"])


if __name__ == "__main__":
    main()
