"""
tools/build_assets.py - ساخت android/assets/index.html (HTML برنامه با فهرست داروها و تنظیمات جاسازی‌شده).
APK آفلاین-محور است: داده‌ها روی گوشی می‌ماند و با آدرس سرور تنظیم‌شده در برنامه همگام می‌شود.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server  # noqa: E402


def main():
    out = os.path.join(ROOT, "android", "assets")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(server.render_index())
    print("android/assets/index.html ساخته شد.")


if __name__ == "__main__":
    main()
