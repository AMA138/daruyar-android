from datetime import date, timezone
import schedule as s

def test_persian_digits():
    assert s.to_ascii_digits("روزی ۳ بار") == "روزی 3 بار"

def test_freq_roozi():
    assert s.parse_frequency("روزی ۳ بار") == 3
    assert s.parse_frequency("روزی 2 بار قبل از غذا") == 2

def test_freq_har_saat():
    assert s.parse_frequency("هر ۸ ساعت") == 3
    assert s.parse_frequency("هر ۱۲ ساعت") == 2
    assert s.parse_frequency("هر ۶ ساعت") == 4

def test_freq_invalid():
    assert s.parse_frequency("هر ۷ ساعت") is None
    assert s.parse_frequency("هر روز") is None
    assert s.parse_frequency("روزی ۹ بار") is None

def test_generate_count_and_order():
    ev = s.generate_due_times(date(2026, 11, 1), 2, s.DEFAULT_TIMES[3])
    assert len(ev) == 6 and ev == sorted(ev)

def test_timezone_conversion():
    ev = s.generate_due_times(date(2026, 11, 1), 1, ["08:00"])
    assert ev[0].astimezone(timezone.utc).strftime("%H:%M") == "04:30"  # تهران = UTC+3:30 (بدون ساعت تابستانی)

def test_utc_str_fixed_length():
    ev = s.generate_due_times(date(2026, 11, 1), 1, ["08:00"])
    assert len(s.utc_str(ev[0])) == 19
