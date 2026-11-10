"""
schedule.py - موتور زمان‌بندی (منطقه‌ی زمانی تهران UTC+3:30) و متن نوار اعلان
فقط کتابخانه‌ی استاندارد پایتون؛ روی ویندوز و Pydroid 3 اجرا می‌شود (بدون jdatetime).
"""
import re
from datetime import datetime, timedelta, timezone

TEHRAN_OFFSET = timedelta(hours=3, minutes=30)  # ایران از ۱۴۰۱ ساعت تابستانی ندارد
PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]  # weekday(): دوشنبه=۰

_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})

DEFAULT_TIMES = {
    1: ["08:00"],
    2: ["08:00", "20:00"],
    3: ["08:00", "14:00", "20:00"],
    4: ["07:00", "12:00", "17:00", "22:00"],
}


def to_ascii_digits(text):
    """تبدیل ارقام فارسی و عربی به ۰-۹ انگلیسی"""
    return str(text).translate(_DIGITS)


def now_utc():
    return datetime.now(timezone.utc)


def utc_str(dt=None):
    return (dt or now_utc()).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def tehran_now():
    """زمان فعلی تهران (datetime ساده، بدون tzinfo)"""
    return (now_utc() + TEHRAN_OFFSET).replace(tzinfo=None)


def gregorian_to_jalali(gy, gm, gd):
    """تبدیل تاریخ میلادی به شمسی بدون کتابخانه‌ی خارجی"""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_date_str(dt=None):
    dt = dt or tehran_now()
    return "%04d/%02d/%02d" % gregorian_to_jalali(dt.year, dt.month, dt.day)


def weekday_fa(dt=None):
    return PERSIAN_WEEKDAYS[(dt or tehran_now()).weekday()]


_WORD_NUM = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4}


def parse_frequency(text, default=1):
    """
    تبدیل عبارت دفعات مصرف به عدد ۱ تا ۴. مثال: «روزی ۳ بار» → ۳ ، «هر ۸ ساعت» → ۳
    اگر عبارت شناسایی نشد، default برمی‌گردد.
    """
    t = to_ascii_digits(text or "").lower().strip()
    if not t:
        return default
    m = re.search(r"هر\s*(\d+)\s*ساعت", t)
    if m and int(m.group(1)) > 0:
        return max(1, min(4, round(24 / int(m.group(1)))))
    m = re.search(r"(\d+)\s*(?:بار|مرتبه|نوبت|times|x)", t) or re.search(r"روزی\s*(\d+)", t)
    if m:
        return max(1, min(4, int(m.group(1))))
    for word, n in _WORD_NUM.items():
        if re.search(rf"{word}\s*(?:بار|مرتبه|نوبت)", t):
            return n
    if "صبح و شب" in t or "صبح و عصر" in t:
        return 2
    for key, n in (("qid", 4), ("tid", 3), ("bid", 2), ("qd", 1), ("daily", 1)):
        if re.search(rf"\b{key}\b", t):
            return n
    return default


def generate_due_times(freq):
    """ساعت‌های پیش‌فرض مصرف برای n بار در روز (۱ تا ۴)"""
    return list(DEFAULT_TIMES[max(1, min(4, int(freq)))])


def next_due(times_list, now_dt=None):
    """
    نزدیک‌ترین زمان بعدی مصرف از روی لیست ساعت‌ها (مثلاً ['08:00', '14:00'])
    برمی‌گرداند: (ساعت هدف به رشته، datetime هدف، دقیقه‌ی باقی‌مانده)
    """
    if now_dt is None:
        now_dt = tehran_now()
    if isinstance(times_list, str):
        times_list = [t.strip() for t in times_list.split(",") if t.strip()]
    if not times_list:
        return None, None, 0

    candidates = []
    for t_str in times_list:
        try:
            parts = t_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                continue
            target = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now_dt:
                target += timedelta(days=1)
            diff = int((target - now_dt).total_seconds() // 60)
            candidates.append((diff, f"{h:02d}:{m:02d}", target))
        except (ValueError, IndexError):
            continue
    if not candidates:
        return None, None, 0
    candidates.sort(key=lambda x: x[0])
    diff, hm, target = candidates[0]
    return hm, target, diff


def format_remaining_time(total_minutes):
    """تبدیل دقیقه‌ی باقی‌مانده به متن فارسی ساعت و دقیقه"""
    if total_minutes <= 0:
        return "هم‌اکنون وقت مصرف دارو است!"
    hours, mins = divmod(total_minutes, 60)
    if hours > 0 and mins > 0:
        return f"{hours} ساعت و {mins} دقیقه دیگر"
    if hours > 0:
        return f"{hours} ساعت دیگر"
    return f"{mins} دقیقه دیگر"


def get_notification_bar_text(
    med_name, drug_category, scheduled_hm, persian_date_str, weekday_name, now_dt=None, meal_relation=None
):
    """متن کامل نوار اعلان: تاریخ شمسی + نام و نوع دارو + (شرط مصرف) + زمان باقی‌مانده"""
    _, _, diff = next_due([scheduled_hm], now_dt=now_dt)
    parts = [
        f"📅 امروز: {weekday_name} {persian_date_str}",
        f"💊 داروی بعدی: {med_name} ({drug_category})",
    ]
    if meal_relation:
        parts.append(f"🍽 شرط مصرف: {meal_relation}")
    parts.append(f"⏱ زمان باقی‌مانده: {format_remaining_time(diff)} (ساعت {scheduled_hm})")
    return "  |  ".join(parts)
