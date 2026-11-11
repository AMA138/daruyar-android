"""
server.py - سرور REST دارویار (فقط کتابخانه‌ی استاندارد؛ Windows / Linux / Pydroid 3)
  python server.py            # اجرا روی DARUYAR_HOST:DARUYAR_PORT
اندپوینت‌ها: /api/register /api/login /api/me /api/sync /api/meds /api/logs /api/parse
             /api/consent /api/profile /api/link_code /api/delete_me /api/bale_webhook /api/drugs /api/health
"""
import base64
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bale_client
import config
import db
import med_parser
import messages
import schedule

WEB_DIR = os.path.join(config.BASE_DIR, "web")
USERNAME_RE = re.compile(r"^[\w.@+\-]{3,32}$")
MAX_BODY = 1_000_000


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
    payload = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    return (html.replace("__DRUGS_JSON__", payload(drugs if drugs is not None else med_parser.DRUGS))
                .replace("__CONFIG_JSON__", payload(cfg if cfg is not None else client_config()))
                .replace("/*__FONT_CSS__*/", font_css))


# ------------------------------------------------------------------ بات بله / n8n
def handle_bale_update(update, db_path, send=None):
    """پردازش یک update شبیه تلگرام (یا {chat_id, text} ساده از n8n). خروجی: {ok, reply, added}"""
    msg = update.get("message") or update.get("edited_message") or {}
    text = (msg.get("text") or update.get("text") or "").strip()
    chat = (msg.get("chat") or {}).get("id") or update.get("chat_id")
    if not chat or not text:
        return {"ok": True, "reply": None, "added": 0}
    chat = str(chat)
    reply, added = None, 0
    cmd = text.split()[0].lower() if text.startswith("/") else ""
    if cmd in ("/start", "/help"):
        reply = messages.WELCOME if cmd == "/start" else messages.HELP
    elif cmd == "/link":
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
                import time
                import uuid
                now = int(time.time() * 1000)
                db.upsert_meds(user["id"], [dict(m, client_id="bale-" + uuid.uuid4().hex[:12], updated_at=now) for m in found], db_path)
                added = len(found)
                reply = messages.PARSED_ADDED.format(count=added, names="، ".join(m["name"] for m in found))
    if reply and send:
        send(chat, reply)
    return {"ok": True, "reply": reply, "added": added}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "Daruyar/2"

    def log_message(self, fmt, *args):
        if os.environ.get("DARUYAR_VERBOSE"):
            super().log_message(fmt, *args)

    # --- کمکی‌ها
    def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8"):
        body = raw if raw is not None else json.dumps(obj if obj is not None else {}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("big")
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except json.JSONDecodeError:
            raise ValueError("json")

    def _user(self):
        auth = self.headers.get("Authorization", "")
        return db.get_user_by_token(auth[7:] if auth.startswith("Bearer ") else "", self.server.db_path)

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
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self._json()
        except ValueError as exc:
            return self._send(400, {"error": f"درخواست نامعتبر ({exc})"})
        dbp = self.server.db_path
        try:
            if path == "/api/register":
                name = (data.get("username") or "").strip()
                if not USERNAME_RE.match(name) or len(data.get("password") or "") < 6:
                    return self._send(400, {"error": messages.AUTH_WEAK})
                try:
                    user = db.register_user(name, data["password"], data.get("profile", "general"), data.get("display_name", ""), dbp)
                except ValueError as exc:
                    return self._send(409 if str(exc) == "exists" else 400,
                                      {"error": messages.AUTH_EXISTS if str(exc) == "exists" else messages.AUTH_WEAK})
                db.set_user_consent(user["id"], dbp)
                return self._send(201, {"token": db.create_session(user["id"], dbp), "user": user})
            if path == "/api/login":
                user = db.verify_login(data.get("username"), data.get("password"), dbp)
                if not user:
                    return self._send(401, {"error": messages.AUTH_BAD})
                return self._send(200, {"token": db.create_session(user["id"], dbp), "user": user})
            if path == "/api/bale_webhook":
                secret = config.WEBHOOK_SECRET
                given = self.headers.get("X-Webhook-Secret") or urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("secret", [""])[0]
                if secret and given != secret:
                    return self._send(403, {"error": "forbidden"})
                send = bale_client.send_message if config.BALE_TOKEN else None
                return self._send(200, handle_bale_update(data, dbp, send))
            if path == "/api/parse":  # بدون ورود هم کار می‌کند؛ فقط متن را تحلیل می‌کند و چیزی ذخیره نمی‌کند
                return self._send(200, {"meds": med_parser.parse_prescription(str(data.get("text", ""))[:20000])})

            user = self._user()
            if not user:
                return self._send(401, {"error": messages.AUTH_BAD})
            if path == "/api/sync":
                db.upsert_meds(user["id"], data.get("meds"), dbp)
                db.insert_logs(user["id"], data.get("logs"), dbp)
                return self._send(200, self._state(user))
            if path == "/api/profile":
                fields = {k: data[k] for k in ("display_name", "profile", "wake_time", "lunch_time", "dinner_time") if k in data}
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
            self._send(500, {"error": str(exc)})

    def _state(self, user):
        dbp, uid = self.server.db_path, user["id"]
        return {
            "user": user, "meds": db.list_meds_full(uid, dbp), "logs": db.list_logs_full(uid, dbp),
            "adherence": db.calculate_adherence_percentage(dbp, uid),
            "adherence_by_category": db.adherence_by_category(dbp, uid),
            "server_time": schedule.utc_str(),
        }


def make_server(host=None, port=None, db_path=None):
    srv = ThreadingHTTPServer((host or config.HOST, config.PORT if port is None else port), Handler)
    srv.db_path = db_path or config.DB_PATH
    db.init_db(srv.db_path)
    return srv


if __name__ == "__main__":
    srv = make_server()
    print(f"دارویار روی http://{config.HOST}:{srv.server_address[1]} در حال اجراست (Ctrl+C برای توقف)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
