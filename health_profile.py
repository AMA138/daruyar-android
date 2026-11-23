"""
health_profile.py - پرونده‌ی اطلاعات ضروری سلامت (فقط آنچه خود کاربر اعلام می‌کند، فقط با رضایت او).
حساسیت‌های دارویی، بیماری‌های اعلام‌شده، داروهای دیگر، تماس اضطراری، یادداشت.
حذف = ردیف خالی بدون اطلاعات شخصی (consented=0) می‌ماند تا یک دستگاه قدیمی نتواند داده را دوباره بالا بیاورد.
"""
import json
import re
import time

import f2db
import schedule
from schedule import to_ascii_digits

MAX_ITEMS, MAX_LEN, MAX_NOTES = 30, 80, 500
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def _ts(value):
    import db
    return db._i(value, 1, db.INT_MAX, int(time.time() * 1000))


def clean_list(value):
    """فهرست رشته‌ها: تمیز، بدون تکرار، حداکثر ۳۰ مورد و هر مورد ۸۰ نویسه"""
    out = []
    for v in value if isinstance(value, list) else []:
        s = " ".join(str(v or "").split())[:MAX_LEN]
        if s and s not in out:
            out.append(s)
    return out[:MAX_ITEMS]


def clean_phone(value):
    """شماره‌ی تماس: ارقام فارسی/عربی تبدیل می‌شوند؛ خالی مجاز است؛ نامعتبر ValueError('phone')"""
    v = re.sub(r"[\s\-()]", "", to_ascii_digits(value or ""))
    if not v:
        return ""
    if not _PHONE_RE.match(v):
        raise ValueError("phone")
    return v


def _row_to_dict(row):
    return {"allergies": json.loads(row["allergies"]), "conditions": json.loads(row["conditions"]),
            "other_meds": json.loads(row["other_meds"]), "emergency_name": row["emergency_name"],
            "emergency_relation": row["emergency_relation"], "emergency_phone": row["emergency_phone"],
            "notes": row["notes"], "consented": True, "consented_at": row["consented_at"], "updated_at": row["updated_at"]}


def get_profile(user_id, db_path):
    """پرونده یا None (وجود ندارد / حذف شده)"""
    conn = f2db.connect(db_path)
    row = conn.execute("SELECT * FROM health_profile WHERE user_id=?", (str(user_id),)).fetchone()
    conn.close()
    return _row_to_dict(row) if row and row["consented"] else None


def save_profile(user_id, data, db_path):
    """
    ذخیره/به‌روزرسانی. بدون consented=true → PermissionError('consent').
    consented=false → حذف (tombstone). آخرین updated_at برنده؛ خروجی: پرونده‌ی فعلی یا None.
    """
    data = data or {}
    ts = _ts(data.get("updated_at"))
    conn = f2db.connect(db_path)
    try:
        row = conn.execute("SELECT updated_at FROM health_profile WHERE user_id=?", (str(user_id),)).fetchone()
        if row is not None and ts < row["updated_at"]:
            return get_profile(user_id, db_path)  # نسخه‌ی قدیمی‌تر؛ نادیده گرفته می‌شود
        if data.get("consented") is False or data.get("deleted"):
            _write(conn, str(user_id), False, "", [], [], [], "", "", "", "", ts)
        elif data.get("consented") is True:
            when = f"{schedule.weekday_fa()} {schedule.jalali_date_str()} - {schedule.tehran_now().strftime('%H:%M')}"
            _write(conn, str(user_id), True, str(data.get("consented_at") or when)[:60],
                   clean_list(data.get("allergies")), clean_list(data.get("conditions")), clean_list(data.get("other_meds")),
                   " ".join(str(data.get("emergency_name") or "").split())[:60],
                   " ".join(str(data.get("emergency_relation") or "").split())[:40],
                   clean_phone(data.get("emergency_phone")),
                   str(data.get("notes") or "").strip()[:MAX_NOTES], ts)
        else:
            raise PermissionError("consent")
        conn.commit()
    finally:
        conn.close()
    return get_profile(user_id, db_path)


def _write(conn, uid, consented, consented_at, allergies, conditions, other_meds, name, relation, phone, notes, ts):
    conn.execute(
        """INSERT OR REPLACE INTO health_profile (user_id, consented, consented_at, allergies, conditions, other_meds,
           emergency_name, emergency_relation, emergency_phone, notes, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, 1 if consented else 0, consented_at, json.dumps(allergies, ensure_ascii=False),
         json.dumps(conditions, ensure_ascii=False), json.dumps(other_meds, ensure_ascii=False),
         name, relation, phone, notes, ts))


def delete_profile(user_id, db_path):
    save_profile(user_id, {"consented": False}, db_path)


def current_meds(user_id, db_path):
    """داروهای فعال ثبت‌شده‌ی کاربر (فقط خواندنی؛ برای نمایش در پرونده)"""
    import db
    return [{"name": m[1], "dose": m[3], "times_csv": m[4]} for m in db.get_medications(db_path, user_id)]
