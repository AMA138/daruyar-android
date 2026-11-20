"""
f2db.py - جدول‌ها و اتصال SQLite قابلیت‌های جدید (موجودی، آب، پرونده‌ی سلامت).
فقط کتابخانه‌ی استاندارد. جدول‌ها اولین بار که استفاده شوند ساخته می‌شوند (نیازی به تغییر db.init_db نیست).
"""
import sqlite3

import db

_READY = set()

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS med_stock (
        user_id TEXT NOT NULL, med_client_id TEXT NOT NULL, quantity REAL NOT NULL DEFAULT 0,
        units_per_dose REAL NOT NULL DEFAULT 1, unit TEXT NOT NULL DEFAULT 'عدد',
        low_days INTEGER NOT NULL DEFAULT 5, deleted INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, med_client_id))""",
    """CREATE TABLE IF NOT EXISTS water_settings (
        user_id TEXT PRIMARY KEY, goal_ml INTEGER NOT NULL, glass_ml INTEGER NOT NULL,
        start_time TEXT NOT NULL, end_time TEXT NOT NULL, interval_min INTEGER NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS water_logs (
        user_id TEXT NOT NULL, client_id TEXT NOT NULL, persian_date TEXT NOT NULL, time_hm TEXT NOT NULL,
        amount_ml INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, client_id))""",
    """CREATE TABLE IF NOT EXISTS health_profile (
        user_id TEXT PRIMARY KEY, consented INTEGER NOT NULL DEFAULT 0, consented_at TEXT NOT NULL DEFAULT '',
        allergies TEXT NOT NULL DEFAULT '[]', conditions TEXT NOT NULL DEFAULT '[]', other_meds TEXT NOT NULL DEFAULT '[]',
        emergency_name TEXT NOT NULL DEFAULT '', emergency_relation TEXT NOT NULL DEFAULT '',
        emergency_phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT 0)""",
]


def connect(db_path="daruyar.db"):
    if db_path not in _READY:
        db.init_db(db_path)
        conn = sqlite3.connect(db_path)
        for ddl in SCHEMA:
            conn.execute(ddl)
        conn.commit()
        conn.close()
        _READY.add(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def delete_user_data(user_id, db_path="daruyar.db"):
    """حذف کامل داده‌های جدید یک کاربر (از db.delete_user_data صدا زده می‌شود)"""
    conn = connect(db_path)
    for table in ("med_stock", "water_settings", "water_logs", "health_profile"):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()
