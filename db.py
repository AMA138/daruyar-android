"""
فایل db.py - پایگاه داده SQLite پروژه دارویار
شامل جدول داروهای بیمار و جدول تاریخچه دقیق مصرف برای ارائه به پزشک معالج
"""
import sqlite3
from datetime import datetime

try:
    import jdatetime
except ImportError:
    jdatetime = None

PERSIAN_WEEKDAYS = [
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
    "شنبه",
    "یکشنبه",
]


def get_persian_date_and_day():
    """برگرداندن تاریخ شمسی امروز، نام روز هفته به فارسی و ساعت فعلی"""
    now = datetime.now()
    weekday_name = PERSIAN_WEEKDAYS[now.weekday()]
    if jdatetime:
        j_now = jdatetime.datetime.now()
        date_str = j_now.strftime("%Y/%m/%d")
    else:
        date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    return date_str, weekday_name, time_str


def init_db(db_path="daruyar.db"):
    """ساخت جداول پایگاه داده در صورت عدم وجود"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # ۱. جدول رضایت‌نامه کاربر (حریم خصوصی)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_consent (
            user_id TEXT PRIMARY KEY,
            consented INTEGER NOT NULL DEFAULT 1,
            consented_at TEXT NOT NULL
        )
        """
    )

    # ۲. جدول داروهای فعال بیمار
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            drug_category TEXT NOT NULL,
            dose TEXT NOT NULL,
            times_csv TEXT NOT NULL,
            meal_relation TEXT DEFAULT 'بعد از غذا',
            duration_days INTEGER DEFAULT 30
        )
        """
    )

    # ۳. جدول تاریخچه دقیق مصرف برای پزشک معالج (Medication Administration Record)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            med_name TEXT NOT NULL,
            drug_category TEXT NOT NULL,
            dose TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            actual_time TEXT NOT NULL,
            weekday_name TEXT NOT NULL,
            persian_date TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def set_user_consent(user_id="default_user", db_path="daruyar.db"):
    """ثبت رضایت کاربر در پایگاه داده"""
    init_db(db_path)
    date_str, weekday_name, time_str = get_persian_date_and_day()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO user_consent (user_id, consented, consented_at)
        VALUES (?, 1, ?)
        """,
        (str(user_id), f"{weekday_name} {date_str} - {time_str}"),
    )
    conn.commit()
    conn.close()


def has_user_consented(user_id="default_user", db_path="daruyar.db"):
    """بررسی اینکه آیا کاربر قبلاً دکمه موافقم را زده است یا خیر"""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT consented FROM user_consent WHERE user_id = ?", (str(user_id),)
    )
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def add_medication(
    name,
    drug_category,
    dose,
    times_csv,
    meal_relation="بعد از غذا",
    duration_days=30,
    db_path="daruyar.db",
):
    """افزودن داروی جدید به لیست داروهای بیمار"""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO medications (name, drug_category, dose, times_csv, meal_relation, duration_days)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, drug_category, dose, times_csv, meal_relation, int(duration_days)),
    )
    med_id = cur.lastrowid
    conn.commit()
    conn.close()
    return med_id


def get_medications(db_path="daruyar.db"):
    """دریافت فهرست تمام داروهای ثبت‌شده بیمار"""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, drug_category, dose, times_csv, meal_relation, duration_days
        FROM medications ORDER BY id DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def log_medication_use(
    med_name,
    drug_category,
    dose,
    scheduled_time,
    status,
    custom_date=None,
    custom_weekday=None,
    custom_actual_time=None,
    db_path="daruyar.db",
):
    """ثبت دقیق نوبت مصرف دارو (ساعت، روز هفته، تاریخ شمسی و نوع دارو) برای پزشک معالج"""
    init_db(db_path)
    date_str, weekday_name, actual_time = get_persian_date_and_day()
    if custom_date:
        date_str = custom_date
    if custom_weekday:
        weekday_name = custom_weekday
    if custom_actual_time:
        actual_time = custom_actual_time

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO medication_logs
        (med_name, drug_category, dose, scheduled_time, actual_time, weekday_name, persian_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            med_name,
            drug_category,
            dose,
            scheduled_time,
            actual_time,
            weekday_name,
            date_str,
            status,
        ),
    )
    conn.commit()
    conn.close()


def get_doctor_report(db_path="daruyar.db"):
    """دریافت لیست کامل تاریخچه مصرف دارو برای نمایش به پزشک معالج"""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT med_name, drug_category, dose, weekday_name, persian_date, scheduled_time, actual_time, status
        FROM medication_logs ORDER BY id DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def calculate_adherence_percentage(db_path="daruyar.db"):
    """محاسبه درصد پایبندی بیمار به مصرف دارو برای بالای صفحه گزارش پزشک"""
    rows = get_doctor_report(db_path)
    if not rows:
        return 100.0
    taken_count = sum(1 for r in rows if "مصرف شد" in r[7] or "مصرف کردم" in r[7])
    return round((taken_count / len(rows)) * 100, 1)


def delete_all_user_data(db_path="daruyar.db"):
    """حذف کامل تمامی اطلاعات کاربر (دستور /delete_me)"""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM medications")
    cur.execute("DELETE FROM medication_logs")
    cur.execute("DELETE FROM user_consent")
    conn.commit()
    conn.close()


def insert_sample_demo_data(db_path="daruyar.db"):
    """درج داده‌های نمونه ۷ روزه یک بیمار دیابت و فشار خون برای دموی استاد مولوی"""
    init_db(db_path)
    set_user_consent("default_user", db_path)

    # اگر دارویی ثبت نشده، ۳ داروی اصلی اضافه شود
    if not get_medications(db_path):
        add_medication("متفورمین", "کنترل قند خون (دیابت نوع ۲)", "۵۰۰ میلی‌گرم", "14:00,20:00", "بعد از غذا", 30, db_path)
        add_medication("لوزارتان", "کنترل فشار خون", "۲۵ میلی‌گرم", "08:00,20:00", "همراه غذا", 30, db_path)
        add_medication("آتورواستاتین", "کنترل چربی خون", "۲۰ میلی‌گرم", "22:00", "قبل از خواب", 30, db_path)

    sample_logs = [
        ("متفورمین", "کنترل قند خون", "۵۰۰ میلی‌گرم", "14:00", "✅ مصرف شد (به‌موقع)", "1405/08/10", "یکشنبه", "14:02"),
        ("لوزارتان", "کنترل فشار خون", "۲۵ میلی‌گرم", "20:00", "✅ مصرف شد (به‌موقع)", "1405/08/10", "یکشنبه", "20:00"),
        ("متفورمین", "کنترل قند خون", "۵۰۰ میلی‌گرم", "14:00", "⏳ مصرف با تعویق (۱۰ دقیقه بعد)", "1405/08/11", "دوشنبه", "14:11"),
        ("متفورمین", "کنترل قند خون", "۵۰۰ میلی‌گرم", "17:00", "✅ مصرف شد (به‌موقع)", "1405/08/11", "دوشنبه", "17:01"),
        ("لوزارتان", "کنترل فشار خون", "۲۵ میلی‌گرم", "20:00", "❌ مصرف نشد (نخوردم)", "1405/08/11", "دوشنبه", "—"),
        ("آتورواستاتین", "کنترل چربی خون", "۲۰ میلی‌گرم", "22:00", "✅ مصرف شد (به‌موقع)", "1405/08/12", "سه‌شنبه", "22:03"),
    ]
    for med_name, cat, dose, sched_t, status, p_date, w_day, act_t in sample_logs:
        log_medication_use(med_name, cat, dose, sched_t, status, p_date, w_day, act_t, db_path)