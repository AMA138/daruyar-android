from datetime import datetime

import schedule as sc


def test_digits():
    assert sc.to_ascii_digits("۱۲:۳۴ ٥") == "12:34 5"


def test_frequency():
    assert sc.parse_frequency("روزی ۳ بار") == 3
    assert sc.parse_frequency("هر ۸ ساعت") == 3
    assert sc.parse_frequency("هر 12 ساعت") == 2
    assert sc.parse_frequency("روزی ۹ بار") == 4
    assert sc.parse_frequency("صبح و شب") == 2
    assert sc.parse_frequency("") == 1
    assert sc.parse_frequency("نامفهوم", default=0) == 0


def test_generate_due_times():
    assert sc.generate_due_times(2) == ["08:00", "20:00"]
    assert len(sc.generate_due_times(4)) == 4
    assert len(sc.generate_due_times(9)) == 4


def test_next_due_wraps_to_tomorrow():
    now = datetime(2026, 11, 10, 21, 0)
    hm, target, diff = sc.next_due(["08:00", "20:00"], now_dt=now)
    assert hm == "08:00" and diff == 11 * 60 and target.day == 11


def test_next_due_ignores_bad_values():
    assert sc.next_due(["25:00", "abc"], now_dt=datetime(2026, 1, 1, 8, 0)) == (None, None, 0)


def test_jalali_conversion():
    assert sc.gregorian_to_jalali(2026, 11, 10) == (1405, 8, 19)
    assert sc.gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)


def test_notification_text_has_condition_tag():
    now = datetime(2026, 11, 10, 6, 0)
    t = sc.get_notification_bar_text("متفورمین", "قند", "08:00", "1405/08/19", "سه‌شنبه", now_dt=now,
                                      meal_relation="ناشتا (۳۰ دقیقه قبل از صبحانه)")
    assert "ناشتا" in t and "2 ساعت دیگر" in t and "1405/08/19" in t


def test_format_remaining():
    assert "هم‌اکنون" in sc.format_remaining_time(0)
    assert sc.format_remaining_time(75) == "1 ساعت و 15 دقیقه دیگر"
