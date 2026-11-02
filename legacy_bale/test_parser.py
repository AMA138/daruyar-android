import med_parser as p

def test_basic_line():
    r = p.extract_medications("متفورمین - ۵۰۰ میلی‌گرم - روزی ۲ بار")
    assert r and r[0]["name"] == "متفورمین" and r[0]["times_per_day"] == 2

def test_ignore_noise():
    assert p.extract_medications("سلام\nنسخه‌ی شما ثبت شد") == []

def test_multi_line():
    r = p.extract_medications("آتنولول: روزی ۱ بار\nآملودیپین: هر ۱۲ ساعت")
    assert [m["times_per_day"] for m in r] == [1, 2]
