import flet as ft
import db
import schedule
import messages
import med_parser

# کد صفحه موبایل دارویار (سازگار با بیلد اندروید Flet)
def main(page: ft.Page):
    page.title = "دارویار"
    page.rtl = True
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 12
    page.bgcolor = "#F8FAFC"

    db.init_db()
    status_txt = ft.Text("اپلیکیشن اندروید دارویار آماده است.", color="#1D4ED8", size=12, weight=ft.FontWeight.BOLD)
    notif_txt = ft.Text("", color="#FFFFFF", size=13, weight=ft.FontWeight.BOLD)
    adh_txt = ft.Text("", color="#0F766E", size=14, weight=ft.FontWeight.BOLD)
    logs_col = ft.Column(spacing=6)

    def refresh():
        p_date, w_day, now_hm = db.get_persian_date_and_day()
        meds = db.get_medications()
        if meds:
            m = meds[0]
            best_t, _, _ = schedule.next_due(m[4])
            notif_txt.value = schedule.get_notification_bar_text(m[1], m[2], best_t or "14:00", p_date, w_day)
        else:
            notif_txt.value = f"📅 امروز: {w_day} {p_date} | هنوز دارویی ثبت نشده است"

        adh_txt.value = f"📊 شاخص پایبندی بیمار به درمان: {db.calculate_adherence_percentage()}٪"
        logs_col.controls.clear()
        for r in db.get_doctor_report():
            logs_col.controls.append(
                ft.Container(
                    bgcolor="#FFFFFF", padding=8, border_radius=8,
                    content=ft.Column([
                        ft.Text(f"💊 {r[0]} ({r[2]}) - {r[1]}", weight=ft.FontWeight.BOLD, size=12),
                        ft.Text(f"📅 {r[3]} {r[4]} | مقرر: {r[5]} | ثبت: {r[6]} | {r[7]}", size=11),
                    ])
                )
            )
        page.update()

    def quick_act(stat):
        meds = db.get_medications()
        m_name, m_cat, m_dose, sched = (meds[0][1], meds[0][2], meds[0][3], "14:00") if meds else ("متفورمین", "کنترل قند خون", "۵۰۰ میلی‌گرم", "14:00")
        db.log_medication_use(m_name, m_cat, m_dose, sched, stat)
        status_txt.value = f"وضعیت «{stat}» در جدول پزشک ذخیره شد."
        refresh()

    def seed_demo(e):
        db.insert_sample_demo_data()
        status_txt.value = "⚡ داده‌های ۷ روزه برای دمو استاد درج شد!"
        refresh()

    page.add(
        ft.Container(
            bgcolor="#0F2C59", padding=12, border_radius=10,
            content=ft.Column([
                ft.Text("🔔 نوار اعلان دائمی دارویار", color="#5EEAD4", size=11),
                notif_txt,
                ft.Row([
                    ft.ElevatedButton("✅ مصرف کردم", on_click=lambda e: quick_act("✅ مصرف شد")),
                    ft.ElevatedButton("⏳ ۱۰ دقیقه بعد", on_click=lambda e: quick_act("⏳ تعویق")),
                    ft.ElevatedButton("❌ نخوردم", on_click=lambda e: quick_act("❌ مصرف نشد")),
                ], wrap=True)
            ])
        ),
        status_txt,
        ft.ElevatedButton("⚡ درج داده نمونه ۷ روزه برای دمو استاد", on_click=seed_demo),
        ft.Text("👨‍⚕️ گزارش بالینی پزشک معالج:", weight=ft.FontWeight.BOLD, size=14),
        adh_txt,
        logs_col
    )
    refresh()

if __name__ == "__main__":
    # سازگار با هر دو نسخه قدیم و جدید Flet
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)