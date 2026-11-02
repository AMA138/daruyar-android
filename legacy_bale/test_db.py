from datetime import timedelta
import db, schedule as s

def mk():
    conn = db.connect(":memory:")
    user = db.get_or_create_user(conn, 111)
    return conn, user

def test_user_idempotent():
    conn, u = mk()
    assert db.get_or_create_user(conn, 111)["id"] == u["id"]

def test_due_and_sent_once():
    conn, u = mk()
    med = db.add_med(conn, u["id"], "تست", 1)
    db.add_dose_events(conn, med, [s.now_utc() - timedelta(minutes=1)])
    now = s.now_utc()
    assert len(db.due_events(conn, now)) == 1
    db.mark_sent(conn, db.due_events(conn, now)[0]["event_id"], now)
    assert db.due_events(conn, now) == []

def test_future_not_due():
    conn, u = mk()
    med = db.add_med(conn, u["id"], "تست", 1)
    db.add_dose_events(conn, med, [s.now_utc() + timedelta(hours=1)])
    assert db.due_events(conn, s.now_utc()) == []

def test_snooze_reactivates():
    conn, u = mk()
    med = db.add_med(conn, u["id"], "تست", 1)
    db.add_dose_events(conn, med, [s.now_utc() - timedelta(minutes=1)])
    now = s.now_utc()
    ev = db.due_events(conn, now)[0]["event_id"]
    db.mark_sent(conn, ev, now)
    db.snooze(conn, ev, now, 10)
    assert db.due_events(conn, now) == []
    assert len(db.due_events(conn, now + timedelta(minutes=11))) == 1

def test_delete_user_cascades():
    conn, u = mk()
    med = db.add_med(conn, u["id"], "تست", 1)
    db.add_dose_events(conn, med, [s.now_utc()])
    db.delete_user_data(conn, 111)
    assert conn.execute("SELECT COUNT(*) FROM meds").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM dose_events").fetchone()[0] == 0
