"""
bale_client.py - کلاینت حداقلی API بات بله (فقط urllib؛ بدون وابستگی خارجی)
⚠ هنوز با API واقعی بله آزمایش نشده است (فرض: سازگار با Telegram Bot API در https://tapi.bale.ai/bot<TOKEN>/<method>).
"""
import json
import urllib.request

import config


def _call(method, payload, token=None, base=None, timeout=10):
    token = token or config.BALE_TOKEN
    base = (base or config.BALE_API_BASE).rstrip("/")
    if not token:
        return None
    req = urllib.request.Request(
        f"{base}/bot{token}/{method}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send_message(chat_id, text, token=None, base=None):
    """ارسال پیام؛ اگر توکن تنظیم نشده باشد None برمی‌گرداند (بدون خطا)"""
    try:
        return _call("sendMessage", {"chat_id": chat_id, "text": text}, token, base)
    except Exception as exc:  # شبکه/فیلتر نباید سرور را از کار بیندازد
        print("bale send_message failed:", exc)
        return None


def set_webhook(url, token=None, base=None):
    return _call("setWebhook", {"url": url}, token, base)
