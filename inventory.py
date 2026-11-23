"""
inventory.py - مدیریت موجودی دارو: ثبت تعداد موجود، کاهش با هر نوبت مصرف، هشدار نزدیک‌شدن به اتمام.
کلید هر ردیف = client_id داروی ثبت‌شده در جدول medications (همان که /api/sync می‌سازد).
ادغام داده‌ی کلاینت: آخرین updated_at برنده است (مثل داروها).
"""
import math
import re
import time

import db
import f2db
import messages2
from schedule import to_ascii_digits

DEFAULT_UNIT = "عدد"
DEFAULT_LOW_DAYS = 5
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _num(value, lo, hi):
    """عدد در بازه‌ی [lo, hi]؛ در غیر این صورت ValueError('stock')"""
    try:
        n = float(to_ascii_digits(value).replace("٫", ".").replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError("stock")
    if math.isnan(n) or math.isinf(n) or not (lo <= n <= hi):
        raise ValueError("stock")
    return n


def _clean(item):
    """یک ورودی را تمیز و اعتبارسنجی می‌کند؛ ValueError('stock') برای مقدار نامعتبر"""
    mid = db.clean_id(item.get("med_client_id"))
    if not mid:
        raise ValueError("stock")
    return {
        "med_client_id": mid,
        "quantity": _num(item.get("quantity", 0), 0, 100000),
        "units_per_dose": _num(item.get("units_per_dose", 1), 0.25, 100),
        "unit": (str(item.get("unit") or DEFAULT_UNIT).strip() or DEFAULT_UNIT)[:20],
        "low_days": int(_num(item.get("low_days", DEFAULT_LOW_DAYS), 1, 60)),
        "deleted": 1 if item.get("deleted") else 0,
        "updated_at": db._i(item.get("updated_at"), 1, db.INT_MAX, int(time.time() * 1000)),
    }


def doses_per_day(times_csv):
    """تعداد ساعت‌های معتبر مصرف در روز (حداقل ۱)"""
    n = sum(1 for t in str(times_csv or "").split(",") if _TIME_RE.match(t.strip()))
    return n or 1


def status_for(quantity, units_per_dose, low_days, times_csv, name=""):
    """
    وضعیت موجودی: {days_left, status: ok|low|empty, message}
    days_left = موجودی ÷ (مصرف هر نوبت × تعداد نوبت در روز)، گردشده به پایین.
    """
    per_day = units_per_dose * doses_per_day(times_csv)
    days = int(math.floor(quantity / per_day + 1e-9)) if per_day > 0 else 0
    if quantity < units_per_dose:
        return {"days_left": 0, "status": "empty", "message": messages2.STOCK_EMPTY.format(name=name)}
    if days <= low_days:
        return {"days_left": days, "status": "low", "message": messages2.STOCK_LOW.format(name=name, days=days)}
    return {"days_left": days, "status": "ok", "message": ""}


def upsert_stock(user_id, items, db_path, strict=False):
    """
    ادغام موجودی‌ها. strict=True (اندپوینت مستقیم): ورودی نامعتبر ValueError('stock') می‌دهد.
    strict=False (همگام‌سازی): ورودی نامعتبر رد می‌شود و بقیه ذخیره می‌شوند. خروجی: تعداد ردیف‌های پذیرفته‌شده.
    """
    conn = f2db.connect(db_path)
    accepted = 0
    try:
        for raw in items or []:
            if not isinstance(raw, dict):
                if strict:
                    raise ValueError("stock")
                continue
            try:
                it = _clean(raw)
            except ValueError:
                if strict:
                    raise
                continue
            row = conn.execute("SELECT updated_at FROM med_stock WHERE user_id=? AND med_client_id=?",
                               (str(user_id), it["med_client_id"])).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO med_stock (user_id, med_client_id, quantity, units_per_dose, unit, low_days, deleted, updated_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (str(user_id), it["med_client_id"], it["quantity"], it["units_per_dose"], it["unit"],
                     it["low_days"], it["deleted"], it["updated_at"]))
            elif it["updated_at"] >= row["updated_at"]:
                conn.execute(
                    """UPDATE med_stock SET quantity=?, units_per_dose=?, unit=?, low_days=?, deleted=?, updated_at=?
                       WHERE user_id=? AND med_client_id=?""",
                    (it["quantity"], it["units_per_dose"], it["unit"], it["low_days"], it["deleted"], it["updated_at"],
                     str(user_id), it["med_client_id"]))
            accepted += 1
        conn.commit()
    finally:
        conn.close()
    return accepted


def list_stock(user_id, db_path):
    """همه‌ی ردیف‌های موجودی؛ برای داروهای فعال، وضعیت و پیام هشدار هم محاسبه می‌شود"""
    conn = f2db.connect(db_path)
    rows = conn.execute(
        """SELECT s.med_client_id, s.quantity, s.units_per_dose, s.unit, s.low_days, s.deleted, s.updated_at,
                  m.name AS med_name, m.times_csv AS times_csv, COALESCE(m.deleted, 1) AS med_deleted
           FROM med_stock s LEFT JOIN medications m ON m.user_id = s.user_id AND m.client_id = s.med_client_id
           WHERE s.user_id=? ORDER BY s.updated_at""", (str(user_id),)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = {k: r[k] for k in ("med_client_id", "quantity", "units_per_dose", "unit", "low_days", "deleted", "updated_at")}
        d["med_name"] = r["med_name"] or ""
        if not r["deleted"] and not r["med_deleted"]:
            d.update(status_for(r["quantity"], r["units_per_dose"], r["low_days"], r["times_csv"], r["med_name"]))
        else:
            d.update({"days_left": None, "status": "inactive", "message": ""})
        out.append(d)
    return out


def alerts(user_id, db_path):
    """فقط ردیف‌هایی که کم یا تمام‌شده‌اند"""
    return [s for s in list_stock(user_id, db_path) if s["status"] in ("low", "empty")]


def consume(user_id, med_client_id, units, db_path):
    """کم‌کردن موجودی (پیش‌فرض: تعداد مصرف هر نوبت). LookupError اگر موجودی ثبت نشده باشد."""
    conn = f2db.connect(db_path)
    try:
        row = conn.execute("SELECT quantity, units_per_dose FROM med_stock WHERE user_id=? AND med_client_id=? AND deleted=0",
                           (str(user_id), str(med_client_id))).fetchone()
        if row is None:
            raise LookupError("stock")
        amount = row["units_per_dose"] if units in (None, "") else _num(units, 0.01, 100000)
        conn.execute("UPDATE med_stock SET quantity=?, updated_at=? WHERE user_id=? AND med_client_id=?",
                     (max(0.0, row["quantity"] - amount), int(time.time() * 1000), str(user_id), str(med_client_id)))
        conn.commit()
    finally:
        conn.close()
    return next(s for s in list_stock(user_id, db_path) if s["med_client_id"] == str(med_client_id))
