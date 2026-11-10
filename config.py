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
HOST = os.environ.get("DARUYAR_HOST", "0.0.0.0")
PORT = int(os.environ.get("DARUYAR_PORT", "8765"))
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_API_BASE = os.environ.get("BALE_API_BASE", "https://tapi.bale.ai")
BALE_BOT_USERNAME = os.environ.get("BALE_BOT_USERNAME", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
DRUGS_CSV = os.path.join(BASE_DIR, "data", "drugs_seed.csv")
