"""config.py - تنظیمات از متغیرهای محیطی و فایل .env (بدون وابستگی خارجی؛ سازگار با Pydroid 3)"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.environ.get("DARUYAR_DB", os.path.join(BASE_DIR, "daruyar.db"))
# پیش‌فرض امن: فقط همین دستگاه. برای اتصال گوشی در شبکه‌ی مورد اعتماد: DARUYAR_HOST=0.0.0.0
HOST = os.environ.get("DARUYAR_HOST", "127.0.0.1")
PORT = int(os.environ.get("DARUYAR_PORT", "8765"))
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_API_BASE = os.environ.get("BALE_API_BASE", "https://tapi.bale.ai")
BALE_BOT_USERNAME = os.environ.get("BALE_BOT_USERNAME", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
DRUGS_CSV = os.path.join(BASE_DIR, "data", "drugs_seed.csv")


def _flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


# وب‌هوک بدون WEBHOOK_SECRET فقط با این گزینه‌ی صریح (و فقط برای آزمایش محلی) پذیرفته می‌شود
ALLOW_OPEN_WEBHOOK = _flag("DARUYAR_ALLOW_OPEN_WEBHOOK")
# مبدأهای مجاز برای CORS (جداشده با ویرگول). مبدأ «null» (WebView اپ اندروید با file://) همیشه مجاز است.
CORS_ORIGINS = tuple(o.strip() for o in os.environ.get("DARUYAR_CORS_ORIGINS", "").split(",") if o.strip())
# فقط وقتی سرور واقعاً پشت HTTPS است (مثلاً reverse proxy) روشن شود؛ HSTS را فعال می‌کند
BEHIND_HTTPS = _flag("DARUYAR_BEHIND_HTTPS")
# فقط وقتی پشت یک reverse proxy مورد اعتماد هستید: آدرس کلاینت از آخرین مقدار X-Forwarded-For خوانده می‌شود
TRUST_PROXY = _flag("DARUYAR_TRUST_PROXY")
