"""تست‌های قابلیت‌های جدید: ثبت دستی دارو (نوع/نحوه‌ی مصرف/توضیحات) و پرونده‌های درمانی."""
import json
import re
import shutil
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

import config
import db
import server


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "t.db")


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


def _token(api, name="sara_m"):
    return api("/api/register", "POST", {"username": name, "password": "secret1"})[1]["token"]


MED = {"client_id": "m1", "name": "داروی دستی", "dose": "۲ قطره", "times_csv": "08:00,20:00", "meal_relation": "بعد از غذا",
       "drug_category": "کاربرد دلخواه", "updated_at": 100, "drug_form": "قطره", "route": "چشمی / گوشی / بینی",
       "notes": "نگه‌داری در یخچال", "file_id": "f1"}


def test_manual_fields_roundtrip(path):
    db.upsert_meds("1", [MED], path)
    m = db.list_meds_full("1", path)[0]
    assert (m["drug_form"], m["route"], m["notes"], m["file_id"]) == ("قطره", "چشمی / گوشی / بینی", "نگه‌داری در یخچال", "f1")
    db.upsert_meds("1", [dict(MED, notes="جدید", updated_at=200)], path)
    assert db.list_meds_full("1", path)[0]["notes"] == "جدید"
    db.upsert_meds("1", [dict(MED, notes="قدیمی", updated_at=50)], path)  # قدیمی‌تر نادیده
    assert db.list_meds_full("1", path)[0]["notes"] == "جدید"


def test_old_clients_without_new_fields_still_work(path):
    db.upsert_meds("1", [{"client_id": "a", "name": "x", "dose": "1", "updated_at": 1}], path)
    m = db.list_meds_full("1", path)[0]
    assert m["file_id"] == "" and m["drug_form"] == "" and m["route"] == "" and m["notes"] == ""


def test_files_upsert_lww_and_validation(path):
    db.upsert_files("1", [{"client_id": "f1", "title": "فشار خون", "icon": "❤️", "updated_at": 100},
                          {"client_id": "", "title": "بی‌شناسه"}, {"client_id": "f2", "title": "  "}], path)
    fs = db.list_files("1", path)
    assert [f["title"] for f in fs] == ["فشار خون"]
    db.upsert_files("1", [{"client_id": "f1", "title": "قدیمی", "updated_at": 50}], path)
    assert db.list_files("1", path)[0]["title"] == "فشار خون"
    db.upsert_files("1", [{"client_id": "f1", "title": "فشار", "updated_at": 300}], path)
    assert db.list_files("1", path)[0]["title"] == "فشار"


def test_delete_file_detaches_meds_but_keeps_them(path):
    db.upsert_files("1", [{"client_id": "f1", "title": "دیابت", "updated_at": 100}], path)
    db.upsert_meds("1", [MED], path)
    db.upsert_files("1", [{"client_id": "f1", "title": "دیابت", "deleted": 1, "updated_at": 200}], path)
    assert db.list_files("1", path)[0]["deleted"] == 1
    m = db.list_meds_full("1", path)[0]
    assert m["file_id"] == "" and not m["deleted"]
    assert len(db.get_medications(path, "1")) == 1


def test_logs_keep_file_id_and_adherence_by_file(path):
    logs = [{"client_id": f"l{i}", "med_name": "x", "drug_category": "c", "dose": "1", "scheduled_time": "08:00", "status": s, "file_id": f}
            for i, (s, f) in enumerate([("✅ مصرف شد", "f1"), ("❌ مصرف نشد", "f1"), ("✅ مصرف شد", "f2"), ("✅ مصرف شد", "")])]
    db.insert_logs("1", logs, path)
    assert {l["client_id"]: l["file_id"] for l in db.list_logs_full("1", path)}["l2"] == "f2"
    by = db.adherence_by_file(path, "1")
    assert by["f1"]["percent"] == 50.0 and by["f2"]["percent"] == 100.0 and by[""]["total"] == 1
    assert len(db.get_doctor_report(path, "1")) == 4  # شکل قدیمی گزارش بدون تغییر


def test_old_database_migrates(tmp_path):
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE medications (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, drug_category TEXT NOT NULL, "
                 "dose TEXT NOT NULL, times_csv TEXT NOT NULL, meal_relation TEXT DEFAULT 'x', duration_days INTEGER DEFAULT 30)")
    conn.execute("INSERT INTO medications (name,drug_category,dose,times_csv) VALUES ('a','b','c','08:00')")
    conn.commit(); conn.close()
    db.init_db(p)
    conn = sqlite3.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(medications)")}
    conn.close()
    assert {"file_id", "drug_form", "route", "notes"} <= cols
    assert len(db.get_medications(p)) == 1


def test_users_files_isolated_and_deleted_with_account(path):
    db.upsert_files("1", [{"client_id": "f1", "title": "الف", "updated_at": 1}], path)
    db.upsert_files("2", [{"client_id": "f1", "title": "ب", "updated_at": 1}], path)
    assert db.list_files("2", path)[0]["title"] == "ب"
    db.delete_user_data("1", path)
    assert db.list_files("1", path) == [] and len(db.list_files("2", path)) == 1


def test_api_sync_files_and_manual_meds(api):
    tok = _token(api)
    f = {"client_id": "f1", "title": "چربی خون", "icon": "🧈", "updated_at": 100}
    s, j = api("/api/sync", "POST", {"files": [f], "meds": [MED], "logs": [
        {"client_id": "l1", "med_name": "داروی دستی", "drug_category": "c", "dose": "۲ قطره", "scheduled_time": "08:00",
         "status": "✅ مصرف شد (به‌موقع)", "file_id": "f1"}]}, tok)
    assert s == 200
    assert j["files"][0]["title"] == "چربی خون" and j["meds"][0]["file_id"] == "f1" and j["meds"][0]["drug_form"] == "قطره"
    assert j["logs"][0]["file_id"] == "f1" and j["adherence_by_file"]["f1"]["percent"] == 100.0
    # sync بدون files (کلاینت قدیمی) پرونده‌ها را پاک نمی‌کند
    s, j = api("/api/sync", "POST", {"meds": [], "logs": []}, tok)
    assert s == 200 and len(j["files"]) == 1
    assert api("/api/sync", "POST", {"files": []})[0] == 401


def _html():
    return server.render_index()


def test_page_has_manual_entry_and_files_ui():
    h = _html()
    for word in ("ثبت دستی دارو", "نوع دارو (شکل دارویی)", "نحوه‌ی مصرف", "پرونده‌ی درمانی", "ساخت پرونده",
                 "viewFiles", "submitManual", "فشار خون", "چربی خون", "دیابت"):
        assert word in h, word
    assert not re.search(r"(?<![A-Za-z_])confirm\(", h) and not re.search(r"(?<![A-Za-z_])prompt\(", h)  # در WebView کار نمی‌کنند


def test_guide_mentions_new_features():
    h = _html()
    block = h[h.index("const TOUR = ["):h.index("function openGuide")]
    for word in ("ثبت دستی دارو", "تب «پرونده‌ها»", "ساخت پرونده", "بدون پرونده"):
        assert word in block, word


def test_page_script_still_valid_js():
    if not shutil.which("node"):
        return
    import os
    import tempfile
    script = re.findall(r"<script>(.*?)</script>", _html(), re.S)[-1]
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "page.js")
        open(fp, "w", encoding="utf-8").write(script)
        r = subprocess.run(["node", "--check", fp], capture_output=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
