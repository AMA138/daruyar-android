"""
db.py - پایگاه داده SQLite دارویار (چندکاربره + ثبت‌نام/ورود + همگام‌سازی)
فقط کتابخانه‌ی استاندارد؛ روی ویندوز و Pydroid 3 اجرا می‌شود.
سازگار با نسخه‌ی تک‌کاربره‌ی قبلی: همه‌ی توابع قدیمی هستند و user_id پیش‌فرض «default_user» است.
فایل daruyar.db قدیمی خودکار مهاجرت می‌کند (ستون‌های جدید با ALTER TABLE اضافه می‌شوند).
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time

import schedule

DEFAULT_USER = "default_user"
SESSION_TTL = 30 * 24 * 3600
PBKDF2_ROUNDS = 120_000
PROFILES = ("general", "athlete", "prosthetic_beauty")
_READY = set()

SCHEMA = {
    "users": """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, display_name TEXT DEFAULT '',
        password_hash TEXT NOT NULL, salt TEXT NOT NULL, profile TEXT NOT NULL DEFAULT 'general',
        created_at TEXT NOT NULL, bale_chat_id TEXT, link_code TEXT)""",
    "sessions": """CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at INTEGER NOT NULL)""",
    "user_consent": """CREATE TABLE IF NOT EXISTS user_consent (
        user_id TEXT PRIMARY KEY, consented INTEGER NOT NULL DEFAULT 1, consented_at TEXT NOT NULL)""",
    "medications": """CREATE TABLE IF NOT EXISTS medications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, drug_category TEXT NOT NULL,
        dose TEXT NOT NULL, times_csv TEXT NOT NULL, meal_relation TEXT DEFAULT 'بعد از غذا',
        duration_days INTEGER DEFAULT 30)""",
    "medication_logs": """CREATE TABLE IF NOT EXISTS medication_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, med_name TEXT NOT NULL, drug_category TEXT NOT NULL,
        dose TEXT NOT NULL, scheduled_time TEXT NOT NULL, actual_time TEXT NOT NULL,
        weekday_name TEXT NOT NULL, persian_date TEXT NOT NULL, status TEXT NOT NULL)""",
}
# ستون‌های اضافه‌شده در اسپرینت ۲ (برای مهاجرت دیتابیس قدیمی)
NEW_COLUMNS = {
    "users": [("lunch_time", "TEXT DEFAULT ''"), ("dinner_time", "TEXT DEFAULT ''"), ("wake_time", "TEXT DEFAULT ''")],
    "medications": [("user_id", "TEXT DEFAULT 'default_user'"), ("client_id", "TEXT"), ("group_key", "TEXT DEFAULT ''"),
                    ("deleted", "INTEGER DEFAULT 0"), ("updated_at", "INTEGER DEFAULT 0")],
    "medication_logs": [("user_id", "TEXT DEFAULT 'default_user'"), ("client_id", "TEXT"), ("meal_relation", "TEXT DEFAULT ''")],
}


def connect(db_path="daruyar.db"):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path="daruyar.db"):
    """ساخت جداول و مهاجرت ستون‌ها (فقط یک بار برای هر مسیر در هر اجرا)"""
    if db_path in _READY:
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for ddl in SCHEMA.values():
        cur.execute(ddl)
    for table, cols in NEW_COLUMNS.items():
        have = {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols:
            if col not in have:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_med_client ON medications(user_id, client_id) WHERE client_id IS NOT NULL")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_log_client ON medication_logs(user_id, client_id) WHERE client_id IS NOT NULL")
    conn.commit()
    conn.close()
    _READY.add(db_path)


def get_persian_date_and_day(now=None):
    """(تاریخ شمسی، نام روز هفته، ساعت HH:MM) به وقت تهران"""
    now = now or schedule.tehran_now()
    return schedule.jalali_date_str(now), schedule.weekday_fa(now), now.strftime("%H:%M")


# ---------------------------------------------------------------- کاربران و نشست
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return h.hex(), salt


def _user_dict(row):
    keys = row.keys()
    return {"id": str(row["id"]), "username": row["username"], "display_name": row["display_name"],
            "profile": row["profile"], "bale_linked": bool(row["bale_chat_id"]),
            "lunch_time": (row["lunch_time"] or "") if "lunch_time" in keys else "",
            "dinner_time": (row["dinner_time"] or "") if "dinner_time" in keys else "",
            "wake_time": (row["wake_time"] or "") if "wake_time" in keys else ""}


def register_user(username, password, profile="general", display_name="", db_path="daruyar.db"):
    username = (username or "").strip()
    if not (3 <= len(username) <= 32) or len(password or "") < 6:
        raise ValueError("weak")
    if profile not in PROFILES:
        profile = "general"
    h, salt = hash_password(password)
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, salt, profile, created_at) VALUES (?,?,?,?,?,?)",
            (username, display_name or username, h, salt, profile, schedule.utc_str()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise ValueError("exists")
    finally:
        conn.close()
    return _user_dict(row)


def normalize_hhmm(value):
    """«۱۳:۰۰» یا «13:0» → «13:00»؛ رشته‌ی خالی یعنی پاک‌کردن؛ مقدار نامعتبر ValueError('time')"""
    v = schedule.to_ascii_digits(value or "").strip()
    if not v:
        return ""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("time")
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


def update_profile(user_id, db_path="daruyar.db", **fields):
    """
    به‌روزرسانی پروفایل: display_name، profile، wake_time، lunch_time، dinner_time (فقط کلیدهای داده‌شده تغییر می‌کنند).
    خطاها: ValueError('time') ساعت نامعتبر ، ValueError('profile') نوع پروفایل نامعتبر ، ValueError('missing') کاربر نیست.
    """
    sets, vals = [], []
    if "display_name" in fields:
        sets.append("display_name=?")
        vals.append(str(fields["display_name"] or "").strip()[:40])
    if "profile" in fields:
        if fields["profile"] not in PROFILES:
            raise ValueError("profile")
        sets.append("profile=?")
        vals.append(fields["profile"])
    for key in ("wake_time", "lunch_time", "dinner_time"):
        if key in fields:
            sets.append(key + "=?")
            vals.append(normalize_hhmm(fields[key]))
    conn = connect(db_path)
    try:
        if sets:
            conn.execute("UPDATE users SET " + ", ".join(sets) + " WHERE id=?", vals + [int(user_id)])
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError("missing")
    return _user_dict(row)


def verify_login(username, password, db_path="daruyar.db"):
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
    conn.close()
    if not row:
        hash_password(password or "x")  # زمان پاسخ را برابر نگه می‌دارد
        return None
    h, _ = hash_password(password or "", row["salt"])
    return _user_dict(row) if hmac.compare_digest(h, row["password_hash"]) else None


def create_session(user_id, db_path="daruyar.db"):
    token = secrets.token_hex(24)
    conn = connect(db_path)
    conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)", (token, str(user_id), int(time.time())))
    conn.commit()
    conn.close()
    return token


def get_user_by_token(token, db_path="daruyar.db"):
    if not token:
        return None
    conn = connect(db_path)
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = CAST(s.user_id AS INTEGER) WHERE s.token=? AND s.created_at>?",
        (token, int(time.time()) - SESSION_TTL),
    ).fetchone()
    conn.close()
    return _user_dict(row) if row else None


def set_link_code(user_id, db_path="daruyar.db"):
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    conn = connect(db_path)
    conn.execute("UPDATE users SET link_code=? WHERE id=?", (code, int(user_id)))
    conn.commit()
    conn.close()
    return code


def link_bale(code, chat_id, db_path="daruyar.db"):
    """اتصال چت بله به حساب با کد یک‌بارمصرف؛ کاربر یا None"""
    code = (code or "").strip().upper()
    if len(code) != 6:
        return None
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM users WHERE link_code=?", (code,)).fetchone()
    if row:
        conn.execute("UPDATE users SET bale_chat_id=?, link_code=NULL WHERE id=?", (str(chat_id), row["id"]))
        conn.commit()
    conn.close()
    return _user_dict(row) if row else None


def find_user_by_chat(chat_id, db_path="daruyar.db"):
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM users WHERE bale_chat_id=?", (str(chat_id),)).fetchone()
    conn.close()
    return _user_dict(row) if row else None


# ---------------------------------------------------------------- رضایت‌نامه
def set_user_consent(user_id=DEFAULT_USER, db_path="daruyar.db"):
    date_str, weekday, hm = get_persian_date_and_day()
    conn = connect(db_path)
    conn.execute("INSERT OR REPLACE INTO user_consent (user_id, consented, consented_at) VALUES (?,1,?)",
                 (str(user_id), f"{weekday} {date_str} - {hm}"))
    conn.commit()
    conn.close()


def has_user_consented(user_id=DEFAULT_USER, db_path="daruyar.db"):
    conn = connect(db_path)
    row = conn.execute("SELECT consented FROM user_consent WHERE user_id=?", (str(user_id),)).fetchone()
    conn.close()
    return bool(row and row[0] == 1)


# ---------------------------------------------------------------- داروها
def add_medication(name, drug_category, dose, times_csv, meal_relation="بعد از غذا", duration_days=30,
                   db_path="daruyar.db", user_id=DEFAULT_USER, group_key="", client_id=None):
    conn = connect(db_path)
    cur = conn.execute(
        """INSERT INTO medications (name, drug_category, dose, times_csv, meal_relation, duration_days,
           user_id, client_id, group_key, deleted, updated_at) VALUES (?,?,?,?,?,?,?,?,?,0,?)""",
        (name, drug_category, dose, times_csv, meal_relation, int(duration_days), str(user_id), client_id,
         group_key, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def get_medications(db_path="daruyar.db", user_id=DEFAULT_USER):
    """ردیف‌های (id, name, category, dose, times_csv, meal_relation, duration_days) داروهای فعال"""
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT id, name, drug_category, dose, times_csv, meal_relation, duration_days
           FROM medications WHERE user_id=? AND COALESCE(deleted,0)=0 ORDER BY id DESC""", (str(user_id),)
    ).fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def list_meds_full(user_id, db_path="daruyar.db"):
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT client_id, name, drug_category, group_key AS "group", dose, times_csv, meal_relation,
           duration_days, deleted, updated_at FROM medications WHERE user_id=? AND client_id IS NOT NULL
           ORDER BY updated_at""", (str(user_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_meds(user_id, meds, db_path="daruyar.db"):
    """ادغام داروهای کلاینت (آخرین نوشتن برنده است؛ مقایسه با updated_at)"""
    conn = connect(db_path)
    for m in meds or []:
        cid = str(m.get("client_id") or "")[:64]
        if not cid or not m.get("name"):
            continue
        ts = int(m.get("updated_at") or 0)
        vals = (str(m["name"])[:100], str(m.get("drug_category") or "")[:120], str(m.get("dose") or "")[:60],
                str(m.get("times_csv") or "08:00")[:60], str(m.get("meal_relation") or "")[:80],
                int(m.get("duration_days") or 30), str(m.get("group") or "")[:20], 1 if m.get("deleted") else 0, ts)
        row = conn.execute("SELECT id, updated_at FROM medications WHERE user_id=? AND client_id=?", (str(user_id), cid)).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO medications (name, drug_category, dose, times_csv, meal_relation, duration_days,
                   group_key, deleted, updated_at, user_id, client_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                vals + (str(user_id), cid))
        elif ts >= (row["updated_at"] or 0):
            conn.execute(
                """UPDATE medications SET name=?, drug_category=?, dose=?, times_csv=?, meal_relation=?,
                   duration_days=?, group_key=?, deleted=?, updated_at=? WHERE id=?""", vals + (row["id"],))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- تاریخچه‌ی مصرف (MAR)
def log_medication_use(med_name, drug_category, dose, scheduled_time, status, custom_date=None,
                       custom_weekday=None, custom_actual_time=None, db_path="daruyar.db",
                       user_id=DEFAULT_USER, meal_relation="", client_id=None):
    date_str, weekday, actual = get_persian_date_and_day()
    conn = connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO medication_logs (med_name, drug_category, dose, scheduled_time, actual_time,
           weekday_name, persian_date, status, user_id, meal_relation, client_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (med_name, drug_category, dose, scheduled_time, custom_actual_time or actual, custom_weekday or weekday,
         custom_date or date_str, status, str(user_id), meal_relation, client_id))
    conn.commit()
    conn.close()


def insert_logs(user_id, logs, db_path="daruyar.db"):
    for l in logs or []:
        cid = str(l.get("client_id") or "")[:64]
        if not cid or not l.get("med_name"):
            continue
        log_medication_use(
            str(l["med_name"])[:100], str(l.get("drug_category") or "")[:120], str(l.get("dose") or "")[:60],
            str(l.get("scheduled_time") or "")[:10], str(l.get("status") or "")[:80], str(l.get("persian_date") or "")[:12] or None,
            str(l.get("weekday_name") or "")[:20] or None, str(l.get("actual_time") or "")[:10] or None,
            db_path, user_id, str(l.get("meal_relation") or "")[:80], cid)


def list_logs_full(user_id, db_path="daruyar.db"):
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT client_id, med_name, drug_category, dose, scheduled_time, actual_time, weekday_name,
           persian_date, status, meal_relation FROM medication_logs
           WHERE user_id=? AND client_id IS NOT NULL ORDER BY id""", (str(user_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_doctor_report(db_path="daruyar.db", user_id=DEFAULT_USER):
    """ردیف‌های (دارو، دسته، دوز، روز، تاریخ شمسی، ساعت مقرر، ساعت ثبت، وضعیت، شرط مصرف)؛ جدیدترین اول"""
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT med_name, drug_category, dose, weekday_name, persian_date, scheduled_time, actual_time, status,
           COALESCE(meal_relation,'') FROM medication_logs WHERE user_id=? ORDER BY id DESC""", (str(user_id),)).fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def status_kind(status):
    s = status or ""
    if "مصرف شد" in s or "مصرف کردم" in s:
        return "taken"
    if "تعویق" in s:
        return "snoozed"
    return "skipped"


def calculate_adherence_percentage(db_path="daruyar.db", user_id=DEFAULT_USER):
    rows = get_doctor_report(db_path, user_id)
    if not rows:
        return 100.0
    return round(sum(1 for r in rows if status_kind(r[7]) == "taken") / len(rows) * 100, 1)


def adherence_by_category(db_path="daruyar.db", user_id=DEFAULT_USER):
    """{دسته: {total, taken, percent}} برای شاخص پایبندی به تفکیک دسته"""
    out = {}
    for r in get_doctor_report(db_path, user_id):
        d = out.setdefault(r[1], {"total": 0, "taken": 0})
        d["total"] += 1
        d["taken"] += status_kind(r[7]) == "taken"
    for d in out.values():
        d["percent"] = round(d["taken"] / d["total"] * 100, 1)
    return out


# ---------------------------------------------------------------- حذف داده
def delete_user_data(user_id, db_path="daruyar.db"):
    """حذف کامل اطلاعات یک کاربر شامل حساب و نشست‌ها"""
    uid = str(user_id)
    conn = connect(db_path)
    for table in ("medications", "medication_logs", "user_consent", "sessions"):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
    if uid.isdigit():
        conn.execute("DELETE FROM users WHERE id=?", (int(uid),))
    conn.commit()
    conn.close()


def delete_all_user_data(db_path="daruyar.db"):
    """حذف داده‌ی کاربر محلی (دستور /delete_me در نسخه‌ی تک‌کاربره)"""
    delete_user_data(DEFAULT_USER, db_path)


def insert_sample_demo_data(db_path="daruyar.db", user_id=DEFAULT_USER):
    """داده‌ی نمونه‌ی ۷ روزه برای دمو؛ تاریخ‌ها نسبت به امروز ساخته می‌شوند"""
    from datetime import timedelta
    set_user_consent(user_id, db_path)
    if not get_medications(db_path, user_id):
        add_medication("متفورمین", "کنترل قند خون (دیابت نوع ۲)", "۵۰۰ میلی‌گرم", "14:00,20:00", "همراه با غذا", 30, db_path, user_id)
        add_medication("لوزارتان", "کنترل فشار خون", "۲۵ میلی‌گرم", "08:00,20:00", "بدون شرط خاص / موضعی", 30, db_path, user_id)
        add_medication("آتورواستاتین", "کنترل چربی خون (کلسترول)", "۲۰ میلی‌گرم", "22:00", "قبل از خواب شبانه", 30, db_path, user_id)
    plan = [("متفورمین", "کنترل قند خون (دیابت نوع ۲)", "۵۰۰ میلی‌گرم", "14:00", "همراه با غذا"),
            ("لوزارتان", "کنترل فشار خون", "۲۵ میلی‌گرم", "08:00", "بدون شرط خاص / موضعی"),
            ("آتورواستاتین", "کنترل چربی خون (کلسترول)", "۲۰ میلی‌گرم", "22:00", "قبل از خواب شبانه")]
    base = schedule.tehran_now()
    for back in range(6, -1, -1):
        day = base - timedelta(days=back)
        for i, (n, c, d, t, meal) in enumerate(plan):
            status = _demo_status((back * 5 + i * 3 + back // 2) % 9)
            actual = "—" if "نشد" in status else t
            log_medication_use(n, c, d, t, status, schedule.jalali_date_str(day), schedule.weekday_fa(day),
                               actual, db_path, user_id, meal, f"demo-{back}-{i}")


def _demo_status(roll):
    if roll == 7:
        return "❌ مصرف نشد (نخوردم)"
    if roll in (2, 4):
        return "⏳ تعویق (۱۰ دقیقه بعد)"
    return "✅ مصرف شد (به‌موقع)"
