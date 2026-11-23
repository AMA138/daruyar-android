"""
server.py - سرور REST دارویار (فقط کتابخانه‌ی استاندارد؛ Windows / Linux / Pydroid 3)
  python server.py            # اجرا روی DARUYAR_HOST:DARUYAR_PORT (پیش‌فرض: فقط 127.0.0.1)
اندپوینت‌ها: /api/register /api/login /api/logout /api/me /api/sync /api/meds /api/logs /api/parse
             /api/consent /api/profile /api/link_code /api/delete_me /api/bale_webhook /api/drugs /api/health
امنیت: هدرهای امنیتی، CORS محدود، محدودیت نرخ (ورود/ثبت‌نام/پارس/لینک بله)، خطای عمومی (بدون نشت جزئیات داخلی)،
       وب‌هوک بسته‌ی پیش‌فرض (بدون WEBHOOK_SECRET رد می‌شود)، نشست‌های هش‌شده.
"""
import base64
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bale_client
import config
import db
import features2
import med_parser
import messages
import schedule

log = logging.getLogger("daruyar")

WEB_DIR = os.path.join(config.BASE_DIR, "web")
USERNAME_RE = re.compile(r"[\w.@+\-]{3,32}")
MAX_BODY = 1_000_000
MAX_PARSE_CHARS = 5000
MAX_BALE_TEXT = 5000
# (تعداد مجاز، پنجره به ثانیه) — برای تنظیم سریع در یک جا
LIMITS = {
    "login_ip_user": (5, 900),    # ورود ناموفق برای یک نام کاربری از یک IP
    "login_user": (20, 900),      # ورود ناموفق برای یک نام کاربری از هر IP (ضد حمله‌ی توزیع‌شده)
    "login_ip": (30, 900),        # ورود ناموفق از یک IP با هر نام کاربری
    "register_ip": (20, 3600),
    "parse_ip": (60, 60),
    "link_chat": (5, 600),        # تلاش /link برای هر چت بله
    "link_all": (60, 600),        # تلاش /link در کل
}
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
       "font-src data:; media-src data: blob:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'; object-src 'none'")


class RateLimiter:
    """محدودکننده‌ی نرخ در حافظه (پنجره‌ی لغزان، امن برای چند نخ). با ری‌استارت سرور صفر می‌شود."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()
        self._ops = 0

    def _live(self, key, window, now):
        hits = [t for t in self._hits.get(key, ()) if now - t < window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def _sweep(self, now):
        self._ops += 1
        if self._ops % 500 == 0:  # جلوگیری از رشد بی‌پایان حافظه
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                self._hits.pop(k, None)

    def blocked(self, key, limit, window):
        """آیا تعداد برخوردهای ثبت‌شده به سقف رسیده؟ (بدون ثبت برخورد جدید)"""
        now = time.time()
        with self._lock:
            self._sweep(now)
            return len(self._live(key, window, now)) >= limit

    def hit(self, key):
        with self._lock:
            self._hits.setdefault(key, []).append(time.time())

    def allow(self, key, limit, window):
        """ثبت یک برخورد؛ False اگر از سقف گذشته باشد"""
        now = time.time()
        with self._lock:
            self._sweep(now)
            hits = self._live(key, window, now)
            if len(hits) >= limit:
                return False
            self._hits.setdefault(key, []).append(now)
            return True

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


def client_config():
    return {"bot_username": config.BALE_BOT_USERNAME}


def render_index(drugs=None, cfg=None):
    """HTML برنامه با داروها و تنظیمات جاسازی‌شده (برای سرور و برای APK آفلاین)"""
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    font_css = ""
    font_path = os.path.join(WEB_DIR, "fonts", "Vazirmatn.woff2")
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        font_css = ("@font-face{font-family:'Vazirmatn';font-weight:100 900;"
                    f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    nf_js = ""
    nf_path = os.path.join(WEB_DIR, "features2.js")
    if os.path.exists(nf_path):
        with open(nf_path, encoding="utf-8") as f:
            nf_js = f.read().replace("</script", "<\\/script")
    payload = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    return (html.replace("/*__NF_JS__*/", nf_js).replace("__DRUGS_JSON__", payload(drugs if drugs is not None else med_parser.DRUGS))
                .replace("__CONFIG_JSON__", payload(cfg if cfg is not None else client_config()))
                .replace("/*__FONT_CSS__*/", font_css))


# ------------------------------------------------------------------ بات بله / n8n
def handle_bale_update(update, db_path, send=None, limiter=None):
    """پردازش یک update شبیه تلگرام (یا {chat_id, text} ساده از n8n). خروجی: {ok, reply, added}"""
    update = update if isinstance(update, dict) else {}
    msg = update.get("message") or update.get("edited_message") or {}
    msg = msg if isinstance(msg, dict) else {}
    text = msg.get("text") or update.get("text") or ""
    text = text.strip()[:MAX_BALE_TEXT] if isinstance(text, str) else ""
    chat_obj = msg.get("chat")
    chat = (chat_obj.get("id") if isinstance(chat_obj, dict) else None) or update.get("chat_id")
    if isinstance(chat, bool) or not isinstance(chat, (int, str)) or len(str(chat)) > 32:
        chat = None
    if not chat or not text:
        return {"ok": True, "reply": None, "added": 0}
    chat = str(chat)
    reply, added = None, 0
    cmd = text.split()[0].lower() if text.startswith("/") else ""
    if cmd in ("/start", "/help"):
        reply = messages.WELCOME if cmd == "/start" else messages.HELP
    elif cmd == "/link":
        if limiter is not None and not (limiter.allow(("link", chat), *LIMITS["link_chat"])
                                        and limiter.allow(("link", "*"), *LIMITS["link_all"])):
            reply = messages.RATE_LIMITED
        else:
            parts = text.split()
            user = db.link_bale(parts[1] if len(parts) > 1 else "", chat, db_path)
            reply = messages.LINK_OK if user else messages.LINK_FAIL
    else:
        user = db.find_user_by_chat(chat, db_path)
        if not user:
            reply = messages.NOT_LINKED
        elif cmd == "/delete_me":
            db.delete_user_data(user["id"], db_path)
            reply = messages.DELETED
        elif cmd == "/meds":
            meds = db.get_medications(db_path, user["id"])
            reply = "\n".join(f"💊 {m[1]} - {m[3]} - {m[4]} - {m[5]}" for m in meds) if meds else messages.NO_MEDS
        else:
            found = med_parser.parse_prescription(text)
            if not found:
                reply = messages.PARSE_EMPTY
            else:
                now = int(time.time() * 1000)
                db.upsert_meds(user["id"], [dict(m, client_id="bale-" + uuid.uuid4().hex[:12], updated_at=now) for m in found], db_path)
                added = len(found)
                reply = messages.PARSED_ADDED.format(count=added, names="، ".join(m["name"] for m in found))
    if reply and send:
        send(chat, reply)
    return {"ok": True, "reply": reply, "added": added}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "Daruyar"
    sys_version = ""
    timeout = 15  # ثانیه؛ اتصال‌های کند/نیمه‌باز (slowloris) رها می‌شوند

    def version_string(self):
        return "Daruyar"

    def log_message(self, fmt, *args):
        if os.environ.get("DARUYAR_VERBOSE"):
            # راز وب‌هوک در query نباید وارد لاگ شود
            args = tuple(re.sub(r"(secret=)[^&\s]+", r"\1***", a) if isinstance(a, str) else a for a in args)
            super().log_message(fmt, *args)

    # --- کمکی‌ها
    def _ip(self):
        if config.TRUST_PROXY:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd.strip():
                return fwd.split(",")[-1].strip()[:64]
        return self.client_address[0]

    def _cors_origin(self):
        """مبدأ مجاز یا None. «null» = WebView اپ اندروید (file://)؛ بقیه فقط از فهرست یا همان میزبان."""
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if origin == "null" or origin in config.CORS_ORIGINS:
            return origin
        host = self.headers.get("Host")
        if host and urllib.parse.urlparse(origin).netloc == host:
            return origin
        return None

    def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8", extra=None):
        body = raw if raw is not None else json.dumps(obj if obj is not None else {}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cache-Control", "no-store")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if config.BEHIND_HTTPS:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if raw != b"" or code != 204:
            self.wfile.write(body)

    def _limited(self):
        return 429, {"error": messages.RATE_LIMITED}

    def _fail(self, exc):
        """خطای پیش‌بینی‌نشده: جزئیات فقط در لاگ سرور؛ به کلاینت پیام عمومی"""
        log.error("unhandled error on %s %s", self.command, urllib.parse.urlparse(self.path).path, exc_info=exc)
        try:
            self._send(500, {"error": messages.SERVER_ERROR})
        except OSError:
            pass

    def _json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("json")
        if n < 0:
            raise ValueError("json")
        if n > MAX_BODY:
            raise ValueError("big")
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("json")
        if not isinstance(data, dict):
            raise ValueError("json")
        return data

    def _token(self):
        auth = self.headers.get("Authorization", "")
        return auth[7:].strip() if auth.startswith("Bearer ") else ""

    def _user(self):
        return db.get_user_by_token(self._token(), self.server.db_path)

    def do_OPTIONS(self):
        self._send(204, raw=b"")

    # --- مسیریابی
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._send(200, raw=render_index().encode("utf-8"), ctype="text/html; charset=utf-8")
            if path == "/api/health":
                return self._send(200, {"ok": True, "time": schedule.utc_str()})
            if path == "/api/drugs":
                return self._send(200, {"drugs": med_parser.DRUGS, "groups": med_parser.GROUPS, "meals": messages.MEAL_OPTIONS})
            if path in ("/api/me", "/api/meds", "/api/logs"):
                user = self._user()
                if not user:
                    return self._send(401, {"error": messages.AUTH_BAD})
                return self._send(200, self._state(user) if path != "/api/me" else {"user": user})
            res = features2.route("GET", path, None, self._user(), self.server.db_path, urllib.parse.urlparse(self.path).query)
            if res:
                return self._send(*res)
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._fail(exc)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self._json()
        except ValueError as exc:
            if str(exc) == "big":
                return self._send(413, {"error": messages.BAD_REQUEST})
            return self._send(400, {"error": messages.BAD_REQUEST})
        dbp, lim, ip = self.server.db_path, self.server.limiter, self._ip()
        try:
            if path == "/api/register":
                if not lim.allow(("register", ip), *LIMITS["register_ip"]):
                    return self._send(429, {"error": messages.RATE_LIMITED}, extra={"Retry-After": "600"})
                name, pwd = data.get("username"), data.get("password")
                if (not isinstance(name, str) or not isinstance(pwd, str) or not USERNAME_RE.fullmatch(name.strip())
                        or not (6 <= len(pwd) <= db.MAX_PASSWORD)):
                    return self._send(400, {"error": messages.AUTH_WEAK})
                profile = data.get("profile", "general")
                try:
                    user = db.register_user(name, pwd, profile if isinstance(profile, str) else "general", data.get("display_name", ""), dbp)
                except ValueError as exc:
                    return self._send(409 if str(exc) == "exists" else 400,
                                      {"error": messages.AUTH_EXISTS if str(exc) == "exists" else messages.AUTH_WEAK})
                db.set_user_consent(user["id"], dbp)
                return self._send(201, {"token": db.create_session(user["id"], dbp), "user": user})
            if path == "/api/login":
                uname, pwd = data.get("username"), data.get("password")
                ukey = (uname.strip().lower()[:64] if isinstance(uname, str) else "")
                k_iu, k_u, k_i = ("login", ip, ukey), ("login-user", ukey), ("login-ip", ip)
                if (lim.blocked(k_iu, *LIMITS["login_ip_user"]) or lim.blocked(k_u, *LIMITS["login_user"])
                        or lim.blocked(k_i, *LIMITS["login_ip"])):
                    return self._send(429, {"error": messages.RATE_LIMITED}, extra={"Retry-After": "300"})
                user = db.verify_login(uname, pwd, dbp)
                if not user:
                    for k in (k_iu, k_u, k_i):
                        lim.hit(k)
                    return self._send(401, {"error": messages.AUTH_BAD})
                lim.reset(k_iu)
                return self._send(200, {"token": db.create_session(user["id"], dbp), "user": user})
            if path == "/api/bale_webhook":
                secret = config.WEBHOOK_SECRET
                given = self.headers.get("X-Webhook-Secret") or urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("secret", [""])[0]
                if secret:
                    if not hmac.compare_digest(given.encode("utf-8"), secret.encode("utf-8")):
                        return self._send(403, {"error": "forbidden"})
                elif not config.ALLOW_OPEN_WEBHOOK:
                    # بسته‌ی پیش‌فرض: بدون راز، هر کسی می‌توانست با chat_id جعلی داروها را بخواند/حذف کند یا از بات هرزنامه بفرستد
                    return self._send(403, {"error": "forbidden"})
                send = bale_client.send_message if config.BALE_TOKEN else None
                return self._send(200, handle_bale_update(data, dbp, send, lim))
            if path == "/api/parse":  # بدون ورود هم کار می‌کند؛ فقط متن را تحلیل می‌کند و چیزی ذخیره نمی‌کند
                if not lim.allow(("parse", ip), *LIMITS["parse_ip"]):
                    return self._send(429, {"error": messages.RATE_LIMITED}, extra={"Retry-After": "60"})
                return self._send(200, {"meds": med_parser.parse_prescription(str(data.get("text", ""))[:MAX_PARSE_CHARS])})

            user = self._user()
            if not user:
                return self._send(401, {"error": messages.AUTH_BAD})
            if path == "/api/logout":
                db.revoke_session(self._token(), dbp)
                return self._send(200, {"ok": True})
            res = features2.route("POST", path, data, user, dbp)
            if res:
                return self._send(*res)
            if path == "/api/sync":
                if any(isinstance(data.get(k), list) and len(data[k]) > db.MAX_SYNC_ITEMS for k in ("meds", "logs", "files")):
                    return self._send(413, {"error": messages.BAD_REQUEST})
                db.upsert_files(user["id"], data.get("files"), dbp)   # قبل از داروها: حذف پرونده داروها را آزاد می‌کند
                db.upsert_meds(user["id"], data.get("meds"), dbp)
                db.insert_logs(user["id"], data.get("logs"), dbp)
                return self._send(200, self._state(user))
            if path == "/api/profile":
                fields = {k: data[k] for k in ("display_name", "profile", "wake_time", "lunch_time", "dinner_time", "allergies") if k in data}
                try:
                    updated = db.update_profile(user["id"], dbp, **fields)
                except ValueError as exc:
                    msg = {"time": messages.PROFILE_BAD_TIME, "profile": messages.PROFILE_BAD_TYPE}.get(str(exc), messages.AUTH_BAD)
                    return self._send(400, {"error": msg})
                return self._send(200, {"user": updated})
            if path == "/api/consent":
                db.set_user_consent(user["id"], dbp)
                return self._send(200, {"ok": True})
            if path == "/api/link_code":
                return self._send(200, {"code": db.set_link_code(user["id"], dbp), "bot_username": config.BALE_BOT_USERNAME})
            if path == "/api/delete_me":
                db.delete_user_data(user["id"], dbp)
                return self._send(200, {"ok": True, "message": messages.DELETED})
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._fail(exc)

    def _state(self, user):
        dbp, uid = self.server.db_path, user["id"]
        return {
            "user": user, "meds": db.list_meds_full(uid, dbp), "logs": db.list_logs_full(uid, dbp),
            "files": db.list_files(uid, dbp), "adherence_by_file": db.adherence_by_file(dbp, uid),
            "adherence": db.calculate_adherence_percentage(dbp, uid),
            "adherence_by_category": db.adherence_by_category(dbp, uid),
            "server_time": schedule.utc_str(),
        }


def make_server(host=None, port=None, db_path=None):
    srv = ThreadingHTTPServer((host or config.HOST, config.PORT if port is None else port), Handler)
    srv.db_path = db_path or config.DB_PATH
    srv.limiter = RateLimiter()
    db.init_db(srv.db_path)
    return srv


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    srv = make_server()
    print(f"دارویار روی http://{config.HOST}:{srv.server_address[1]} در حال اجراست (Ctrl+C برای توقف)")
    if config.HOST not in ("127.0.0.1", "localhost", "::1"):
        print("⚠ سرور روی شبکه باز است و ارتباط HTTP رمزنگاری نمی‌شود؛ فقط در شبکه‌ی مورد اعتماد یا پشت HTTPS استفاده کنید.")
    if config.WEBHOOK_SECRET == "" and config.BALE_TOKEN:
        print("⚠ WEBHOOK_SECRET خالی است؛ وب‌هوک بله/n8n رد می‌شود تا راز تنظیم شود.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
