"""tests/test_security.py - آزمون‌های رگرسیون امنیتی (هر یافته‌ی ممیزی یک تست دارد). فقط کتابخانه‌ی استاندارد + node (مثل بقیه‌ی تست‌های JS)."""
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

import config
import db
import med_parser
import messages
import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "secret12"


@pytest.fixture
def env(tmp_path):
    saved = (config.WEBHOOK_SECRET, config.ALLOW_OPEN_WEBHOOK)
    config.WEBHOOK_SECRET, config.ALLOW_OPEN_WEBHOOK = "", False
    dbp = str(tmp_path / "sec.db")
    srv = server.make_server("127.0.0.1", 0, dbp)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = "127.0.0.1", srv.server_address[1]

    def raw(path, method="GET", body=None, token=None, headers=None):
        """(status, headers(dict, lower-case), body-text)"""
        h = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode() if not isinstance(body, (bytes, str)) else (body.encode() if isinstance(body, str) else body)
            h.setdefault("Content-Type", "application/json")
        if token:
            h["Authorization"] = "Bearer " + token
        c = http.client.HTTPConnection(host, port, timeout=10)
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        text = r.read().decode("utf-8", "replace")
        hd = {k.lower(): v for k, v in r.getheaders()}
        c.close()
        return r.status, hd, text

    def call(path, method="GET", body=None, token=None, headers=None):
        s, _, t = raw(path, method, body, token, headers)
        try:
            return s, json.loads(t)
        except ValueError:
            return s, t

    class E:
        pass
    e = E()
    e.raw, e.call, e.dbp, e.srv, e.host, e.port = raw, call, dbp, srv, host, port
    yield e
    srv.shutdown()
    config.WEBHOOK_SECRET, config.ALLOW_OPEN_WEBHOOK = saved


def signup(env, name="sara_m", pw=PW):
    s, j = env.call("/api/register", "POST", {"username": name, "password": pw})
    assert s == 201, (s, j)
    return j["token"]


# ------------------------------------------------------------ هدرها، CORS، خطاها
def test_security_headers_on_api_and_html(env):
    for path in ("/api/health", "/"):
        s, h, _ = env.raw(path)
        assert s == 200
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "no-store"
        assert h["server"] == "Daruyar" and "python" not in h["server"].lower()
    _, h, _ = env.raw("/")
    assert "frame-ancestors 'none'" in h["content-security-policy"] and "object-src 'none'" in h["content-security-policy"]
    assert "strict-transport-security" not in h  # بدون HTTPS واقعی HSTS نمی‌فرستیم


def test_cors_is_not_wildcard(env):
    _, h, _ = env.raw("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in h
    _, h, _ = env.raw("/api/health", headers={"Origin": "null"})  # WebView اپ (file://)
    assert h["access-control-allow-origin"] == "null"
    _, h, _ = env.raw("/api/health", headers={"Origin": f"http://{env.host}:{env.port}"})
    assert h["access-control-allow-origin"] == f"http://{env.host}:{env.port}"
    s, h, _ = env.raw("/api/sync", "OPTIONS", headers={"Origin": "https://evil.example"})
    assert s == 204 and "access-control-allow-origin" not in h
    _, h, _ = env.raw("/api/health")
    assert "access-control-allow-origin" not in h and "*" not in h.values()


def test_internal_errors_are_not_leaked(env):
    tok = signup(env)
    orig = server.db.list_meds_full
    def boom(*a, **k):
        raise RuntimeError("SECRET-INTERNAL /etc/passwd stack detail")
    server.db.list_meds_full = boom
    try:
        s, _, text = env.raw("/api/meds", token=tok)
    finally:
        server.db.list_meds_full = orig
    assert s == 500 and "SECRET-INTERNAL" not in text and "RuntimeError" not in text
    assert json.loads(text)["error"] == messages.SERVER_ERROR


def test_malformed_bodies_are_rejected_cleanly(env):
    assert env.raw("/api/login", "POST", "[1,2,3]")[0] == 400           # JSON غیر دیکشنری
    assert env.raw("/api/login", "POST", "{not json")[0] == 400
    assert env.raw("/api/login", "POST", b"\xff\xfe\x00")[0] == 400
    assert env.call("/api/login", "POST", {"username": ["x"], "password": {"a": 1}})[0] == 401   # نوع اشتباه، نه ۵۰۰
    assert env.call("/api/register", "POST", {"username": 123, "password": 456})[0] == 400
    for cl in ("-5", "abc"):
        c = http.client.HTTPConnection(env.host, env.port, timeout=5)
        c.putrequest("POST", "/api/login"); c.putheader("Content-Length", cl); c.endheaders()
        assert c.getresponse().status == 400
        c.close()
    c = http.client.HTTPConnection(env.host, env.port, timeout=5)
    c.putrequest("POST", "/api/login"); c.putheader("Content-Length", "2000000"); c.endheaders()
    assert c.getresponse().status == 413
    c.close()


# ------------------------------------------------------------ احراز هویت
def test_login_bruteforce_is_throttled(env):
    signup(env, "victim_u")
    for _ in range(5):
        assert env.call("/api/login", "POST", {"username": "victim_u", "password": "wrong-pw"})[0] == 401
    s, j = env.call("/api/login", "POST", {"username": "victim_u", "password": PW})   # رمز درست هم بعد از قفل رد می‌شود
    assert s == 429 and j["error"] == messages.RATE_LIMITED
    assert env.call("/api/login", "POST", {"username": "someone_else", "password": "x" * 8})[0] == 401  # حساب دیگر قفل نیست


def test_successful_login_resets_counter(env):
    signup(env, "victim_u")
    for _ in range(4):
        env.call("/api/login", "POST", {"username": "victim_u", "password": "wrong-pw"})
    assert env.call("/api/login", "POST", {"username": "victim_u", "password": PW})[0] == 200
    for _ in range(4):
        assert env.call("/api/login", "POST", {"username": "victim_u", "password": "wrong-pw"})[0] == 401


def test_register_is_rate_limited(env):
    old = server.LIMITS["register_ip"]
    server.LIMITS["register_ip"] = (3, 3600)
    try:
        codes = [env.call("/api/register", "POST", {"username": f"user_{i}", "password": PW})[0] for i in range(5)]
    finally:
        server.LIMITS["register_ip"] = old
    assert codes == [201, 201, 201, 429, 429]


def test_password_length_limits(env):
    assert env.call("/api/register", "POST", {"username": "longpw_u", "password": "a" * 129})[0] == 400
    assert env.call("/api/register", "POST", {"username": "longpw_u", "password": "a" * 128})[0] == 201
    t = time.time()
    assert env.call("/api/login", "POST", {"username": "longpw_u", "password": "a" * 100000})[0] == 401
    assert time.time() - t < 2


def test_password_hash_rounds_and_silent_upgrade(env):
    assert db.PBKDF2_ROUNDS >= 600_000
    signup(env, "old_user")
    conn = sqlite3.connect(env.dbp)
    assert conn.execute("SELECT pw_rounds FROM users WHERE username='old_user'").fetchone()[0] == db.PBKDF2_ROUNDS
    h, salt = db.hash_password(PW, rounds=db.LEGACY_PBKDF2_ROUNDS)   # شبیه‌سازی حساب قدیمی
    conn.execute("UPDATE users SET password_hash=?, salt=?, pw_rounds=? WHERE username='old_user'", (h, salt, db.LEGACY_PBKDF2_ROUNDS))
    conn.commit()
    assert db.verify_login("old_user", PW, env.dbp)
    assert conn.execute("SELECT pw_rounds FROM users WHERE username='old_user'").fetchone()[0] == db.PBKDF2_ROUNDS
    assert db.verify_login("old_user", PW, env.dbp) and not db.verify_login("old_user", "bad-pass", env.dbp)
    conn.close()


def test_sessions_are_stored_hashed_and_logout_revokes(env):
    tok = signup(env)
    conn = sqlite3.connect(env.dbp)
    stored = [r[0] for r in conn.execute("SELECT token FROM sessions")]
    conn.close()
    assert tok not in stored and hashlib.sha256(tok.encode()).hexdigest() in stored
    assert env.call("/api/me", token=tok)[0] == 200
    assert env.call("/api/logout", "POST", {}, tok)[0] == 200
    assert env.call("/api/me", token=tok)[0] == 401          # نشست در سرور واقعاً ابطال شد
    assert env.call("/api/logout", "POST", {})[0] == 401


def test_legacy_plaintext_sessions_are_migrated(tmp_path):
    p = str(tmp_path / "legacy.db")
    u = db.register_user("legacy_u", PW, db_path=p)
    legacy = "a1" * 24                                        # توکن خام قدیمی: ۴۸ نویسه
    conn = sqlite3.connect(p)
    conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)", (legacy, u["id"], int(time.time())))
    conn.commit(); conn.close()
    db._READY.discard(p)
    db.init_db(p)
    conn = sqlite3.connect(p)
    assert legacy not in [r[0] for r in conn.execute("SELECT token FROM sessions")]
    conn.close()
    assert db.get_user_by_token(legacy, p)["username"] == "legacy_u"


def test_expired_sessions_are_purged(tmp_path):
    p = str(tmp_path / "exp.db")
    u = db.register_user("exp_user", PW, db_path=p)
    old = db.create_session(u["id"], p)
    conn = sqlite3.connect(p)
    conn.execute("UPDATE sessions SET created_at=?", (int(time.time()) - db.SESSION_TTL - 10,))
    conn.commit(); conn.close()
    assert db.get_user_by_token(old, p) is None
    db.create_session(u["id"], p)
    conn = sqlite3.connect(p)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    conn.close()


def test_db_file_is_owner_only(env):
    if os.name != "posix":
        return
    assert os.stat(env.dbp).st_mode & 0o077 == 0


# ------------------------------------------------------------ وب‌هوک و اتصال بله
def test_webhook_is_closed_without_secret(env):
    body = {"chat_id": 99, "text": "/meds"}
    assert env.call("/api/bale_webhook", "POST", body)[0] == 403
    config.WEBHOOK_SECRET = "s3cret"
    assert env.call("/api/bale_webhook", "POST", body)[0] == 403
    assert env.call("/api/bale_webhook", "POST", body, headers={"X-Webhook-Secret": "wrong"})[0] == 403
    assert env.call("/api/bale_webhook", "POST", body, headers={"X-Webhook-Secret": "s3cret"})[0] == 200
    assert env.call("/api/bale_webhook", "POST", body, headers={"X-Webhook-Secret": "s\u00e9cret"})[0] == 403  # غیر ASCII → ۴۰۳ نه ۵۰۰
    config.WEBHOOK_SECRET = ""
    config.ALLOW_OPEN_WEBHOOK = True                       # فقط با گزینه‌ی صریح
    assert env.call("/api/bale_webhook", "POST", body)[0] == 200


def test_webhook_cannot_read_or_delete_unlinked_users(env):
    tok = signup(env)
    config.ALLOW_OPEN_WEBHOOK = True
    s, j = env.call("/api/bale_webhook", "POST", {"chat_id": 12345, "text": "/delete_me"})
    assert s == 200 and j["reply"] == messages.NOT_LINKED
    assert env.call("/api/me", token=tok)[0] == 200


def test_webhook_tolerates_weird_payloads(env):
    config.ALLOW_OPEN_WEBHOOK = True
    for body in ({"message": []}, {"message": {"chat": 5, "text": 7}}, {"chat_id": {"a": 1}, "text": "x"},
                 {"chat_id": True, "text": "/start"}, {"chat_id": "9" * 100, "text": "/start"}):
        assert env.call("/api/bale_webhook", "POST", body)[0] == 200


def test_link_code_expires_and_chat_belongs_to_one_account(env):
    a, b = signup(env, "user_a"), signup(env, "user_b")
    config.ALLOW_OPEN_WEBHOOK = True
    wh = lambda chat, text: env.call("/api/bale_webhook", "POST", {"chat_id": chat, "text": text})[1]["reply"]
    code = env.call("/api/link_code", "POST", {}, a)[1]["code"]
    conn = sqlite3.connect(env.dbp)
    conn.execute("UPDATE users SET link_code_at=? WHERE link_code=?", (int(time.time()) - db.LINK_CODE_TTL - 5, code))
    conn.commit()
    assert wh(777, f"/link {code}") == messages.LINK_FAIL         # کد منقضی
    code = env.call("/api/link_code", "POST", {}, a)[1]["code"]
    assert wh(777, f"/link {code}") == messages.LINK_OK
    assert wh(777, f"/link {code}") == messages.LINK_FAIL         # یک‌بارمصرف
    code_b = env.call("/api/link_code", "POST", {}, b)[1]["code"]
    assert wh(777, f"/link {code_b}") == messages.LINK_OK          # همان چت به حساب دیگر
    assert conn.execute("SELECT COUNT(*) FROM users WHERE bale_chat_id='777'").fetchone()[0] == 1
    conn.close()


def test_link_code_guessing_is_throttled(tmp_path):
    p = str(tmp_path / "l.db")
    lim = server.RateLimiter()
    replies = [server.handle_bale_update({"chat_id": 5, "text": "/link AAAAAA"}, p, None, lim)["reply"] for _ in range(7)]
    assert replies[:5] == [messages.LINK_FAIL] * 5 and replies[5:] == [messages.RATE_LIMITED] * 2


# ------------------------------------------------------------ تزریق، IDOR، اعتبارسنجی
def test_sql_injection_payloads_are_inert(env):
    signup(env, "real_user")
    assert env.call("/api/login", "POST", {"username": "real_user' OR '1'='1", "password": "x' OR '1'='1"})[0] == 401
    assert env.call("/api/login", "POST", {"username": "' OR 1=1--", "password": PW})[0] == 401
    assert env.call("/api/register", "POST", {"username": "a'; DROP TABLE users;--", "password": PW})[0] == 400
    assert env.call("/api/me", token="' OR 1=1--")[0] == 401
    tok = signup(env, "inj_user")
    nasty = "x'); DROP TABLE users;--"
    s, j = env.call("/api/sync", "POST", {"meds": [{"client_id": "m1", "name": nasty, "times_csv": "08:00", "updated_at": 1}]}, tok)
    assert s == 200 and j["meds"][0]["name"] == nasty
    assert env.call("/api/login", "POST", {"username": "real_user", "password": PW})[0] == 200   # جدول users هنوز هست


def test_users_cannot_touch_each_others_data(env):
    a, b = signup(env, "alice_a"), signup(env, "bob_bb")
    med = {"client_id": "m1", "name": "A-secret-drug", "times_csv": "08:00", "updated_at": 5}
    env.call("/api/sync", "POST", {"meds": [med]}, a)
    env.call("/api/stock", "POST", {"med_client_id": "m1", "quantity": 10}, a)
    # باب همان client_id را می‌فرستد: ردیف جدا برای خودش، نه بازنویسی ردیف آلیس
    env.call("/api/sync", "POST", {"meds": [dict(med, name="B-drug", updated_at=99)]}, b)
    assert env.call("/api/meds", token=a)[1]["meds"][0]["name"] == "A-secret-drug"
    assert [m["name"] for m in env.call("/api/meds", token=b)[1]["meds"]] == ["B-drug"]
    assert env.call("/api/stock/consume", "POST", {"med_client_id": "m1"}, b)[0] == 404
    assert env.call("/api/stock", token=a)[1]["stock"][0]["quantity"] == 10


def test_client_ids_are_whitelisted(env):
    tok = signup(env)
    evil = "x');window.__pwned=1;//"
    s, j = env.call("/api/sync", "POST", {
        "files": [{"client_id": evil, "title": "bad", "updated_at": 1}, {"client_id": "ok-1.a_b:c", "title": "good", "updated_at": 1}],
        "meds": [{"client_id": evil, "name": "bad", "updated_at": 1}, {"client_id": "m1", "name": "ok", "file_id": evil, "updated_at": 1}],
        "logs": [{"client_id": evil, "med_name": "bad"}]}, tok)
    assert s == 200
    assert [f["client_id"] for f in j["files"]] == ["ok-1.a_b:c"]
    assert [m["client_id"] for m in j["meds"]] == ["m1"] and j["meds"][0]["file_id"] == "" and j["logs"] == []
    assert env.call("/api/stock", "POST", {"med_client_id": evil, "quantity": 1}, tok)[0] == 400


def test_garbage_numbers_never_cause_500(env):
    tok = signup(env)
    meds = [{"client_id": "m1", "name": "x", "duration_days": "abc", "updated_at": 10 ** 30, "interval_days": [], "review_after_days": {}},
            "not-a-dict", 7, None, {"client_id": "m2", "name": "y", "duration_days": 10 ** 40}]
    s, j = env.call("/api/sync", "POST", {"meds": meds, "logs": "oops", "files": {"a": 1}}, tok)
    assert s == 200 and len(j["meds"]) == 2
    assert env.call("/api/sync2", "POST", {"stock": [{"med_client_id": "m1", "quantity": "1", "updated_at": "zzz"}],
                                           "water_logs": [{"client_id": "w1", "amount_ml": 200, "updated_at": 10 ** 30}]}, tok)[0] in (200, 400)


def test_sync_list_size_is_capped(env):
    tok = signup(env)
    big = [{"client_id": f"m{i}", "name": "x"} for i in range(db.MAX_SYNC_ITEMS + 1)]
    assert env.call("/api/sync", "POST", {"meds": big}, tok)[0] == 413


def test_no_admin_upload_or_static_file_routes(env):
    tok = signup(env)
    for path in ("/admin", "/api/admin", "/api/admin/users", "/api/upload", "/upload", "/server.py", "/db.py", "/.env",
                 "/../server.py", "/web/index.html", "/daruyar.db", "/%2e%2e/server.py"):
        assert env.raw(path)[0] == 404, path
        assert env.raw(path, "POST", {}, tok)[0] in (404, 401), path


def test_stored_script_payload_is_only_ever_json_data(env):
    tok = signup(env)
    xss = "<script>alert(1)</script>"
    env.call("/api/sync", "POST", {"meds": [{"client_id": "m1", "name": xss, "times_csv": "08:00", "updated_at": 1}]}, tok)
    s, h, text = env.raw("/api/meds", token=tok)
    assert h["content-type"].startswith("application/json") and h["x-content-type-options"] == "nosniff"
    assert json.loads(text)["meds"][0]["name"] == xss
    s, h, page = env.raw("/")
    assert xss not in page                                  # صفحه‌ی HTML داده‌ی کاربر را جاسازی نمی‌کند


# ------------------------------------------------------------ DoS
def test_parser_is_not_vulnerable_to_regex_dos(env):
    for payload in ("۵" * 20000, "5" * 20000, "5 " * 10000, "متفورمین" + " " * 19000 + "x"):
        t = time.time()
        med_parser.parse_prescription(payload)
        assert time.time() - t < 1.0
    t = time.time()
    assert env.call("/api/parse", "POST", {"text": "5" * 20000})[0] == 200
    assert time.time() - t < 1.0
    old = server.LIMITS["parse_ip"]
    server.LIMITS["parse_ip"] = (2, 60)
    try:
        codes = [env.call("/api/parse", "POST", {"text": "متفورمین"})[0] for _ in range(4)]
    finally:
        server.LIMITS["parse_ip"] = old
    assert codes[-1] == 429
    assert len(med_parser.parse_prescription("متفورمین ۵۰۰ میلی‌گرم\n" * 900)) <= med_parser.MAX_LINES


# ------------------------------------------------------------ فرانت‌اند (روی کد واقعی index.html با node)
def _node(script, payload):
    if not shutil.which("node"):
        pytest.skip("Node.js نصب نیست؛ این آزمون فرانت‌اند اجرا نشد (از nodejs.org نسخه‌ی LTS را نصب کنید و ترمینال را دوباره باز کنید)")
    r = subprocess.run(["node", "-e", script], input=json.dumps(payload), capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_jsq_makes_inline_handlers_injection_proof():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    esc_line = re.search(r"^const esc = .*$", html, re.M).group(0)
    jsq_line = re.search(r"^const jsq = .*$", html, re.M).group(0)
    script = esc_line + "\n" + jsq_line + r"""
const payloads = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const decode = (s) => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const out = payloads.map((p) => {
  let got = null, side = 0;
  const attr = 'f(' + jsq(p) + ')';                      // همان چیزی که داخل onclick="..." نوشته می‌شود
  const browserSees = decode(attr);                       // مرورگر قبل از اجرای JS موجودیت‌ها را برمی‌گرداند
  new Function('f', 'sideEffect', browserSees)((v) => { got = v; }, () => { side++; });
  return {ok: got === p && side === 0 && !/[<>]/.test(attr) && attr.indexOf('"') === -1};
});
console.log(JSON.stringify(out));"""
    payloads = ["x');window.__p=1;//", '"); sideEffect(); //', "');sideEffect();('", "\\", "\\');sideEffect();//", "</script><img onerror=sideEffect()>",
                "a\nb", "&amp;&#39;&quot;", "پرونده‌ی ۱", "'", '"', ""]
    res = _node(script, payloads)
    assert all(r["ok"] for r in res), [p for p, r in zip(payloads, res) if not r["ok"]]
    for name in ("features2.js", "dy-features.js"):
        src = open(os.path.join(ROOT, "web", name), encoding="utf-8").read()
        assert not re.search(r"\\\\'' \+ (D\.)?esc\(", src), name + " هنوز الگوی ناامن onclick دارد"
    assert not re.search(r"on\w+=\"[^\"]*'\$\{esc\(", html)


def test_server_url_rules_block_cleartext_on_public_hosts():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    fn = re.search(r"function safeServerUrl\(u\) \{.*?\n\}\n", html, re.S).group(0)
    cases = {"": "", "https://daruyar.example.ir": "https://daruyar.example.ir", "https://daruyar.example.ir/": "https://daruyar.example.ir",
             "http://192.168.1.20:8765": "http://192.168.1.20:8765", "http://10.0.0.5": "http://10.0.0.5", "http://172.16.0.1": "http://172.16.0.1",
             "http://localhost:8765": "http://localhost:8765", "http://127.0.0.1:8765": "http://127.0.0.1:8765",
             "http://evil.example": None, "http://8.8.8.8:8765": None, "http://172.32.0.1": None, "http://192.168.1.2.evil.com": None,
             "javascript:alert(1)": None, "ftp://192.168.1.2": None, "http://user:pw@192.168.1.2": None, "https://x.ir/path": None, "not a url": None}
    script = fn + "\nconst cases = JSON.parse(require('fs').readFileSync(0,'utf8'));\nconsole.log(JSON.stringify(Object.keys(cases).map(k => safeServerUrl(k))));"
    res = _node(script, cases)
    assert res == list(cases.values()), dict(zip(cases, res))


# ------------------------------------------------------------ پیکربندی و مخزن
def test_default_bind_is_loopback_only():
    env = {k: v for k, v in os.environ.items() if not k.startswith("DARUYAR_")}
    out = subprocess.run([sys.executable, "-c", "import config;print(config.HOST, config.ALLOW_OPEN_WEBHOOK, config.BEHIND_HTTPS)"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=30).stdout.split()
    assert out == ["127.0.0.1", "False", "False"]


def test_repo_has_no_hardcoded_secrets_and_ignores_them():
    wf = open(os.path.join(ROOT, ".github", "workflows", "build_apk.yml"), encoding="utf-8").read()
    assert "daruyar123" not in wf and "permissions:" in wf
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().split()
    for pat in (".env", "*.db", "*.jks", "*.keystore", "*.pem"):
        assert pat in gi
    token_like = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}")
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__", "node_modules")]
        for f in fn:
            if f.endswith((".png", ".pyc", ".csv", ".jpg")):
                continue
            try:
                text = open(os.path.join(dp, f), encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            assert not token_like.search(text), os.path.join(dp, f)
    env_example = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert re.search(r"^BALE_BOT_TOKEN=$", env_example, re.M) and re.search(r"^WEBHOOK_SECRET=$", env_example, re.M)
