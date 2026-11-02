"""
فایل app_ui.py - رابط گرافیکی کامل اپلیکیشن اندروید دارویار (سازگار با Python 3.14 و ویندوز)
متصل به: db.py (دیتابیس پزشک)، schedule.py (نوار اعلان)، messages.py و med_parser.py
"""
import urllib.parse
import webbrowser
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

import db
import schedule
import messages
import med_parser

PORT = 8765
LAST_MESSAGE = "اپلیکیشن دارویار آماده است. برای تست سریع، دکمه طلایی «درج داده نمونه ۷ روزه برای دمو استاد» را بزنید."


def build_html_page():
    db.init_db()
    p_date, w_day, now_hm = db.get_persian_date_and_day()
    meds = db.get_medications()

    if meds:
        first_med = meds[0]
        m_name, m_cat, m_dose, m_times = first_med[1], first_med[2], first_med[3], first_med[4]
        best_t, _, _ = schedule.next_due(m_times)
        target_hm = best_t if best_t else "14:00"
        bar_str = schedule.get_notification_bar_text(m_name, m_cat, target_hm, p_date, w_day)
    else:
        bar_str = f"📅 امروز: {w_day} {p_date} (ساعت {now_hm}) | 💊 هنوز دارویی ثبت نشده است (از فرم زیر اضافه کنید)"

    adh = db.calculate_adherence_percentage()
    consented = db.has_user_consented()
    consent_badge = "✅ رضایت‌نامه ثبت شده است" if consented else "⚠️ در انتظار تأیید رضایت‌نامه"

    # ساخت ردیف‌های جدول گزارش پزشک معالج
    logs = db.get_doctor_report()
    logs_html = ""
    if not logs:
        logs_html = """
        <tr>
            <td colspan="7" style="text-align:center; padding:18px; color:#64748B;">
                هنوز رکوردی ثبت نشده است. روی دکمه طلایی <b>«⚡ درج داده نمونه ۷ روزه برای دمو استاد»</b> کلیک کنید!
            </td>
        </tr>
        """
    else:
        for idx, row in enumerate(logs, start=1):
            med_n, cat, dose, w_name, p_d, sched_t, act_t, stat = row
            if "مصرف شد" in stat:
                row_bg = "#F0FDF4"
                badge_color = "#15803D"
            elif "تعویق" in stat:
                row_bg = "#FEFCE8"
                badge_color = "#B45309"
            else:
                row_bg = "#FEF2F2"
                badge_color = "#B91C1C"

            logs_html += f"""
            <tr style="background:{row_bg}; border-bottom:1px solid #E2E8F0;">
                <td style="padding:8px; text-align:center; font-weight:bold;">{idx}</td>
                <td style="padding:8px; font-weight:bold; color:#0F172A;">{med_n}<br><span style="font-size:11px; color:#475569;">{dose}</span></td>
                <td style="padding:8px; color:#0F766E; font-weight:bold;">{cat}</td>
                <td style="padding:8px; text-align:center;">{w_name}<br><span style="font-size:11px; color:#475569;">{p_d}</span></td>
                <td style="padding:8px; text-align:center; font-weight:bold;">{sched_t}</td>
                <td style="padding:8px; text-align:center; color:#1E40AF; font-weight:bold;">{act_t}</td>
                <td style="padding:8px; color:{badge_color}; font-weight:bold;">{stat}</td>
            </tr>
            """

    # فهرست داروهای فعال بیمار
    meds_html = ""
    if meds:
        for m in meds:
            meds_html += f"<span style='display:inline-block; background:#E0F2FE; color:#0369A1; padding:4px 10px; border-radius:20px; font-size:12px; margin:3px;'>💊 {m[1]} ({m[2]}) - ساعت {m[4]}</span>"
    else:
        meds_html = "<span style='font-size:12px; color:#64748B;'>هنوز دارویی ثبت نشده است.</span>"

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>اپلیکیشن اندروید دارویار - نسخه دمو</title>
    <style>
        body {{
            font-family: Tahoma, 'Vazirmatn', 'B Nazanin', Arial, sans-serif;
            background: #CBD5E1;
            margin: 0;
            padding: 15px;
            display: flex;
            justify-content: center;
        }}
        .phone-frame {{
            width: 520px;
            background: #F8FAFC;
            border-radius: 28px;
            border: 8px solid #1E293B;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .status-bar {{
            background: #091E3A;
            color: #99F6E4;
            padding: 6px 16px;
            font-size: 11px;
            display: flex;
            justify-content: space-between;
        }}
        .notif-bar {{
            background: linear-gradient(135deg, #0F2C59, #1E3A8A);
            color: #FFFFFF;
            padding: 14px 16px;
            border-bottom: 3px solid #0D9488;
        }}
        .notif-title {{
            font-size: 11px;
            color: #5EEAD4;
            margin-bottom: 6px;
        }}
        .notif-main {{
            font-size: 13px;
            font-weight: bold;
            line-height: 1.7;
            background: rgba(255,255,255,0.1);
            padding: 8px 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }}
        .btn-row {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .btn {{
            border: none;
            padding: 8px 12px;
            border-radius: 8px;
            font-family: inherit;
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            color: white;
            text-decoration: none;
            display: inline-block;
        }}
        .btn-green {{ background: #16A34A; }}
        .btn-amber {{ background: #D97706; }}
        .btn-red {{ background: #DC2626; }}
        .btn-blue {{ background: #2563EB; }}
        .btn-teal {{ background: #0D9488; width: 100%; padding: 10px; font-size: 13px; margin-top: 8px; }}
        .btn-gold {{ background: #CA8A04; }}
        .btn-gray {{ background: #64748B; }}
        .content {{
            padding: 14px;
        }}
        .alert-msg {{
            background: #DBEAFE;
            color: #1E3A8A;
            border-right: 4px solid #2563EB;
            padding: 10px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 12px;
        }}
        .card {{
            background: #FFFFFF;
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 14px;
            border: 1px solid #E2E8F0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.04);
        }}
        .card-title {{
            font-size: 14px;
            font-weight: bold;
            color: #0F2C59;
            margin-bottom: 10px;
            border-bottom: 2px solid #F1F5F9;
            padding-bottom: 6px;
        }}
        .form-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}
        label {{
            font-size: 11px;
            color: #475569;
            display: block;
            margin-bottom: 3px;
            font-weight: bold;
        }}
        input, select, textarea {{
            width: 100%;
            padding: 7px;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            font-family: inherit;
            font-size: 12px;
            box-sizing: border-box;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 11.5px;
            margin-top: 8px;
        }}
        th {{
            background: #0F2C59;
            color: white;
            padding: 8px 4px;
            text-align: center;
        }}
        .adh-box {{
            background: #F0FDFA;
            border: 1px solid #99F6E4;
            color: #0F766E;
            padding: 8px 12px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 13px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
    </style>
</head>
<body>
<div class="phone-frame">
    <!-- نوار وضعیت اندروید -->
    <div class="status-bar">
        <span>📱 Android APK | دارویار نسخه ۱.۰</span>
        <span>🔋 ۹۸٪ | 📶 4G | {now_hm}</span>
    </div>

    <!-- ۱. نوار اعلان دائمی در بالای گوشی (درخواستی استاد مولوی) -->
    <div class="notif-bar">
        <div class="notif-title">🔔 نوار اعلان دائمی دارویار در بالای گوشی (Persistent Notification Bar)</div>
        <div class="notif-main">{bar_str}</div>
        <div class="btn-row">
            <form method="POST" action="/action" style="margin:0;">
                <input type="hidden" name="act" value="taken">
                <button type="submit" class="btn btn-green">✅ مصرف کردم</button>
            </form>
            <form method="POST" action="/action" style="margin:0;">
                <input type="hidden" name="act" value="snooze">
                <button type="submit" class="btn btn-amber">⏳ ۱۰ دقیقه بعد</button>
            </form>
            <form method="POST" action="/action" style="margin:0;">
                <input type="hidden" name="act" value="skip">
                <button type="submit" class="btn btn-red">❌ نخوردم</button>
            </form>
        </div>
    </div>

    <div class="content">
        <div class="alert-msg">💡 وضعیت: {LAST_MESSAGE}</div>

        <!-- ۲. کادر رضایت‌نامه و ایمنی پزشکی -->
        <div class="card" style="background:#EFF6FF; border-color:#BFDBFE;">
            <div style="font-size:11.5px; color:#1E3A8A; font-weight:bold; margin-bottom:8px;">
                ⚠️ {messages.DISCLAIMER}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; font-weight:bold; color:#0F172A;">{consent_badge}</span>
                <form method="POST" action="/action" style="margin:0;">
                    <input type="hidden" name="act" value="consent">
                    <button type="submit" class="btn btn-blue">👍 موافقم (ثبت رضایت)</button>
                </form>
            </div>
        </div>

        <!-- ۳. فرم ثبت داروی جدید بیمار -->
        <div class="card">
            <div class="card-title">➕ ثبت داروی جدید بیمار در حافظه برنامه</div>
            <form method="POST" action="/add_med">
                <div class="form-grid">
                    <div>
                        <label>نام دارو:</label>
                        <input type="text" name="name" value="متفورمین" required>
                    </div>
                    <div>
                        <label>نوع دارو (برای گزارش پزشک معالج):</label>
                        <select name="category">
                            <option value="کنترل قند خون (دیابت نوع ۲)">کنترل قند خون (دیابت نوع ۲)</option>
                            <option value="کنترل فشار خون">کنترل فشار خون</option>
                            <option value="کنترل چربی خون">کنترل چربی خون</option>
                            <option value="پیشگیری قلبی-عروقی">پیشگیری قلبی-عروقی</option>
                        </select>
                    </div>
                    <div>
                        <label>دوز مصرفی:</label>
                        <input type="text" name="dose" value="۵۰۰ میلی‌گرم" required>
                    </div>
                    <div>
                        <label>ساعت مصرف (مثلاً 14:00):</label>
                        <input type="text" name="times" value="14:00" required>
                    </div>
                </div>
                <button type="submit" class="btn btn-teal">💾 ذخیره دارو در برنامه و فعال‌سازی نوار اعلان</button>
            </form>
            <div style="margin-top:10px; padding-top:8px; border-top:1px dashed #CBD5E1;">
                <div style="font-size:11px; color:#475569; margin-bottom:4px; font-weight:bold;">داروهای فعال بیمار:</div>
                {meds_html}
            </div>
        </div>

        <!-- ۴. جدول گزارش بالینی برای پزشک معالج (درخواستی استاد مولوی) -->
        <div class="card" style="border: 2px solid #0D9488;">
            <div class="card-title">👨‍⚕️ پرونده و گزارش بالینی مصرف دارو (ویژه ارائه به پزشک معالج)</div>
            <div class="adh-box">
                <span>📊 شاخص پایبندی بیمار به درمان: {adh}٪</span>
                <button onclick="window.print()" class="btn btn-blue" style="padding:4px 8px; font-size:11px;">🖨️ چاپ / PDF برای پزشک</button>
            </div>
            <div class="btn-row" style="margin-bottom:10px;">
                <form method="POST" action="/action" style="margin:0;">
                    <input type="hidden" name="act" value="seed">
                    <button type="submit" class="btn btn-gold">⚡ درج داده نمونه ۷ روزه برای دمو استاد</button>
                </form>
                <form method="POST" action="/action" style="margin:0;">
                    <input type="hidden" name="act" value="clear">
                    <button type="submit" class="btn btn-gray">🗑️ حذف همه اطلاعات (/delete_me)</button>
                </form>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>نام و دوز دارو</th>
                        <th>نوع دارو</th>
                        <th>روز و تاریخ</th>
                        <th>ساعت مقرر</th>
                        <th>ساعت مصرف</th>
                        <th>وضعیت ثبت‌شده</th>
                    </tr>
                </thead>
                <tbody>
                    {logs_html}
                </tbody>
            </table>
        </div>
    </div>
</div>
</body>
</html>"""
    return html


class DaruyarAppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        html = build_html_page()
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        global LAST_MESSAGE
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = urllib.parse.parse_qs(body)

        if self.path == "/add_med":
            name = params.get("name", ["متفورمین"])[0].strip()
            cat = params.get("category", ["کنترل قند خون"])[0].strip()
            dose = params.get("dose", ["۵۰۰ میلی‌گرم"])[0].strip()
            times = params.get("times", ["14:00"])[0].strip()
            db.add_medication(name, cat, dose, times)
            db.log_medication_use(name, cat, dose, times.split(",")[0], "✅ مصرف شد (ثبت اولیه)")
            LAST_MESSAGE = f"داروی «{name}» ({cat}) برای ساعت {times} ذخیره شد و در جدول پزشک ثبت گردید."

        elif self.path == "/action":
            act = params.get("act", [""])[0]
            meds = db.get_medications()
            if meds:
                m_name, m_cat, m_dose, m_times = meds[0][1], meds[0][2], meds[0][3], meds[0][4]
                best_t, _, _ = schedule.next_due(m_times)
                sched_hm = best_t if best_t else "14:00"
            else:
                m_name, m_cat, m_dose, sched_hm = "متفورمین", "کنترل قند خون", "۵۰۰ میلی‌گرم", "14:00"

            if act == "consent":
                db.set_user_consent()
                LAST_MESSAGE = messages.CONSENT_OK
            elif act == "taken":
                db.log_medication_use(m_name, m_cat, m_dose, sched_hm, "✅ مصرف شد (به‌موقع)")
                LAST_MESSAGE = f"ثبت شد: داروی {m_name} در ساعت فعلی مصرف گردید و به گزارش پزشک اضافه شد."
            elif act == "snooze":
                db.log_medication_use(m_name, m_cat, m_dose, sched_hm, "⏳ مصرف با تعویق (۱۰ دقیقه بعد)")
                LAST_MESSAGE = messages.SNOOZED.format(minutes=10)
            elif act == "skip":
                db.log_medication_use(m_name, m_cat, m_dose, sched_hm, "❌ مصرف نشد (نخوردم)")
                LAST_MESSAGE = messages.SKIPPED
            elif act == "seed":
                db.insert_sample_demo_data()
                LAST_MESSAGE = "⚡ داده‌های نمونه ۷ روزه بیمار (یکشنبه ساعت ۱۴، دوشنبه ساعت ۱۷ و...) برای دمو استاد درج شد!"
            elif act == "clear":
                db.delete_all_user_data()
                LAST_MESSAGE = messages.DELETED

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def open_app_window(url):
    """باز کردن برنامه به صورت یک پنجره موبایلی مستقل در ویندوز"""
    try:
        subprocess.Popen(["cmd", "/c", "start", "msedge", f"--app={url}", "--window-size=560,880"])
    except Exception:
        webbrowser.open(url)


if __name__ == "__main__":
    db.init_db()
    url = f"http://127.0.0.1:{PORT}"
    print("=" * 60)
    print("✅ اپلیکیشن دارویار با موفقیت روشن شد!")
    print(f"📱 در حال باز کردن پنجره اپلیکیشن: {url}")
    print("=" * 60)
    open_app_window(url)
    server = HTTPServer(("127.0.0.1", PORT), DaruyarAppHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nاپلیکیشن بسته شد.")