"""
water.py - یادآوری نوشیدن آب: برنامه‌ی شخصی (هدف، لیوان، بازه‌ی ساعت، فاصله)، ثبت مصرف، پیشرفت روزانه.
مقدار هدف را کاربر تعیین می‌کند؛ عدد پیش‌فرض فقط نقطه‌ی شروع قابل‌تغییر است (توصیه‌ی پزشکی نیست).
"""
import math
import re
import time

import f2db
import schedule
from schedule import to_ascii_digits

DEFAULTS = {"goal_ml": 2000, "glass_ml": 250, "start_time": "08:00", "end_time": "22:00",
            "interval_min": 90, "enabled": 1}
_DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


def _hm(value):
    v = to_ascii_digits(value or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("water")
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


def _int(value, lo, hi):
    try:
        n = int(round(float(to_ascii_digits(value).replace("٫", ".").strip())))
    except (TypeError, ValueError):
        raise ValueError("water")
    if not (lo <= n <= hi):
        raise ValueError("water")
    return n


def _minutes(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def normalize_settings(data):
    """تنظیمات را کامل و معتبر می‌کند (کلیدهای نیامده = پیش‌فرض). خطا: ValueError('water')"""
    d = dict(DEFAULTS)
    d.update({k: data[k] for k in DEFAULTS if k in (data or {}) and data[k] not in (None, "")})
    out = {
        "goal_ml": _int(d["goal_ml"], 500, 6000),
        "glass_ml": _int(d["glass_ml"], 50, 1500),
        "start_time": _hm(d["start_time"]),
        "end_time": _hm(d["end_time"]),
        "interval_min": _int(d["interval_min"], 30, 480),
        "enabled": 1 if d["enabled"] in (1, True, "1", "true") else 0,
    }
    if _minutes(out["end_time"]) <= _minutes(out["start_time"]):
        raise ValueError("water")
    return out


def reminder_times(start_time, end_time, interval_min):
    """ساعت‌های یادآوری از شروع تا پایان با فاصله‌ی ثابت، مثلاً ['08:00','09:30',...]"""
    a, b, step = _minutes(start_time), _minutes(end_time), int(interval_min)
    if b <= a or step <= 0:
        return []
    return ["%02d:%02d" % divmod(t, 60) for t in range(a, b + 1, step)]


def next_reminder(settings, now_dt=None):
    """(ساعت بعدی، دقیقه‌ی باقی‌مانده) یا None اگر یادآوری خاموش است"""
    if not settings.get("enabled"):
        return None
    times = reminder_times(settings["start_time"], settings["end_time"], settings["interval_min"])
    hm, _, diff = schedule.next_due(times, now_dt=now_dt)
    return (hm, diff) if hm else None


def get_settings(user_id, db_path):
    """تنظیمات ذخیره‌شده یا پیش‌فرض (updated_at=0 یعنی هنوز هرگز ذخیره نشده)"""
    conn = f2db.connect(db_path)
    row = conn.execute("SELECT * FROM water_settings WHERE user_id=?", (str(user_id),)).fetchone()
    conn.close()
    if row is None:
        return dict(DEFAULTS, updated_at=0)
    return {k: row[k] for k in (*DEFAULTS, "updated_at")}


def save_settings(user_id, data, db_path, strict=True):
    """ذخیره‌ی تنظیمات (آخرین updated_at برنده). strict=False: ورودی نامعتبر نادیده گرفته می‌شود."""
    try:
        s = normalize_settings(data)
    except ValueError:
        if strict:
            raise
        return get_settings(user_id, db_path)
    ts = int((data or {}).get("updated_at") or int(time.time() * 1000))
    conn = f2db.connect(db_path)
    try:
        row = conn.execute("SELECT updated_at FROM water_settings WHERE user_id=?", (str(user_id),)).fetchone()
        if row is None:
            conn.execute("""INSERT INTO water_settings (user_id, goal_ml, glass_ml, start_time, end_time, interval_min, enabled, updated_at)
                            VALUES (?,?,?,?,?,?,?,?)""",
                         (str(user_id), s["goal_ml"], s["glass_ml"], s["start_time"], s["end_time"], s["interval_min"], s["enabled"], ts))
        elif ts >= row["updated_at"]:
            conn.execute("""UPDATE water_settings SET goal_ml=?, glass_ml=?, start_time=?, end_time=?, interval_min=?, enabled=?, updated_at=?
                            WHERE user_id=?""",
                         (s["goal_ml"], s["glass_ml"], s["start_time"], s["end_time"], s["interval_min"], s["enabled"], ts, str(user_id)))
        conn.commit()
    finally:
        conn.close()
    return get_settings(user_id, db_path)


def add_logs(user_id, logs, db_path, strict=False):
    """
    ثبت/ادغام مصرف آب (idempotent با client_id؛ آخرین updated_at برنده است، حذف با deleted=1).
    هر ردیف: {client_id, amount_ml, persian_date?, time_hm?, deleted?, updated_at?}
    """
    conn = f2db.connect(db_path)
    accepted = 0
    try:
        for l in logs or []:
            try:
                if not isinstance(l, dict):
                    raise ValueError("log")
                cid = str(l.get("client_id") or "")[:64]
                if not cid:
                    raise ValueError("log")
                amount = _int(l.get("amount_ml"), 10, 3000)
            except ValueError:
                if strict:
                    raise ValueError("water_log")
                continue
            date = to_ascii_digits(l.get("persian_date") or "").strip()
            if not _DATE_RE.match(date):
                date = schedule.jalali_date_str()
            try:
                hm = _hm(l.get("time_hm"))
            except ValueError:
                hm = schedule.tehran_now().strftime("%H:%M")
            ts = int(l.get("updated_at") or int(time.time() * 1000))
            deleted = 1 if l.get("deleted") else 0
            row = conn.execute("SELECT updated_at FROM water_logs WHERE user_id=? AND client_id=?", (str(user_id), cid)).fetchone()
            if row is None:
                conn.execute("INSERT INTO water_logs (user_id, client_id, persian_date, time_hm, amount_ml, deleted, updated_at) VALUES (?,?,?,?,?,?,?)",
                             (str(user_id), cid, date, hm, amount, deleted, ts))
            elif ts >= row["updated_at"]:
                conn.execute("UPDATE water_logs SET persian_date=?, time_hm=?, amount_ml=?, deleted=?, updated_at=? WHERE user_id=? AND client_id=?",
                             (date, hm, amount, deleted, ts, str(user_id), cid))
            accepted += 1
        conn.commit()
    finally:
        conn.close()
    return accepted


def list_logs(user_id, db_path, date=None, limit=2000):
    """ردیف‌های مصرف آب (شامل حذف‌شده‌ها برای همگام‌سازی)؛ با date فقط همان روز"""
    conn = f2db.connect(db_path)
    sql = "SELECT client_id, persian_date, time_hm, amount_ml, deleted, updated_at FROM water_logs WHERE user_id=?"
    args = [str(user_id)]
    if date:
        sql += " AND persian_date=?"
        args.append(date)
    rows = conn.execute(sql + " ORDER BY updated_at DESC LIMIT ?", args + [int(limit)]).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def progress(settings, logs, date=None):
    """پیشرفت روز: {date, drunk_ml, goal_ml, percent (حداکثر ۱۰۰), remaining_ml, glasses_left, done}"""
    date = date or schedule.jalali_date_str()
    drunk = sum(l["amount_ml"] for l in logs if l["persian_date"] == date and not l.get("deleted"))
    goal, glass = settings["goal_ml"], settings["glass_ml"]
    remaining = max(0, goal - drunk)
    return {"date": date, "drunk_ml": drunk, "goal_ml": goal, "percent": min(100, round(drunk / goal * 100)),
            "remaining_ml": remaining, "glasses_left": int(math.ceil(remaining / glass)) if glass else 0,
            "done": drunk >= goal}


def overview(user_id, db_path, date=None):
    """خلاصه‌ی کامل برای API: تنظیمات، لیست ساعت‌های یادآوری، پیشرفت امروز و یادآوری بعدی"""
    s = get_settings(user_id, db_path)
    date = date or schedule.jalali_date_str()
    logs = list_logs(user_id, db_path, date)
    nxt = next_reminder(s)
    return {"settings": s, "reminders": reminder_times(s["start_time"], s["end_time"], s["interval_min"]) if s["enabled"] else [],
            "next_reminder": {"time": nxt[0], "minutes": nxt[1]} if nxt else None,
            "progress": progress(s, logs, date), "logs": [l for l in logs if not l["deleted"]]}
