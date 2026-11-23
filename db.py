"""
db.py - پایگاه داده SQLite دارویار (چندکاربره + ثبت‌نام/ورود + همگام‌سازی)
فقط کتابخانه‌ی استاندارد؛ روی ویندوز و Pydroid 3 اجرا می‌شود.
سازگار با نسخه‌ی تک‌کاربره‌ی قبلی: همه‌ی توابع قدیمی هستند و user_id پیش‌فرض «default_user» است.
فایل daruyar.db قدیمی خودکار مهاجرت می‌کند (ستون‌های جدید با ALTER TABLE اضافه می‌شوند).
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

import schedule

DEFAULT_USER = "default_user"
SESSION_TTL = 30 * 24 * 3600
PBKDF2_ROUNDS = 600_000          # دورهای هش برای حساب‌های جدید (توصیه‌ی OWASP برای PBKDF2-HMAC-SHA256)
LEGACY_PBKDF2_ROUNDS = 120_000   # حساب‌های قدیمی؛ با اولین ورود موفق خودکار ارتقا می‌یابند
MAX_PASSWORD = 128               # سقف طول رمز (جلوگیری از مصرف CPU با رمزهای عظیم)
LINK_CODE_TTL = 600              # اعتبار کد اتصال بله: ۱۰ دقیقه
MAX_SYNC_ITEMS = 5000            # سقف تعداد ردیف در هر لیست همگام‌سازی
ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
INT_MAX = 2 ** 53 - 1
PROFILES = ("general", "athlete", "prosthetic_beauty")
_READY = set()

SCHEMA = {
    "users": """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, display_name TEXT DEFAULT '',
        password_hash TEXT NOT NULL, salt TEXT NOT NULL, profile TEXT NOT NULL DEFAULT 'general', allergies TEXT DEFAULT '',
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
    # پرونده‌های درمانی (v3): هر کاربر می‌تواند چند پرونده بسازد (مثلاً فشار خون، چربی، دیابت)
    "health_files": """CREATE TABLE IF NOT EXISTS health_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, client_id TEXT NOT NULL,
        title TEXT NOT NULL, icon TEXT DEFAULT '', note TEXT DEFAULT '',
        deleted INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0)""",
}
# ستون‌های اضافه‌شده در اسپرینت ۲ (برای مهاجرت دیتابیس قدیمی)
NEW_COLUMNS = {
    "users": [("lunch_time", "TEXT DEFAULT ''"), ("dinner_time", "TEXT DEFAULT ''"), ("wake_time", "TEXT DEFAULT ''"), ("allergies", "TEXT DEFAULT ''"),
              ("pw_rounds", "INTEGER DEFAULT 120000"), ("link_code_at", "INTEGER DEFAULT 0")],
    "medications": [("user_id", "TEXT DEFAULT 'default_user'"), ("client_id", "TEXT"), ("group_key", "TEXT DEFAULT ''"),
                    ("deleted", "INTEGER DEFAULT 0"), ("updated_at", "INTEGER DEFAULT 0"),
                    ("start_date", "TEXT DEFAULT ''"), ("interval_days", "INTEGER DEFAULT 1"),
                    ("exercise_time", "TEXT DEFAULT ''"), ("allergy_notes", "TEXT DEFAULT ''"),
                    ("review_after_days", "INTEGER DEFAULT 0"),
                    # v3: پرونده‌ی درمانی + ثبت دستی (نوع دارو، نحوه‌ی مصرف، توضیحات)
                    ("file_id", "TEXT DEFAULT ''"), ("drug_form", "TEXT DEFAULT ''"), ("route", "TEXT DEFAULT ''"),
                    ("notes", "TEXT DEFAULT ''")],
    "medication_logs": [("user_id", "TEXT DEFAULT 'default_user'"), ("client_id", "TEXT"),
                        ("meal_relation", "TEXT DEFAULT ''"), ("group_key", "TEXT DEFAULT ''"),
                        ("file_id", "TEXT DEFAULT ''")],
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
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_file_client ON health_files(user_id, client_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_log_client ON medication_logs(user_id, client_id) WHERE client_id IS NOT NULL")
    # مهاجرت نشست‌های قدیمی: توکن خام (۴۸ نویسه) → SHA-256 (۶۴ نویسه). فقط هش در دیتابیس می‌ماند.
    for (tok,) in cur.execute("SELECT token FROM sessions WHERE length(token)<>64").fetchall():
        cur.execute("UPDATE sessions SET token=? WHERE token=?", (_tok_hash(tok), tok))
    conn.commit()
    conn.close()
    if db_path != ":memory:":
        try:
            os.chmod(db_path, 0o600)  # فقط مالک فایل بتواند بخواند (روی ویندوز/Pydroid ممکن است بی‌اثر باشد)
        except OSError:
            pass
    _READY.add(db_path)


def get_persian_date_and_day(now=None):
    """(تاریخ شمسی، نام روز هفته، ساعت HH:MM) به وقت تهران"""
    now = now or schedule.tehran_now()
    return schedule.jalali_date_str(now), schedule.weekday_fa(now), now.strftime("%H:%M")


# ---------------------------------------------------------------- اعتبارسنجی ورودی
def clean_id(value):
    """شناسه‌ی کلاینت: فقط حروف/ارقام و _ . : - تا ۶۴ نویسه؛ در غیر این صورت رشته‌ی خالی"""
    v = value if isinstance(value, str) else ""
    return v if ID_RE.match(v) else ""


def _i(value, lo, hi, default=0):
    """عدد صحیح در بازه‌ی [lo, hi]؛ ورودی نامعتبر یا خارج از بازه → default (هرگز استثنا نمی‌دهد)"""
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return n if lo <= n <= hi else default


def _dicts(items):
    """فقط لیستِ دیکشنری‌ها، حداکثر MAX_SYNC_ITEMS ردیف (بقیه‌ی انواع نادیده گرفته می‌شوند)"""
    if not isinstance(items, list):
        return []
    return [x for x in items[:MAX_SYNC_ITEMS] if isinstance(x, dict)]


def _tok_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- کاربران و نشست
def hash_password(password, salt=None, rounds=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), rounds or PBKDF2_ROUNDS)
    return h.hex(), salt


def _user_dict(row):
    keys = row.keys()
    return {"id": str(row["id"]), "username": row["username"], "display_name": row["display_name"],
            "profile": row["profile"], "bale_linked": bool(row["bale_chat_id"]),
            "lunch_time": (row["lunch_time"] or "") if "lunch_time" in keys else "",
            "dinner_time": (row["dinner_time"] or "") if "dinner_time" in keys else "",
            "wake_time": (row["wake_time"] or "") if "wake_time" in keys else "",
            "allergies": (row["allergies"] or "") if "allergies" in keys else ""}


def register_user(username, password, profile="general", display_name="", db_path="daruyar.db"):
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("weak")
    username = username.strip()
    if not (3 <= len(username) <= 32) or not (6 <= len(password) <= MAX_PASSWORD):
        raise ValueError("weak")
    if profile not in PROFILES:
        profile = "general"
    display_name = display_name.strip()[:40] if isinstance(display_name, str) else ""
    h, salt = hash_password(password)
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, salt, profile, created_at, pw_rounds) VALUES (?,?,?,?,?,?,?)",
            (username, display_name or username, h, salt, profile, schedule.utc_str(), PBKDF2_ROUNDS),
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
    if "allergies" in fields:
        sets.append("allergies=?")
        vals.append(str(fields["allergies"] or "").strip()[:1000])
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
    if not isinstance(username, str) or not isinstance(password, str) or len(password) > MAX_PASSWORD:
        return None
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
        if not row:
            hash_password(password or "x")  # زمان پاسخ را برابر نگه می‌دارد
            return None
        rounds = row["pw_rounds"] or LEGACY_PBKDF2_ROUNDS
        h, _ = hash_password(password, row["salt"], rounds)
        if not hmac.compare_digest(h, row["password_hash"]):
            return None
        if rounds < PBKDF2_ROUNDS:  # ارتقای بی‌صدای هش قدیمی به تعداد دور فعلی
            nh, nsalt = hash_password(password)
            conn.execute("UPDATE users SET password_hash=?, salt=?, pw_rounds=? WHERE id=?", (nh, nsalt, PBKDF2_ROUNDS, row["id"]))
            conn.commit()
        return _user_dict(row)
    finally:
        conn.close()


def create_session(user_id, db_path="daruyar.db"):
    """توکن تصادفی ۱۹۲بیتی؛ فقط SHA-256 آن در دیتابیس ذخیره می‌شود (نشت دیتابیس = نشت توکن فعال نیست)"""
    token = secrets.token_hex(24)
    now = int(time.time())
    conn = connect(db_path)
    conn.execute("DELETE FROM sessions WHERE created_at<=?", (now - SESSION_TTL,))  # پاک‌سازی نشست‌های منقضی
    conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)", (_tok_hash(token), str(user_id), now))
    conn.commit()
    conn.close()
    return token


def revoke_session(token, db_path="daruyar.db"):
    """خروج از حساب در سمت سرور؛ True اگر نشستی حذف شد"""
    if not isinstance(token, str) or not token:
        return False
    conn = connect(db_path)
    cur = conn.execute("DELETE FROM sessions WHERE token=?", (_tok_hash(token),))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_user_by_token(token, db_path="daruyar.db"):
    if not token or not isinstance(token, str):
        return None
    conn = connect(db_path)
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = CAST(s.user_id AS INTEGER) WHERE s.token=? AND s.created_at>?",
        (_tok_hash(token), int(time.time()) - SESSION_TTL),
    ).fetchone()
    conn.close()
    return _user_dict(row) if row else None


def set_link_code(user_id, db_path="daruyar.db"):
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    conn = connect(db_path)
    conn.execute("UPDATE users SET link_code=?, link_code_at=? WHERE id=?", (code, int(time.time()), int(user_id)))
    conn.commit()
    conn.close()
    return code


def link_bale(code, chat_id, db_path="daruyar.db"):
    """اتصال چت بله به حساب با کد یک‌بارمصرف (اعتبار ۱۰ دقیقه)؛ کاربر یا None"""
    code = (code or "").strip().upper() if isinstance(code, str) else ""
    if len(code) != 6:
        return None
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE link_code=? AND link_code_at>?",
                           (code, int(time.time()) - LINK_CODE_TTL)).fetchone()
        if not row:
            return None
        cur = conn.execute("UPDATE users SET bale_chat_id=?, link_code=NULL WHERE id=? AND link_code=?",
                           (str(chat_id), row["id"], code))
        if cur.rowcount != 1:  # کد همزمان مصرف شد
            return None
        # یک چت فقط به یک حساب وصل باشد
        conn.execute("UPDATE users SET bale_chat_id=NULL WHERE bale_chat_id=? AND id<>?", (str(chat_id), row["id"]))
        conn.commit()
        return _user_dict(conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone())
    finally:
        conn.close()


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
                   db_path="daruyar.db", user_id=DEFAULT_USER, group_key="", client_id=None,
                   file_id="", drug_form="", route="", notes=""):
    conn = connect(db_path)
    cur = conn.execute(
        """INSERT INTO medications (name, drug_category, dose, times_csv, meal_relation, duration_days,
           user_id, client_id, group_key, deleted, updated_at, file_id, drug_form, route, notes)
           VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
        (name, drug_category, dose, times_csv, meal_relation, int(duration_days), str(user_id), client_id,
         group_key, int(time.time() * 1000), file_id, drug_form, route, notes),
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
           duration_days, deleted, updated_at, start_date, interval_days, exercise_time, allergy_notes, review_after_days,
           COALESCE(file_id,'') AS file_id, COALESCE(drug_form,'') AS drug_form,
           COALESCE(route,'') AS route, COALESCE(notes,'') AS notes FROM medications WHERE user_id=? AND client_id IS NOT NULL
           ORDER BY updated_at""", (str(user_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_meds(user_id, meds, db_path="daruyar.db"):
    """ادغام داروهای کلاینت (آخرین نوشتن برنده است؛ مقایسه با updated_at)"""
    conn = connect(db_path)
    for m in _dicts(meds):
        cid = clean_id(m.get("client_id"))
        if not cid or not m.get("name"):
            continue
        ts = _i(m.get("updated_at"), 0, INT_MAX)
        vals = (str(m["name"])[:100], str(m.get("drug_category") or "")[:120], str(m.get("dose") or "")[:60],
                str(m.get("times_csv") or "08:00")[:60], str(m.get("meal_relation") or "")[:80],
                _i(m.get("duration_days"), 0, 3650), str(m.get("group") or "")[:20], 1 if m.get("deleted") else 0, ts,
                str(m.get("start_date") or "")[:10], _i(m.get("interval_days"), 1, 365, 1),
                str(m.get("exercise_time") or "")[:5], str(m.get("allergy_notes") or "")[:500],
                _i(m.get("review_after_days"), 0, 3650),
                clean_id(m.get("file_id")), str(m.get("drug_form") or "")[:40], str(m.get("route") or "")[:40],
                str(m.get("notes") or "")[:300])
        row = conn.execute("SELECT id, updated_at FROM medications WHERE user_id=? AND client_id=?", (str(user_id), cid)).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO medications (name, drug_category, dose, times_csv, meal_relation, duration_days,
                   group_key, deleted, updated_at, start_date, interval_days, exercise_time, allergy_notes, review_after_days,
                   file_id, drug_form, route, notes, user_id, client_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                vals + (str(user_id), cid))
        elif ts >= (row["updated_at"] or 0):
            conn.execute(
                """UPDATE medications SET name=?, drug_category=?, dose=?, times_csv=?, meal_relation=?,
                   duration_days=?, group_key=?, deleted=?, updated_at=?, start_date=?, interval_days=?,
                   exercise_time=?, allergy_notes=?, review_after_days=?, file_id=?, drug_form=?, route=?, notes=?
                   WHERE id=?""", vals + (row["id"],))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- پرونده‌های درمانی (v3)
def list_files(user_id, db_path="daruyar.db"):
    """همه‌ی پرونده‌ها (حذف‌شده‌ها هم با deleted=1 برای همگام‌سازی)"""
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT client_id, title, icon, note, deleted, updated_at FROM health_files
           WHERE user_id=? ORDER BY updated_at""", (str(user_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_files(user_id, files, db_path="daruyar.db"):
    """ادغام پرونده‌های کلاینت (آخرین نوشتن برنده است). حذف پرونده، داروهایش را حذف نمی‌کند؛ از پرونده خارج می‌شوند."""
    conn = connect(db_path)
    for f in _dicts(files):
        cid = clean_id(f.get("client_id"))
        title = str(f.get("title") or "").strip()[:60]
        if not cid or not title:
            continue
        ts = _i(f.get("updated_at"), 0, INT_MAX)
        deleted = 1 if f.get("deleted") else 0
        vals = (title, str(f.get("icon") or "")[:8], str(f.get("note") or "")[:300], deleted, ts)
        row = conn.execute("SELECT id, updated_at FROM health_files WHERE user_id=? AND client_id=?", (str(user_id), cid)).fetchone()
        if row is None:
            conn.execute("INSERT INTO health_files (title, icon, note, deleted, updated_at, user_id, client_id) VALUES (?,?,?,?,?,?,?)",
                         vals + (str(user_id), cid))
        elif ts >= (row["updated_at"] or 0):
            conn.execute("UPDATE health_files SET title=?, icon=?, note=?, deleted=?, updated_at=? WHERE id=?", vals + (row["id"],))
        if deleted and (row is None or ts >= (row["updated_at"] or 0)):
            conn.execute("UPDATE medications SET file_id='', updated_at=? WHERE user_id=? AND file_id=?",
                         (max(ts, int(time.time() * 1000)), str(user_id), cid))
    conn.commit()
    conn.close()


def adherence_by_file(db_path="daruyar.db", user_id=DEFAULT_USER):
    """{file_id: {total, taken, percent}} ؛ نوبت‌های بدون پرونده زیر کلید «» می‌آیند"""
    conn = connect(db_path)
    rows = conn.execute("SELECT COALESCE(file_id,''), status FROM medication_logs WHERE user_id=?", (str(user_id),)).fetchall()
    conn.close()
    out = {}
    for fid, status in rows:
        d = out.setdefault(fid, {"total": 0, "taken": 0})
        d["total"] += 1
        d["taken"] += status_kind(status) == "taken"
    for d in out.values():
        d["percent"] = round(d["taken"] / d["total"] * 100, 1)
    return out


# ---------------------------------------------------------------- تاریخچه‌ی مصرف (MAR)
def log_medication_use(med_name, drug_category, dose, scheduled_time, status, custom_date=None,
                       custom_weekday=None, custom_actual_time=None, db_path="daruyar.db",
                       user_id=DEFAULT_USER, meal_relation="", client_id=None, group_key="", file_id=""):
    date_str, weekday, actual = get_persian_date_and_day()
    conn = connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO medication_logs (med_name, drug_category, dose, scheduled_time, actual_time,
           weekday_name, persian_date, status, user_id, meal_relation, client_id, group_key, file_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (med_name, drug_category, dose, scheduled_time, custom_actual_time or actual, custom_weekday or weekday,
         custom_date or date_str, status, str(user_id), meal_relation, client_id, group_key, file_id))
    conn.commit()
    conn.close()


def insert_logs(user_id, logs, db_path="daruyar.db"):
    for l in _dicts(logs):
        cid = clean_id(l.get("client_id"))
        if not cid or not l.get("med_name"):
            continue
        log_medication_use(
            str(l["med_name"])[:100], str(l.get("drug_category") or "")[:120], str(l.get("dose") or "")[:60],
            str(l.get("scheduled_time") or "")[:10], str(l.get("status") or "")[:80], str(l.get("persian_date") or "")[:12] or None,
            str(l.get("weekday_name") or "")[:20] or None, str(l.get("actual_time") or "")[:10] or None,
            db_path, user_id, str(l.get("meal_relation") or "")[:80], cid, str(l.get("group") or "")[:20],
            clean_id(l.get("file_id")))


def list_logs_full(user_id, db_path="daruyar.db"):
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT client_id, med_name, drug_category, dose, scheduled_time, actual_time, weekday_name,
           persian_date, status, meal_relation, group_key AS "group", COALESCE(file_id,'') AS file_id FROM medication_logs
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
    for table in ("medications", "medication_logs", "health_files", "user_consent", "sessions"):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
    if uid.isdigit():
        conn.execute("DELETE FROM users WHERE id=?", (int(uid),))
    conn.commit()
    conn.close()
    try:  # قابلیت‌های جدید (موجودی، آب، پرونده‌ی سلامت)
        import features2
        features2.delete_user_data(uid, db_path)
    except ModuleNotFoundError as exc:
        if exc.name != "features2":
            raise


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
