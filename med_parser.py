"""
med_parser.py - بانک داروها (۴ دسته) و استخراج خودکار دارو از متن نسخه/پیام
منبع داده: data/drugs_seed.csv (ستون ATC هنوز توسط نقش ۴ با WHO ATC/DDD تأیید نشده؛ خالی = ندارد/بررسی نشده)
"""
import csv
import os
import re

import config
from schedule import generate_due_times, parse_frequency, to_ascii_digits

GROUPS = {
    "chronic": "داروهای بیماری‌های مزمن",
    "sport": "ورزش و تندرستی",
    "beauty": "آرایشی و بهداشتی (پوست و مو)",
}

_FALLBACK = [
    {"group": "chronic", "name_fa": "متفورمین", "name_en": "Metformin", "atc": "A10BA02",
     "category": "کنترل قند خون (دیابت نوع ۲)", "dose": "۵۰۰ میلی‌گرم", "meal_relation": "همراه با غذا",
     "times": "08:00,20:00", "duration_days": 30},
]


def load_drugs(path=None):
    path = path or config.DRUGS_CSV
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = [dict(r) for r in csv.DictReader(f)]
        for r in rows:
            r["duration_days"] = int(r.get("duration_days") or 30)
        return rows or list(_FALLBACK)
    except (OSError, ValueError, KeyError):
        return list(_FALLBACK)


DRUGS = load_drugs()
# سازگاری با نسخه‌ی قبلی: (نام نمایشی، دسته‌ی درمانی، دوز)
DEFAULT_DRUGS = [(f"{d['name_fa']} ({d['name_en']})", d["category"], d["dose"]) for d in DRUGS]


def _norm(s):
    return to_ascii_digits(s).lower()


def detect_drug_category(med_name):
    """تشخیص خودکار دسته‌ی درمانی دارو برای ثبت در جدول پزشک معالج"""
    for d in DRUGS:
        if d["name_fa"] in med_name or (med_name and med_name in d["name_fa"]):
            return d["category"]
    if "قند" in med_name or "انسولین" in med_name:
        return "کنترل قند خون"
    if "فشار" in med_name:
        return "کنترل فشار خون"
    if "چربی" in med_name or "استاتین" in med_name:
        return "کنترل چربی خون"
    return "داروی عمومی / تجویزی پزشک"


MEAL_KEYWORDS = [
    (r"ناشتا", "ناشتا (۳۰ دقیقه قبل از صبحانه)"),
    (r"بعد\s*از\s*(?:ورزش|تمرین)|پست\s*ورک", "بلافاصله بعد از ورزش (Post-Workout)"),
    (r"قبل\s*از\s*(?:ورزش|تمرین)|پری\s*ورک", "قبل از شروع ورزش (Pre-Workout)"),
    (r"قبل\s*از\s*خواب|شب\s*ها?\s*هنگام\s*خواب|موقع\s*خواب", "قبل از خواب شبانه"),
    (r"قبل\s*از\s*(?:ناهار|شام|غذا)", "قبل از ناهار / شام"),
    (r"بعد\s*از\s*(?:غذا|ناهار|شام|صبحانه)", "بعد از غذا"),
    (r"همراه\s*(?:با\s*)?غذا|با\s*غذا", "همراه با غذا"),
]


def detect_meal_relation(line):
    for pattern, label in MEAL_KEYWORDS:
        if re.search(pattern, line):
            return label
    return None


_DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:میلی\s*‌?گرم|میکروگرم|گرم|میلی\s*‌?لیتر|سی\s*‌?سی|mg|mcg|g|ml|cc|iu|واحد|قطره|اسکوپ|عدد|قرص|کپسول))",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def _first_word(d):
    return _norm(d["name_fa"].split()[0])


def _find_drug(line_norm):
    """بلندترین تطابق: نام کامل فارسی، نام انگلیسی، یا اولین کلمه‌ی نام (فقط اگر در بانک یکتا باشد)"""
    firsts = [_first_word(d) for d in DRUGS]
    best = None
    for d in DRUGS:
        cands = [_norm(d["name_fa"]), _norm(d["name_en"].split("(")[0].strip())]
        fw = _first_word(d)
        if len(fw) >= 4 and firsts.count(fw) == 1:
            cands.append(fw)
        for cand in cands:
            if cand and cand in line_norm and (best is None or len(cand) > best[0]):
                best = (len(cand), d)
    return best[1] if best else None


def parse_prescription(text):
    """
    استخراج نام دارو، دوز، ساعت مصرف و شرط مصرف از متن نسخه (هر خط یک دارو).
    مثال: 'متفورمین ۵۰۰ میلی‌گرم روزی ۲ بار بعد از غذا' یا 'داروی متفورمین 500mg ساعت 14:00'
    """
    if not text or not text.strip():
        return []
    results = []
    for raw in text.strip().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        line = to_ascii_digits(raw)
        drug = _find_drug(_norm(raw))
        dose_m = _DOSE_RE.search(line)
        time_m = _TIME_RE.findall(line)
        freq = parse_frequency(line, default=0)
        if not (drug or dose_m or time_m):
            continue  # خط بی‌ربط (سلام، توضیحات و ...)

        if time_m:
            times = [f"{int(h):02d}:{m}" for h, m in time_m]
        elif freq:
            times = generate_due_times(freq)
        elif drug:
            times = [t.strip() for t in drug["times"].split(",")]
        else:
            times = ["14:00"]

        if drug:
            name, category, group = drug["name_fa"], drug["category"], drug["group"]
            dose = dose_m.group(1) if dose_m else drug["dose"]
            meal = detect_meal_relation(raw) or drug["meal_relation"]
            duration = drug["duration_days"]
        else:
            cleaned = _TIME_RE.sub("", line).replace("داروی", "").replace("قرص", "").strip()
            words = cleaned.split()
            name = words[0] if words else "داروی ثبت‌شده"
            category, group = detect_drug_category(name), ""
            dose = dose_m.group(1) if dose_m else "۱ عدد"
            meal = detect_meal_relation(raw) or "بعد از غذا"
            duration = 30

        results.append({
            "name": name, "drug_category": category, "group": group, "dose": dose,
            "times_csv": ",".join(times), "meal_relation": meal,
            "duration_days": duration, "known": drug is not None,
        })
    return results


def extract_medications(text):
    """نام قدیمی تابع؛ همان parse_prescription"""
    return parse_prescription(text)
