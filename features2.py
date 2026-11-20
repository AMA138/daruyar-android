"""
features2.py - مسیریاب قابلیت‌های جدید دارویار (موجودی دارو، یادآوری آب، پرونده‌ی سلامت).
فقط یک تابع به server.py وصل می‌شود: route(method, path, data, user, db_path, query)
  GET  /api/stock            POST /api/stock  {items:[...]} یا یک آیتم   POST /api/stock/consume {med_client_id, units?}
  GET  /api/water[?date=]    POST /api/water  {settings?, logs?, add_ml?}
  GET  /api/health_profile   POST /api/health_profile   POST /api/health_profile/delete
  POST /api/sync2  {stock, water_settings, water_logs, health_profile} ← همگام‌سازی یک‌جای اپ؛ خروجی: وضعیت کامل
خروجی route: (کد HTTP، دیکشنری JSON) یا None اگر مسیر مال این ماژول نیست.
"""
import time
import urllib.parse
import uuid

import f2db
import health_profile
import inventory
import messages
import messages2
import schedule
import water

GET_PATHS = {"/api/stock", "/api/water", "/api/health_profile"}
POST_PATHS = {"/api/stock", "/api/stock/consume", "/api/water", "/api/health_profile",
              "/api/health_profile/delete", "/api/sync2"}


def delete_user_data(user_id, db_path):
    f2db.delete_user_data(user_id, db_path)


def state(user_id, db_path):
    """وضعیت کامل قابلیت‌های جدید برای کلاینت"""
    stock = inventory.list_stock(user_id, db_path)
    return {
        "stock": stock,
        "stock_alerts": [s for s in stock if s["status"] in ("low", "empty")],
        "water": dict(water.overview(user_id, db_path), all_logs=water.list_logs(user_id, db_path)),
        "health_profile": health_profile.get_profile(user_id, db_path),
        "server_time": schedule.utc_str(),
    }


def sync(user_id, data, db_path):
    """ادغام داده‌ی کلاینت (ورودی نامعتبر نادیده گرفته می‌شود، نه خطای کل درخواست)"""
    data = data or {}
    inventory.upsert_stock(user_id, data.get("stock"), db_path, strict=False)
    if isinstance(data.get("water_settings"), dict):
        water.save_settings(user_id, data["water_settings"], db_path, strict=False)
    water.add_logs(user_id, data.get("water_logs"), db_path, strict=False)
    hp = data.get("health_profile")
    if isinstance(hp, dict):
        try:
            health_profile.save_profile(user_id, hp, db_path)
        except (PermissionError, ValueError):
            pass
    return state(user_id, db_path)


def _error(exc):
    """نگاشت خطاهای دامنه به (کد، پیام)"""
    kind = str(exc)
    if isinstance(exc, PermissionError):
        return 403, {"error": messages2.HEALTH_NEEDS_CONSENT}
    if isinstance(exc, LookupError):
        return 404, {"error": messages2.STOCK_NO_ITEM}
    return 400, {"error": {"stock": messages2.STOCK_BAD, "water": messages2.WATER_BAD, "water_log": messages2.WATER_BAD_LOG,
                           "phone": messages2.HEALTH_BAD_PHONE}.get(kind, messages.AUTH_BAD)}


def route(method, path, data, user, db_path, query=""):
    known = GET_PATHS if method == "GET" else POST_PATHS if method == "POST" else ()
    if path not in known:
        return None
    if not user:
        return 401, {"error": messages.AUTH_BAD}
    uid = user["id"]
    data = data if isinstance(data, dict) else {}
    try:
        if method == "GET":
            if path == "/api/stock":
                stock = inventory.list_stock(uid, db_path)
                return 200, {"stock": stock, "alerts": [s for s in stock if s["status"] in ("low", "empty")],
                             "note": messages2.STOCK_NOTE}
            if path == "/api/water":
                date = urllib.parse.parse_qs(query or "").get("date", [None])[0]
                return 200, dict(water.overview(uid, db_path, date), note=messages2.WATER_NOTE)
            return 200, {"health_profile": health_profile.get_profile(uid, db_path),
                         "current_meds": health_profile.current_meds(uid, db_path), "note": messages2.HEALTH_NOTE}

        if path == "/api/sync2":
            return 200, sync(uid, data, db_path)
        if path == "/api/stock":
            items = data["items"] if isinstance(data.get("items"), list) else [data]
            inventory.upsert_stock(uid, items, db_path, strict=True)
            return 200, {"stock": inventory.list_stock(uid, db_path)}
        if path == "/api/stock/consume":
            return 200, {"item": inventory.consume(uid, data.get("med_client_id"), data.get("units"), db_path)}
        if path == "/api/water":
            if isinstance(data.get("settings"), dict):
                water.save_settings(uid, data["settings"], db_path, strict=True)
            logs = list(data.get("logs") or [])
            if "add_ml" in data:  # میان‌بر برای API: ثبت یک نوبت نوشیدن با زمان سرور
                logs.append({"client_id": "api-" + uuid.uuid4().hex[:12], "amount_ml": data["add_ml"]})
            if logs:
                water.add_logs(uid, logs, db_path, strict=True)
            return 200, water.overview(uid, db_path)
        if path == "/api/health_profile":
            profile = health_profile.save_profile(uid, data, db_path)
            return 200, {"health_profile": profile, "message": messages2.HEALTH_SAVED if profile else messages2.HEALTH_DELETED}
        health_profile.delete_profile(uid, db_path)  # /api/health_profile/delete
        return 200, {"ok": True, "message": messages2.HEALTH_DELETED}
    except (ValueError, PermissionError, LookupError) as exc:
        return _error(exc)
