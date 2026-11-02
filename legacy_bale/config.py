"""تنظیمات برنامه. مقادیر از متغیرهای محیطی (یا فایل .env) خوانده می‌شوند."""
import os

TOKEN = os.getenv("BALE_BOT_TOKEN", "")
# آدرس API بله؛ در هفته‌ی ۲ با مستندات رسمی بله تطبیق داده شود.
BASE_URL = os.getenv("BALE_API_BASE", "https://tapi.bale.ai")
DB_PATH = os.getenv("DARUYAR_DB", "daruyar.db")
TZ_NAME = "Asia/Tehran"
POLL_TIMEOUT = 25          # ثانیه‌ی انتظار در getUpdates
WORKER_INTERVAL = 30       # ثانیه بین هر بررسی یادآورها
SNOOZE_MINUTES = 10
