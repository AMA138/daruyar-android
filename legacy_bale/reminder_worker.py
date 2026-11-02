"""ارسال یادآورها. (مسئول: موتور زمان‌بندی و تست؛ همکار: بات و زیرساخت)"""
import time
import config
import db
import messages
from bale_client import inline_keyboard
from schedule import now_utc


def send_due(client, conn, now=None):
    """همه‌ی یادآورهای رسیده را یک‌بار می‌فرستد. تعداد ارسال‌شده‌ها را برمی‌گرداند."""
    now = now or now_utc()
    sent = 0
    for ev in db.due_events(conn, now):
        text = messages.REMINDER.format(name=ev["name"], dose=ev["dose_text"] or "").strip()
        kb = inline_keyboard([[
            (messages.BTN_TAKEN, f"taken:{ev['event_id']}"),
            (messages.BTN_SNOOZE, f"snooze:{ev['event_id']}"),
            (messages.BTN_SKIP, f"skip:{ev['event_id']}"),
        ]])
        client.send_message(ev["chat_id"], text, reply_markup=kb)
        db.mark_sent(conn, ev["event_id"], now)   # بعد از ارسال موفق؛ جلوگیری از ارسال تکراری
        sent += 1
    return sent


def run_forever(client, conn):
    while True:
        try:
            send_due(client, conn)
        except Exception as exc:  # TODO(هفته ۴): لاگ‌گیری مناسب و تلاش مجدد
            print("worker error:", exc)
        time.sleep(config.WORKER_INTERVAL)
