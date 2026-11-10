import pytest

import db


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "t.db")


def test_register_login_session(path):
    u = db.register_user("ali123", "secret1", "athlete", db_path=path)
    assert u["profile"] == "athlete"
    assert db.verify_login("ali123", "secret1", path)["id"] == u["id"]
    assert db.verify_login("ali123", "wrong", path) is None
    tok = db.create_session(u["id"], path)
    assert db.get_user_by_token(tok, path)["username"] == "ali123"
    assert db.get_user_by_token("nope", path) is None


def test_register_rules(path):
    db.register_user("ali123", "secret1", db_path=path)
    with pytest.raises(ValueError):
        db.register_user("ali123", "another1", db_path=path)
    with pytest.raises(ValueError):
        db.register_user("ab", "secret1", db_path=path)
    with pytest.raises(ValueError):
        db.register_user("okname", "123", db_path=path)


def test_password_not_stored_plain(path):
    db.register_user("ali123", "secret1", db_path=path)
    conn = db.connect(path)
    row = conn.execute("SELECT password_hash, salt FROM users").fetchone()
    conn.close()
    assert "secret1" not in row[0] and len(row[0]) == 64 and row[1]


def test_sync_last_write_wins_and_soft_delete(path):
    m = {"client_id": "a1", "name": "متفورمین", "dose": "500", "times_csv": "08:00", "meal_relation": "ناشتا", "updated_at": 100}
    db.upsert_meds("1", [m], path)
    db.upsert_meds("1", [dict(m, dose="1000", updated_at=50)], path)  # قدیمی‌تر؛ نادیده
    assert db.list_meds_full("1", path)[0]["dose"] == "500"
    db.upsert_meds("1", [dict(m, deleted=1, updated_at=200)], path)
    assert db.get_medications(path, "1") == []
    assert db.list_meds_full("1", path)[0]["deleted"] == 1


def test_logs_idempotent_and_adherence(path):
    logs = [{"client_id": f"l{i}", "med_name": "x", "drug_category": "cat", "dose": "1", "scheduled_time": "08:00", "status": s}
            for i, s in enumerate(["✅ مصرف شد", "❌ مصرف نشد", "⏳ تعویق (۱۰ دقیقه بعد)", "✅ مصرف شد"])]
    db.insert_logs("1", logs, path)
    db.insert_logs("1", logs, path)
    assert len(db.get_doctor_report(path, "1")) == 4
    assert db.calculate_adherence_percentage(path, "1") == 50.0
    assert db.adherence_by_category(path, "1")["cat"]["percent"] == 50.0
    assert db.calculate_adherence_percentage(path, "2") == 100.0


def test_users_are_isolated_and_delete_cascades(path):
    a = db.register_user("user_a", "secret1", db_path=path)
    b = db.register_user("user_b", "secret1", db_path=path)
    db.upsert_meds(a["id"], [{"client_id": "m", "name": "n", "updated_at": 1}], path)
    db.upsert_meds(b["id"], [{"client_id": "m", "name": "n", "updated_at": 1}], path)
    db.delete_user_data(a["id"], path)
    assert db.list_meds_full(a["id"], path) == [] and len(db.list_meds_full(b["id"], path)) == 1
    assert db.verify_login("user_a", "secret1", path) is None


def test_legacy_api_and_migration(path):
    import sqlite3
    conn = sqlite3.connect(path)  # دیتابیس قدیمی بدون ستون‌های جدید
    conn.execute("CREATE TABLE medications (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, drug_category TEXT NOT NULL, dose TEXT NOT NULL, times_csv TEXT NOT NULL, meal_relation TEXT DEFAULT 'x', duration_days INTEGER DEFAULT 30)")
    conn.execute("INSERT INTO medications (name, drug_category, dose, times_csv) VALUES ('old','c','1','08:00')")
    conn.commit(); conn.close()
    assert [m[1] for m in db.get_medications(path)] == ["old"]
    db.add_medication("new", "c", "2", "09:00", "همراه با غذا", 10, path)
    db.log_medication_use("new", "c", "2", "09:00", "✅ مصرف شد", db_path=path)
    db.set_user_consent("default_user", path)
    assert db.has_user_consented("default_user", path)
    db.delete_all_user_data(path)
    assert db.get_medications(path) == [] and not db.has_user_consented("default_user", path)


def test_bale_link_flow(path):
    u = db.register_user("ali123", "secret1", db_path=path)
    code = db.set_link_code(u["id"], path)
    assert db.link_bale("WRONG1", "555", path) is None
    assert db.link_bale(code, "555", path)["id"] == u["id"]
    assert db.find_user_by_chat("555", path)["id"] == u["id"]
    assert db.link_bale(code, "666", path) is None  # کد یک‌بارمصرف


def test_demo_data(path):
    db.insert_sample_demo_data(path)
    assert len(db.get_doctor_report(path)) == 21 and 0 < db.calculate_adherence_percentage(path) < 100
