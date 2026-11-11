import med_parser as mp


def test_bank_has_three_groups():
    assert {d["group"] for d in mp.DRUGS} == set(mp.GROUPS)
    assert len(mp.DRUGS) >= 30
    assert all(d["meal_relation"] for d in mp.DRUGS)


def test_parse_with_frequency_and_meal():
    r = mp.parse_prescription("متفورمین ۵۰۰ میلی‌گرم روزی ۲ بار بعد از غذا")[0]
    assert r["name"] == "متفورمین" and r["times_csv"] == "08:00,20:00" and r["meal_relation"] == "بعد از غذا"
    assert r["group"] == "chronic" and r["known"]


def test_parse_sport_and_conditions():
    r = mp.parse_prescription("کراتین ۵ گرم قبل از ورزش")[0]
    assert r["group"] == "sport" and "Pre-Workout" in r["meal_relation"]
    r = mp.parse_prescription("لووتیروکسین ناشتا")[0]
    assert "ناشتا" in r["meal_relation"]


def test_explicit_time_wins_and_unknown_drug_kept():
    r = mp.parse_prescription("داروی ایکس 10mg ساعت 14:00")[0]
    assert r["times_csv"] == "14:00" and not r["known"]


def test_noise_and_empty():
    assert mp.parse_prescription("") == []
    assert mp.parse_prescription("سلام وقت بخیر") == []


def test_category_detection():
    assert "قند" in mp.detect_drug_category("متفورمین")
    assert mp.detect_drug_category("چیز ناشناخته") == "داروی عمومی / تجویزی پزشک"
