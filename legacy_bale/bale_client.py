"""کلاینت ساده‌ی API بله با requests. (مسئول: بات و زیرساخت)
فرض: API بله با Telegram Bot API سازگار است؛ در هفته‌ی ۲ باید با مستندات رسمی بله تأیید شود."""
import requests
import config


class BaleError(Exception):
    pass


def inline_keyboard(rows):
    """rows = [[("متن دکمه", "callback_data"), ...], ...]"""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


class BaleClient:
    def __init__(self, token=None, base_url=None, session=None):
        self.token = token or config.TOKEN
        self.base = (base_url or config.BASE_URL).rstrip("/")
        self.http = session or requests.Session()

    def _call(self, method, **params):
        if not self.token:
            raise BaleError("توکن بات تنظیم نشده است (BALE_BOT_TOKEN).")
        url = f"{self.base}/bot{self.token}/{method}"
        r = self.http.post(url, json=params, timeout=config.POLL_TIMEOUT + 10)
        data = r.json()
        if not data.get("ok"):
            raise BaleError(f"{method} failed: {data}")
        return data["result"]

    def get_updates(self, offset=None, timeout=None):
        return self._call("getUpdates", offset=offset, timeout=timeout or config.POLL_TIMEOUT)

    def send_message(self, chat_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self._call("sendMessage", **params)

    def answer_callback(self, callback_id, text=None):
        return self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)
