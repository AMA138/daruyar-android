import json
import threading
import urllib.error
import urllib.request

import pytest

import config
import db
import messages
import server


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "p.db")


@pytest.fixture
def api(tmp_path):
    config.WEBHOOK_SECRET = ""
    srv = server.make_server("127.0.0.1", 0, str(tmp_path / "api.db"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(p, method="GET", body=None, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + p, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    yield call
    srv.shutdown()


def test_normalize_hhmm():
    assert db.normalize_hhmm("۱۳:۰۰") == "13:00"
    assert db.normalize_hhmm("9:05") == "09:05"
    assert db.normalize_hhmm("") == "" and db.normalize_hhmm(None) == ""
    for bad in ("24:00", "12:60", "abc", "1300", "12:5"):
        with pytest.raises(ValueError):
            db.normalize_hhmm(bad)


def test_new_user_has_empty_meal_times(path):
    u = db.register_user("ali123", "secret1", db_path=path)
    assert u["lunch_time"] == "" and u["dinner_time"] == "" and u["wake_time"] == ""


def test_update_profile_partial_and_persist(path):
    u = db.register_user("ali123", "secret1", db_path=path)
    r = db.update_profile(u["id"], path, wake_time="6:45", lunch_time="13:30", dinner_time="۲۰:۱۵")
    assert r["wake_time"] == "06:45" and r["lunch_time"] == "13:30" and r["dinner_time"] == "20:15" and r["profile"] == "general"
    r = db.update_profile(u["id"], path, profile="athlete", display_name="  سارا  ")
    assert r["profile"] == "athlete" and r["display_name"] == "سارا" and r["lunch_time"] == "13:30"
    assert db.verify_login("ali123", "secret1", path)["dinner_time"] == "20:15"
    r = db.update_profile(u["id"], path, lunch_time="")  # پاک کردن
    assert r["lunch_time"] == "" and r["dinner_time"] == "20:15"


def test_update_profile_validation(path):
    u = db.register_user("ali123", "secret1", db_path=path)
    with pytest.raises(ValueError):
        db.update_profile(u["id"], path, lunch_time="25:00")
    with pytest.raises(ValueError):
        db.update_profile(u["id"], path, profile="doctor")
    with pytest.raises(ValueError):
        db.update_profile(9999, path, lunch_time="12:00")
    assert db.verify_login("ali123", "secret1", path)["lunch_time"] == ""  # چیزی نیمه‌کاره ذخیره نشد


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)  # users قدیمی بدون ستون‌های ساعت غذا
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, display_name TEXT DEFAULT '', password_hash TEXT NOT NULL, salt TEXT NOT NULL, profile TEXT NOT NULL DEFAULT 'general', created_at TEXT NOT NULL, bale_chat_id TEXT, link_code TEXT)")
    conn.commit()
    conn.close()
    u = db.register_user("ali123", "secret1", db_path=p)
    assert db.update_profile(u["id"], p, dinner_time="21:00")["dinner_time"] == "21:00"


def test_api_profile_roundtrip(api):
    s, j = api("/api/register", "POST", {"username": "sara_m", "password": "secret1"})
    tok = j["token"]
    s, j = api("/api/profile", "POST", {"wake_time": "07:00", "lunch_time": "13:00", "dinner_time": "20:30", "profile": "athlete"}, tok)
    assert s == 200 and j["user"]["wake_time"] == "07:00" and j["user"]["lunch_time"] == "13:00" and j["user"]["profile"] == "athlete"
    s, j = api("/api/me", token=tok)
    assert j["user"]["dinner_time"] == "20:30"
    s, j = api("/api/login", "POST", {"username": "sara_m", "password": "secret1"})
    assert j["user"]["lunch_time"] == "13:00"


def test_api_profile_errors_and_isolation(api):
    assert api("/api/profile", "POST", {"lunch_time": "13:00"})[0] == 401
    tok = api("/api/register", "POST", {"username": "sara_m", "password": "secret1"})[1]["token"]
    assert api("/api/profile", "POST", {"wake_time": "7pm"}, tok)[0] == 400
    s, j = api("/api/profile", "POST", {"lunch_time": "99:99"}, tok)
    assert s == 400 and j["error"] == messages.PROFILE_BAD_TIME
    s, j = api("/api/profile", "POST", {"profile": "x"}, tok)
    assert s == 400 and j["error"] == messages.PROFILE_BAD_TYPE
    tok2 = api("/api/register", "POST", {"username": "other_user", "password": "secret1"})[1]["token"]
    api("/api/profile", "POST", {"lunch_time": "12:00"}, tok2)
    assert api("/api/me", token=tok)[1]["user"]["lunch_time"] == ""  # کاربر دیگر اثری ندارد


def test_meal_note_is_safe_and_not_advice():
    assert messages.is_text_safe(messages.MEAL_TIME_NOTE)
    assert "پزشک" in messages.MEAL_TIME_NOTE


def test_ui_has_profile_tab_and_note_matches_server_text():
    import re
    html = server.render_index()
    assert 'id="pw"' in html and "wake_time" in html and "viewProfile" in html and '["profile", "👤", "پروفایل"]' in html
    assert re.search(r'const MEAL_NOTE = "([^"]+)"', html).group(1) == messages.MEAL_TIME_NOTE
