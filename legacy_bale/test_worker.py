from datetime import timedelta
import db, schedule as s, reminder_worker as w

class FakeClient:
    def __init__(self): self.sent = []
    def send_message(self, chat_id, text, reply_markup=None): self.sent.append((chat_id, text, reply_markup))

def setup_one(dose=""):
    conn = db.connect(":memory:")
    u = db.get_or_create_user(conn, 5)
    med = db.add_med(conn, u["id"], "دارو", 1, dose_text=dose)
    db.add_dose_events(conn, med, [s.now_utc() - timedelta(minutes=2)])
    return conn

def test_no_duplicate_sends():
    conn = setup_one("۱ عدد"); c = FakeClient()
    assert w.send_due(c, conn) == 1
    assert w.send_due(c, conn) == 0
    assert len(c.sent) == 1 and "دارو" in c.sent[0][1]

def test_buttons_present():
    conn = setup_one(); c = FakeClient(); w.send_due(c, conn)
    assert len(c.sent[0][2]["inline_keyboard"][0]) == 3
