"""
فایل med_parser.py - فهرست داروها و استخراج خودکار دارو از متن پیامک نسخه بیمه
"""
import re

# فهرست پیش‌فرض داروهای پرمصرف دیابت نوع ۲، فشار خون و چربی خون به همراه نوع درمانی برای گزارش پزشک
DEFAULT_DRUGS = [
    ("متفورمین (Metformin)", "کنترل قند خون (دیابت نوع ۲)", "۵۰۰ میلی‌گرم"),
    ("گلی‌بن‌کلامید (Glibenclamide)", "کنترل قند خون (دیابت نوع ۲)", "۵ میلی‌گرم"),
    ("سیتاگلیپتین (Sitagliptin)", "کنترل قند خون (دیابت نوع ۲)", "۵۰ میلی‌گرم"),
    ("امپاگلیفلوزین (Empagliflozin)", "کنترل قند خون (دیابت نوع ۲)", "۱۰ میلی‌گرم"),
    ("لوزارتان (Losartan)", "کنترل فشار خون", "۲۵ میلی‌گرم"),
    ("والسارتان (Valsartan)", "کنترل فشار خون", "۸۰ میلی‌گرم"),
    ("آملودیپین (Amlodipine)", "کنترل فشار خون", "۵ میلی‌گرم"),
    ("متوپرولول (Metoprolol)", "کنترل فشار خون و ضربان قلب", "۵۰ میلی‌گرم"),
    ("کاپتوپریل (Captopril)", "کنترل فشار خون", "۲۵ میلی‌گرم"),
    ("آتورواستاتین (Atorvastatin)", "کنترل چربی خون (کلسترول)", "۲۰ میلی‌گرم"),
    ("رزوواستاتین (Rosuvastatin)", "کنترل چربی خون (کلسترول)", "۱۰ میلی‌گرم"),
    ("آسپرین ۸۰ (ASA)", "پیشگیری قلبی-عروقی", "۸۰ میلی‌گرم"),
]


def detect_drug_category(med_name):
    """تشخیص خودکار نوع/دسته درمانی دارو برای ثبت در جدول پزشک معالج"""
    for name, category, _ in DEFAULT_DRUGS:
        clean_fa = name.split("(")[0].strip()
        if clean_fa in med_name or med_name in clean_fa:
            return category
    if "قند" in med_name or "متفورمین" in med_name or "انسولین" in med_name:
        return "کنترل قند خون"
    if "فشار" in med_name or "لوزارتان" in med_name or "آملودیپین" in med_name:
        return "کنترل فشار خون"
    if "چربی" in med_name or "استاتین" in med_name:
        return "کنترل چربی خون"
    return "داروی عمومی / تجویزی پزشک"


def parse_prescription(text):
    """
    استخراج نام دارو، دوز و ساعت مصرف از متن کپی‌شده یا فورواردشده پیامک نسخه بیمه
    مثال ورودی: 'داروی متفورمین ۵۰۰ میلی‌گرم ساعت 14:00'
    """
    if not text or not text.strip():
        return []

    results = []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    for line in lines:
        # جستجوی ساعت در متن (مثلاً 14:00 یا 08:30)
        time_matches = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", line)
        times_csv = (
            ",".join([f"{int(h):02d}:{m}" for h, m in time_matches])
            if time_matches
            else "14:00"
        )

        # جستجوی دوز (مثلاً ۵۰۰ میلی‌گرم یا ۲۵mg)
        dose_match = re.search(
            r"(\d+\s*(?:میلی‌گرم|میلی گرم|mg|سی‌سی|عدد|قرص))", line, re.IGNORECASE
        )
        dose = dose_match.group(1) if dose_match else "۱ عدد"

        # تشخیص نام دارو از لیست استاندارد یا کلمات خط
        found_name = None
        for d_name, _, _ in DEFAULT_DRUGS:
            fa_part = d_name.split("(")[0].strip()
            if fa_part in line:
                found_name = fa_part
                break

        if not found_name:
            cleaned = re.sub(r"(\b\d{1,2}:\d{2}\b)", "", line)
            cleaned = cleaned.replace("داروی", "").replace("قرص", "").strip()
            words = cleaned.split()
            found_name = words[0] if words else "داروی ثبت‌شده"

        category = detect_drug_category(found_name)
        results.append(
            {
                "name": found_name,
                "drug_category": category,
                "dose": dose,
                "times_csv": times_csv,
            }
        )

    return results