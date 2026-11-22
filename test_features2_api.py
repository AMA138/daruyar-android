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
    srv = server.make_server("127.0.0.1", 0, str(tmp_path / "f2api.db"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, method="GET", body=None, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    yield call
    srv.shutdown()


def signup(api, name="sara_m"):
    s, j = api("/api/register", "POST", {"username": name, "password": "secret1"})
    assert s == 201
    return j["token"]


MED = {"client_id": "m1", "name": "متفورمین", "drug_category": "کنترل قند خون", "dose": "۵۰۰ میلی‌گرم",
       "times_csv": "08:00,20:00", "meal_relation": "همراه با غذا", "group": "chronic", "updated_at": 10}


def test_auth_required(api):
    for method, path in (("GET", "/api/stock"), ("GET", "/api/water"), ("GET", "/api/health_profile"),
                         ("POST", "/api/stock"), ("POST", "/api/water"), ("POST", "/api/health_profile"),
                         ("POST", "/api/health_profile/delete"), ("POST", "/api/sync2"), ("POST", "/api/stock/consume")):
        assert api(path, method, {} if method == "POST" else None)[0] == 401, path
    assert api("/api/stock", token="bad")[0] == 401


def test_stock_flow(api):
    tok = signup(api)
    api("/api/sync", "POST", {"meds": [MED]}, tok)
    s, j = api("/api/stock", "POST", {"med_client_id": "m1", "quantity": 7, "units_per_dose": 1, "low_days": 5}, tok)
    assert s == 200 and j["stock"][0]["status"] == "low" and j["stock"][0]["days_left"] == 3
    s, j = api("/api/stock", token=tok)
    assert j["alerts"][0]["med_name"] == "متفورمین" and "متفورمین" in j["alerts"][0]["message"]
    s, j = api("/api/stock/consume", "POST", {"med_client_id": "m1"}, tok)
    assert s == 200 and j["item"]["quantity"] == 6
    assert api("/api/stock/consume", "POST", {"med_client_id": "zzz"}, tok)[0] == 404
    assert api("/api/stock", "POST", {"med_client_id": "m1", "quantity": -3}, tok)[0] == 400
    other = signup(api, "other_user")
    assert api("/api/stock", token=other)[1]["stock"] == []  # کاربر دیگر نمی‌بیند


def test_water_flow(api):
    tok = signup(api)
    s, j = api("/api/water", token=tok)
    assert s == 200 and j["settings"]["goal_ml"] == 2000 and j["progress"]["drunk_ml"] == 0 and "note" in j
    s, j = api("/api/water", "POST", {"settings": {"goal_ml": 1500, "start_time": "09:00", "end_time": "21:00", "interval_min": 120}}, tok)
    assert s == 200 and j["reminders"] == ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00"]
    s, j = api("/api/water", "POST", {"add_ml": 250}, tok)
    assert s == 200 and j["progress"]["drunk_ml"] == 250 and j["progress"]["goal_ml"] == 1500
    assert api("/api/water", "POST", {"settings": {"goal_ml": 10}}, tok)[0] == 400
    assert api("/api/water", "POST", {"add_ml": 1}, tok)[0] == 400


def test_health_profile_flow(api):
    tok = signup(api)
    api("/api/sync", "POST", {"meds": [MED]}, tok)
    assert api("/api/health_profile", token=tok)[1]["health_profile"] is None
    assert api("/api/health_profile", "POST", {"allergies": ["پنی‌سیلین"]}, tok)[0] == 403  # بدون رضایت
    s, j = api("/api/health_profile", "POST", {"consented": True, "allergies": ["پنی‌سیلین"], "emergency_name": "مریم",
                                                "emergency_phone": "09121234567"}, tok)
    assert s == 200 and j["health_profile"]["allergies"] == ["پنی‌سیلین"]
    s, j = api("/api/health_profile", token=tok)
    assert j["current_meds"][0]["name"] == "متفورمین" and j["health_profile"]["emergency_phone"] == "09121234567"
    assert api("/api/health_profile", "POST", {"consented": True, "emergency_phone": "abc"}, tok)[0] == 400
    other = signup(api, "other_user")
    assert api("/api/health_profile", token=other)[1]["health_profile"] is None
    assert api("/api/health_profile/delete", "POST", {}, tok)[0] == 200
    assert api("/api/health_profile", token=tok)[1]["health_profile"] is None


def test_sync2_roundtrip_and_idempotent(api):
    tok = signup(api)
    api("/api/sync", "POST", {"meds": [MED]}, tok)
    body = {"stock": [{"med_client_id": "m1", "quantity": 20, "updated_at": 100}, {"med_client_id": "m1x", "quantity": -5}],
            "water_settings": {"goal_ml": 2200, "updated_at": 100},
            "water_logs": [{"client_id": "w1", "amount_ml": 300, "persian_date": "1405/08/27", "time_hm": "10:00", "updated_at": 100}],
            "health_profile": {"consented": True, "allergies": ["گرد و غبار"], "updated_at": 100}}
    for _ in range(2):  # دوبار = بدون تکرار
        s, j = api("/api/sync2", "POST", body, tok)
        assert s == 200
    assert len(j["stock"]) == 1 and j["stock"][0]["quantity"] == 20
    assert j["water"]["settings"]["goal_ml"] == 2200 and len(j["water"]["all_logs"]) == 1
    assert j["health_profile"]["allergies"] == ["گرد و غبار"]
    # حذف از دستگاه (tombstone) در همگام‌سازی
    s, j = api("/api/sync2", "POST", {"health_profile": {"consented": False, "updated_at": 200}}, tok)
    assert j["health_profile"] is None


def test_delete_me_removes_new_data(api):
    tok = signup(api)
    api("/api/sync", "POST", {"meds": [MED]}, tok)
    api("/api/sync2", "POST", {"stock": [{"med_client_id": "m1", "quantity": 5}],
                              "health_profile": {"consented": True, "allergies": ["x"]}}, tok)
    assert api("/api/delete_me", "POST", {}, tok)[0] == 200
    assert api("/api/stock", token=tok)[0] == 401
