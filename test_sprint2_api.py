import json
import threading
import urllib.error
import urllib.request

import pytest

import config
import server


@pytest.fixture
def api(tmp_path):
    config.WEBHOOK_SECRET = ""
    srv = server.make_server("127.0.0.1", 0, str(tmp_path / "api.db"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, method="GET", body=None, token=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers["Content-Type"].startswith("application/json") else raw.decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    yield call
    srv.shutdown()


def signup(api, name="sara_m"):
    s, j = api("/api/register", "POST", {"username": name, "password": "secret1", "profile": "athlete"})
    assert s == 201
    return j["token"]


def test_health_index_drugs(api):
    assert api("/api/health")[0] == 200
    s, html = api("/")
    assert s == 200 and "دارویار" in html and "__DRUGS_JSON__" not in html and "متفورمین" in html
    s, j = api("/api/drugs")
    assert len(j["drugs"]) >= 30 and len(j["groups"]) == 3


def test_register_login_errors(api):
    signup(api)
    assert api("/api/register", "POST", {"username": "sara_m", "password": "secret1"})[0] == 409
    assert api("/api/register", "POST", {"username": "x", "password": "secret1"})[0] == 400
    assert api("/api/login", "POST", {"username": "sara_m", "password": "bad"})[0] == 401
    s, j = api("/api/login", "POST", {"username": "sara_m", "password": "secret1"})
    assert s == 200 and j["user"]["profile"] == "athlete"


def test_auth_required(api):
    assert api("/api/sync", "POST", {})[0] == 401
    assert api("/api/meds")[0] == 401
    assert api("/api/logs", token="bad")[0] == 401


def test_sync_roundtrip(api):
    tok = signup(api)
    med = {"client_id": "m1", "name": "کراتین مونوهیدرات", "drug_category": "مکمل ورزشی (قدرت)", "dose": "۵ گرم",
           "times_csv": "17:00", "meal_relation": "بلافاصله بعد از ورزش (Post-Workout)", "group": "sport", "updated_at": 10}
    log = {"client_id": "l1", "med_name": med["name"], "drug_category": med["drug_category"], "dose": "۵ گرم",
           "scheduled_time": "17:00", "status": "✅ مصرف شد (به‌موقع)", "persian_date": "1405/08/19", "weekday_name": "سه‌شنبه", "actual_time": "17:02"}
    s, j = api("/api/sync", "POST", {"meds": [med], "logs": [log]}, tok)
    assert s == 200 and j["meds"][0]["meal_relation"].startswith("بلافاصله") and j["adherence"] == 100.0
    s, j = api("/api/logs", token=tok)
    assert len(j["logs"]) == 1 and j["adherence_by_category"]["مکمل ورزشی (قدرت)"]["percent"] == 100.0
    # کاربر دیگر داده‌ی این کاربر را نمی‌بیند
    tok2 = signup(api, "other_user")
    assert api("/api/meds", token=tok2)[1]["meds"] == []


def test_parse_endpoint(api):
    s, j = api("/api/parse", "POST", {"text": "متفورمین ۵۰۰ میلی‌گرم روزی ۲ بار\nکراتین ۵ گرم قبل از ورزش"})
    assert s == 200 and len(j["meds"]) == 2


def test_bale_webhook_full_flow(api):
    tok = signup(api)
    chat = {"message": {"chat": {"id": 777}, "text": "/start"}}
    assert "دارویار" in api("/api/bale_webhook", "POST", chat)[1]["reply"]
    # قبل از اتصال
    s, j = api("/api/bale_webhook", "POST", {"message": {"chat": {"id": 777}, "text": "متفورمین ۵۰۰ میلی‌گرم"}})
    assert "وصل" in j["reply"]
    code = api("/api/link_code", "POST", {}, tok)[1]["code"]
    s, j = api("/api/bale_webhook", "POST", {"message": {"chat": {"id": 777}, "text": f"/link {code}"}})
    assert "متصل" in j["reply"]
    s, j = api("/api/bale_webhook", "POST", {"chat_id": 777, "text": "متفورمین ۵۰۰ میلی‌گرم روزی ۲ بار ناشتا\nکراتین ۵ گرم بعد از ورزش"})  # فرمت ساده‌ی n8n
    assert j["added"] == 2
    meds = api("/api/meds", token=tok)[1]["meds"]
    assert {m["name"] for m in meds} == {"متفورمین", "کراتین مونوهیدرات"}
    assert any("ناشتا" in m["meal_relation"] for m in meds)
    s, j = api("/api/bale_webhook", "POST", {"message": {"chat": {"id": 777}, "text": "/delete_me"}})
    assert api("/api/meds", token=tok)[0] == 401  # حساب حذف شد


def test_webhook_secret(api):
    config.WEBHOOK_SECRET = "s3"
    try:
        body = {"chat_id": 1, "text": "/help"}
        assert api("/api/bale_webhook", "POST", body)[0] == 403
        assert api("/api/bale_webhook", "POST", body, headers={"X-Webhook-Secret": "s3"})[0] == 200
        assert api("/api/bale_webhook?secret=s3", "POST", body)[0] == 200
    finally:
        config.WEBHOOK_SECRET = ""


def test_delete_me(api):
    tok = signup(api)
    assert api("/api/delete_me", "POST", {}, tok)[0] == 200
    assert api("/api/me", token=tok)[0] == 401
