import pytest

import db
import health_profile
import inventory
import messages2
import water
from datetime import datetime


@pytest.fixture
def dbp(tmp_path):
    p = str(tmp_path / "f2.db")
    db.init_db(p)
    return p


def make_user(dbp, name="user1"):
    return str(db.register_user(name, "secret1", "general", "", dbp)["id"])


def add_med(dbp, uid, cid="m1", times="08:00,20:00", name="متفورمین"):
    db.upsert_meds(uid, [{"client_id": cid, "name": name, "times_csv": times, "updated_at": 1}], dbp)


# ---------------------------------------------------------------- متن‌ها
def test_new_texts_are_safe():
    for key, text in messages2.all_texts().items():
        assert messages2.is_text_safe(text), key


# ---------------------------------------------------------------- موجودی
def test_status_math():
    s = inventory.status_for(30, 1, 5, "08:00,20:00")  # ۲ نوبت × ۱ عدد = ۲ در روز → ۱۵ روز
    assert s["days_left"] == 15 and s["status"] == "ok"
    s = inventory.status_for(9, 1, 5, "08:00,20:00", "متفورمین")
    assert s["days_left"] == 4 and s["status"] == "low" and "متفورمین" in s["message"] and "۴" not in s["message"]
    assert inventory.status_for(0.5, 1, 5, "08:00")["status"] == "empty"
    assert inventory.status_for(10, 2, 5, "")["days_left"] == 5  # بدون ساعت معتبر = ۱ نوبت


def test_stock_upsert_lww_and_consume(dbp):
    uid = make_user(dbp)
    add_med(dbp, uid)
    inventory.upsert_stock(uid, [{"med_client_id": "m1", "quantity": "۱۴", "updated_at": 100}], dbp)  # ارقام فارسی
    s = inventory.list_stock(uid, dbp)[0]
    assert s["quantity"] == 14 and s["status"] == "ok" and s["days_left"] == 7 and s["unit"] == "عدد"
    inventory.upsert_stock(uid, [{"med_client_id": "m1", "quantity": 99, "updated_at": 50}], dbp)  # قدیمی‌تر: نادیده
    assert inventory.list_stock(uid, dbp)[0]["quantity"] == 14
    item = inventory.consume(uid, "m1", None, dbp)  # یک نوبت
    assert item["quantity"] == 13
    inventory.consume(uid, "m1", 100, dbp)  # کمتر از صفر نمی‌شود
    assert inventory.list_stock(uid, dbp)[0]["quantity"] == 0
    assert inventory.list_stock(uid, dbp)[0]["status"] == "empty"
    with pytest.raises(LookupError):
        inventory.consume(uid, "nope", None, dbp)


def test_stock_validation(dbp):
    uid = make_user(dbp)
    for bad in ({"med_client_id": "m1", "quantity": -1}, {"med_client_id": "m1", "quantity": "abc"},
                {"med_client_id": "m1", "quantity": 5, "units_per_dose": 0}, {"quantity": 5}):
        with pytest.raises(ValueError):
            inventory.upsert_stock(uid, [bad], dbp, strict=True)
    assert inventory.upsert_stock(uid, [{"med_client_id": "m1", "quantity": -1}], dbp) == 0  # حالت همگام‌سازی: رد می‌شود


def test_stock_inactive_when_med_deleted(dbp):
    uid = make_user(dbp)
    add_med(dbp, uid)
    inventory.upsert_stock(uid, [{"med_client_id": "m1", "quantity": 0, "updated_at": 1}], dbp)
    assert inventory.alerts(uid, dbp)[0]["status"] == "empty"
    db.upsert_meds(uid, [{"client_id": "m1", "name": "متفورمین", "deleted": 1, "updated_at": 5}], dbp)
    assert inventory.alerts(uid, dbp) == []


# ---------------------------------------------------------------- آب
def test_water_settings_validation():
    s = water.normalize_settings({"goal_ml": "۲۵۰۰", "start_time": "۰۷:۳۰"})
    assert s["goal_ml"] == 2500 and s["start_time"] == "07:30" and s["glass_ml"] == 250
    for bad in ({"goal_ml": 100}, {"interval_min": 5}, {"start_time": "25:00"}, {"start_time": "22:00", "end_time": "08:00"},
                {"glass_ml": "x"}):
        with pytest.raises(ValueError):
            water.normalize_settings(bad)


def test_reminder_times_and_next():
    assert water.reminder_times("08:00", "10:00", 60) == ["08:00", "09:00", "10:00"]
    assert water.reminder_times("08:00", "09:40", 90) == ["08:00", "09:30"]
    s = water.normalize_settings({"start_time": "08:00", "end_time": "20:00", "interval_min": 120})
    assert water.next_reminder(s, datetime(2026, 1, 1, 9, 0)) == ("10:00", 60)
    assert water.next_reminder(s, datetime(2026, 1, 1, 21, 0))[0] == "08:00"  # فردا
    assert water.next_reminder(dict(s, enabled=0)) is None


def test_water_logs_progress_and_lww(dbp):
    uid = make_user(dbp)
    d = "1405/08/27"
    water.add_logs(uid, [{"client_id": "w1", "amount_ml": 250, "persian_date": d, "time_hm": "09:00", "updated_at": 1},
                         {"client_id": "w2", "amount_ml": "۳۰۰", "persian_date": d, "updated_at": 1},
                         {"client_id": "bad", "amount_ml": 5}, {"amount_ml": 250}], dbp)
    s = water.get_settings(uid, dbp)
    p = water.progress(s, water.list_logs(uid, dbp), d)
    assert p["drunk_ml"] == 550 and p["percent"] == 28 and p["remaining_ml"] == 1450 and p["glasses_left"] == 6 and not p["done"]
    water.add_logs(uid, [{"client_id": "w1", "amount_ml": 250, "persian_date": d, "deleted": 1, "updated_at": 2}], dbp)
    assert water.progress(s, water.list_logs(uid, dbp), d)["drunk_ml"] == 300
    water.add_logs(uid, [{"client_id": "w1", "amount_ml": 250, "persian_date": d, "deleted": 0, "updated_at": 1}], dbp)  # قدیمی
    assert water.progress(s, water.list_logs(uid, dbp), d)["drunk_ml"] == 300
    with pytest.raises(ValueError):
        water.add_logs(uid, [{"client_id": "x", "amount_ml": 1}], dbp, strict=True)


def test_water_percent_capped(dbp):
    uid = make_user(dbp)
    water.add_logs(uid, [{"client_id": "a", "amount_ml": 3000, "persian_date": "1405/01/01"}], dbp)
    p = water.progress(water.get_settings(uid, dbp), water.list_logs(uid, dbp), "1405/01/01")
    assert p["percent"] == 100 and p["done"] and p["remaining_ml"] == 0


# ---------------------------------------------------------------- پرونده‌ی سلامت
def test_health_requires_consent(dbp):
    uid = make_user(dbp)
    with pytest.raises(PermissionError):
        health_profile.save_profile(uid, {"allergies": ["پنی‌سیلین"]}, dbp)
    assert health_profile.get_profile(uid, dbp) is None


def test_health_save_clean_and_delete(dbp):
    uid = make_user(dbp)
    p = health_profile.save_profile(uid, {
        "consented": True, "allergies": ["پنی‌سیلین", " پنی‌سیلین ", "", "آسپرین"], "conditions": ["دیابت نوع ۲"],
        "emergency_name": "مریم", "emergency_relation": "همسر", "emergency_phone": "۰۹۱۲ ۱۲۳-۴۵۶۷", "notes": "x" * 900,
        "updated_at": 10}, dbp)
    assert p["allergies"] == ["پنی‌سیلین", "آسپرین"] and p["emergency_phone"] == "09121234567" and len(p["notes"]) == 500
    assert p["consented_at"]
    with pytest.raises(ValueError):
        health_profile.save_profile(uid, {"consented": True, "emergency_phone": "12ab"}, dbp)
    # نسخه‌ی قدیمی‌تر نادیده گرفته می‌شود
    health_profile.save_profile(uid, {"consented": True, "allergies": ["قدیمی"], "updated_at": 5}, dbp)
    assert health_profile.get_profile(uid, dbp)["allergies"] == ["پنی‌سیلین", "آسپرین"]
    # حذف: هیچ اطلاعات شخصی نمی‌ماند و دستگاه قدیمی نمی‌تواند برگرداند
    health_profile.delete_profile(uid, dbp)
    assert health_profile.get_profile(uid, dbp) is None
    health_profile.save_profile(uid, {"consented": True, "allergies": ["قدیمی"], "updated_at": 20}, dbp)
    health_profile.delete_profile(uid, dbp)
    import f2db
    row = f2db.connect(dbp).execute("SELECT * FROM health_profile WHERE user_id=?", (uid,)).fetchone()
    assert row["allergies"] == "[]" and row["emergency_phone"] == "" and row["notes"] == ""


def test_delete_user_data_removes_new_tables(dbp):
    uid = make_user(dbp)
    add_med(dbp, uid)
    inventory.upsert_stock(uid, [{"med_client_id": "m1", "quantity": 5}], dbp)
    water.save_settings(uid, {"goal_ml": 1800}, dbp)
    water.add_logs(uid, [{"client_id": "w", "amount_ml": 200}], dbp)
    health_profile.save_profile(uid, {"consented": True, "allergies": ["x"]}, dbp)
    db.delete_user_data(uid, dbp)
    import f2db
    conn = f2db.connect(dbp)
    for t in ("med_stock", "water_settings", "water_logs", "health_profile"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
