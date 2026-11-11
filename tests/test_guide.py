import re
import shutil
import subprocess

import messages
import server


def _html():
    return server.render_index()


def _tour_text(html):
    block = html[html.index("const TOUR = ["):html.index("function openGuide")]
    return block


def test_guide_covers_every_feature():
    t = _tour_text(_html())
    for word in ("ادامه بدون سرور", "آدرس سرور", "همگام‌سازی", "مصرف کردم", "۱۰ دقیقه بعد", "نخوردم",
                 "داده‌ی نمونه", "ثبت دارو", "شرایط مصرف", "دفعات مصرف", "نسخه‌ی الکترونیک", "استخراج",
                 "کد اتصال", "/link", "پایبندی", "MAR", "چاپ گزارش", "پروفایل", "بیداری", "ناهار", "شام",
                 "نوتیفیکیشن", "تنظیمات", "حذف همه‌ی اطلاعات من", "خروج"):
        assert word in t, word


def test_guide_has_entry_points_and_first_run():
    h = _html()
    assert "openGuide(0)" in h and "❓ راهنما" in h          # هدر
    assert "دیدن آموزش" in h                                  # تب پروفایل
    assert "آموزش استفاده از دارویار" in h                    # صفحه‌ی ورود
    assert "!st.tourDone" in h and "st.tourDone = true" in h  # نمایش خودکار بار اول


def test_guide_keeps_safety_and_honesty_notes():
    t = _tour_text(_html())
    assert "توصیه‌ی پزشکی" in t
    assert "بازبینی نشده" in t          # بانک دارو هنوز بازبینی داروساز ندارد
    assert "آزمایش نشده" in t           # بات بله هنوز با API واقعی آزمایش نشده


def test_whole_page_has_no_forbidden_medical_phrases():
    h = _html()
    for phrase in messages.FORBIDDEN_MEDICAL_TERMS:
        assert phrase not in h, phrase


def test_page_script_is_valid_javascript():
    if not shutil.which("node"):
        return  # در GitHub Actions (ubuntu) node موجود است
    scripts = re.findall(r"<script>(.*?)</script>", _html(), re.S)
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        open_path = os.path.join(d, "page.js")
        with open(open_path, "w", encoding="utf-8") as f:
            f.write(scripts[-1])
        r = subprocess.run(["node", "--check", open_path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
