"""
فایل schedule.py - موتور زمان‌بندی و محاسبه زمان باقی‌مانده برای نوار اعلان بالای گوشی
"""
from datetime import datetime, timedelta


def next_due(times_list, now_dt=None):
    """
    محاسبه نزدیک‌ترین زمان بعدی مصرف دارو از روی لیست ساعت‌ها (مثلاً ['08:00', '14:00', '20:00'])
    برمی‌گرداند: (ساعت_هدف به رشته، زمان_دقیق_هدف به datetime، دقیقه_باقی‌مانده)
    """
    if now_dt is None:
        now_dt = datetime.now()

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
            diff_minutes = int((target - now_dt).total_seconds() // 60)
            candidates.append((diff_minutes, f"{h:02d}:{m:02d}", target))
        except (ValueError, IndexError):
            continue

    if not candidates:
        return None, None, 0

    candidates.sort(key=lambda x: x[0])
    best_diff, best_time_str, best_target_dt = candidates[0]
    return best_time_str, best_target_dt, best_diff


def format_remaining_time(total_minutes):
    """تبدیل دقیقه باقی‌مانده به متن فارسی ساعت و دقیقه"""
    if total_minutes <= 0:
        return "هم‌اکنون وقت مصرف دارو است!"
    hours = total_minutes // 60
    mins = total_minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours} ساعت و {mins} دقیقه دیگر"
    elif hours > 0:
        return f"{hours} ساعت دیگر"
    else:
        return f"{mins} دقیقه دیگر"


def get_notification_bar_text(
    med_name, drug_category, scheduled_hm, persian_date_str, weekday_name, now_dt=None
):
    """
    تولید متن کامل نوار اعلان دائمی بالای گوشی (Persistent Notification Bar)
    شامل: تاریخ شمسی روز + نام و نوع دارو + زمان باقی‌مانده تا مصرف
    """
    _, _, diff_mins = next_due([scheduled_hm], now_dt=now_dt)
    rem_text = format_remaining_time(diff_mins)
    return (
        f"📅 امروز: {weekday_name} {persian_date_str}  |  "
        f"💊 داروی بعدی: {med_name} ({drug_category})  |  "
        f"⏱ زمان باقی‌مانده: {rem_text} (ساعت {scheduled_hm})"
    )