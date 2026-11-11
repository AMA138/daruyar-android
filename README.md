# دارویار (Daruyar) — نسخه‌ی اسپرینت ۲

یادآور مصرف دارو: اپ اندروید (WebView) + سرور پایتونی با ثبت‌نام/ورود + بات بله. فقط کتابخانه‌ی استاندارد پایتون (سازگار با ویندوز و Pydroid 3).

## اجرای دمو (۲ دقیقه)
```
python -m pytest -q          # همه‌ی تست‌ها باید سبز باشد
python app_ui.py             # سرور + پنجره‌ی موبایلی (روی ویندوز با Edge)
```
- ثبت‌نام کنید (یا «ادامه بدون سرور») و روی «⚡ درج داده‌ی نمونه‌ی ۷ روزه» بزنید.
- فقط سرور: `python server.py`. تنظیمات با متغیر محیطی یا `.env` (نمونه: `.env.example`): `DARUYAR_HOST`, `DARUYAR_PORT`, `DARUYAR_DB`, `BALE_BOT_TOKEN`, `BALE_BOT_USERNAME`, `WEBHOOK_SECRET`.
- **آدرس سرور قابل تنظیم است**: در APK روی صفحه‌ی ورود «تنظیم آدرس سرور» یا بعد از ورود از منوی 👤 ← آدرس سرور (مثلاً `http://192.168.1.20:8765` یا سرور دانشگاه). برنامه بدون سرور هم کار می‌کند و بعداً همگام می‌شود.

## معماری
| بخش | فایل |
|---|---|
| سرور REST + سرو HTML | `server.py` |
| پایگاه داده چندکاربره، ثبت‌نام/ورود (PBKDF2-SHA256 با salt)، نشست، همگام‌سازی، پایبندی | `db.py` |
| زمان‌بندی (تهران، تاریخ شمسی بدون jdatetime، `parse_frequency`) | `schedule.py` |
| بانک ۳۰ دارو/مکمل در ۳ دسته + استخراج از متن نسخه | `data/drugs_seed.csv`, `med_parser.py` |
| متن‌ها و لیست شرایط مصرف | `messages.py` |
| آموزش درون‌برنامه‌ای (۱۱ بخش؛ بار اول خودکار، بعداً از «❓ راهنما») | `web/index.html` (ثابت `TOUR`) · تست: `tests/test_guide.py` |
| رابط (ورود، ۴ تب شامل پروفایل و ساعت تقریبی بیداری/ناهار/شام، حلقه‌ی پایبندی، جدول MAR، پل نوتیفیکیشن) | `web/index.html` |
| کلاینت بله | `bale_client.py` |
| اپ اندروید و بیلد | `android/`, `tools/`, `.github/workflows/build_apk.yml` |
| Flet قدیمی (بایگانی) | `legacy/main_flet.py` |

## API
| مسیر | کار |
|---|---|
| `POST /api/register` `{username,password,profile}` | ثبت‌نام؛ profile: `general` / `athlete` / `prosthetic_beauty` |
| `POST /api/login` | ورود؛ خروجی `token` (هدر `Authorization: Bearer ...`) |
| `POST /api/sync` `{meds,logs}` | ادغام داروها (آخرین `updated_at` برنده) و لاگ‌ها (idempotent با `client_id`)؛ خروجی وضعیت کامل |
| `GET /api/meds` ، `GET /api/logs` | داروها / تاریخچه + پایبندی کل و به تفکیک دسته |
| `POST /api/parse` `{text}` | استخراج دارو از متن نسخه (چیزی ذخیره نمی‌کند) |
| `POST /api/link_code` | کد ۶ نویسه‌ای اتصال حساب به بات بله |
| `POST /api/bale_webhook` | پیام بله/n8n: `{message:{chat:{id},text}}` یا ساده `{chat_id,text}` |
| `POST /api/profile` `{display_name?,profile?,wake_time?,lunch_time?,dinner_time?}` | به‌روزرسانی پروفایل؛ ساعت‌ها `HH:MM` (خالی = پاک‌کردن)؛ خروجی `user` |
| `POST /api/delete_me` ، `GET /api/health` ، `GET /api/drugs` | حذف کامل داده‌ها / سلامت / بانک دارو |

## بات بله و n8n
1. در اپ: ثبت دارو ← «دریافت کد اتصال» ← در بله به بات `/link CODE` بفرستید.
2. بعد از آن هر متن نسخه‌ای که به بات برسد (فوروارد یا کپی) با `med_parser` خوانده و برای همان کاربر ثبت می‌شود؛ اپ در همگام‌سازی بعدی (حداکثر ۶۰ ثانیه) آن را نشان می‌دهد.
3. دو حالت اتصال: (الف) وب‌هوک مستقیم بله به `/api/bale_webhook` (ب) **n8n**: گره Webhook/Telegram-Trigger ← گره HTTP Request (POST به `/api/bale_webhook` با هدر `X-Webhook-Secret`) ← پاسخ `reply` را n8n برای کاربر بفرستد. n8n الزامی نیست؛ فقط واسط انعطاف‌پذیر است (مثلاً زمان‌بندی گزارش هفتگی برای پزشک).
4. ⚠ API واقعی بله هنوز آزمایش نشده؛ بات‌ها معمولاً فقط پیام‌های مستقیم به خودشان را می‌بینند (اتصال مستقیم به پیام رسمی بیمه بدون API/مجوز ممکن نیست).

## ساخت APK
`git push` به `main` ← GitHub Actions: تست‌ها، `tools/make_icon.py` (لوگو)، `tools/build_assets.py` (HTML)، `javac/d8/aapt/zipalign/apksigner` ← فایل `Daruyar.apk` (شناسه‌ی `ir.daruyar.app`).
نوتیفیکیشن دائمی با تاریخ شمسی، داروی بعدی، شرط مصرف، زمان باقی‌مانده و ۳ دکمه؛ مجوز `POST_NOTIFICATIONS` در اندروید ۱۳+ هنگام اجرا درخواست می‌شود.
فونت وزیرمتن: فایل `Vazirmatn.woff2` را در `web/fonts/` بگذارید تا داخل HTML جاسازی شود (بدون آن از Tahoma/فونت سیستم استفاده می‌شود).

## نقش‌ها ← فایل‌ها
بیتا: `db.py`، `/api/register|login|sync` · ستاره: `schedule.py`، پل نوتیفیکیشن (`MainActivity.java`) و تست روی گوشی · نگین: `data/drugs_seed.csv` (تأیید ATC و دوزها با داروساز) و `med_parser.py` · هستی: `web/index.html` (ظاهر)، `messages.py`، آیکون · بهاره: اتصال کلاینت-سرور، n8n، تست نصب APK · نگار: `adherence_by_category`، `tests/test_sprint2_messages.py` · امیرمهدی: ادغام، سرور دانشگاه، CI.

## محدودیت‌های شناخته‌شده
- نوتیفیکیشن فقط وقتی به‌روز می‌شود که برنامه باز/در پس‌زمینه‌ی زنده باشد (هر ۳۰ ثانیه)؛ برای یادآور با برنامه‌ی بسته باید `AlarmManager`/سرویس پیش‌زمینه اضافه شود (مجوز `FOREGROUND_SERVICE` اعلام شده ولی سرویسی ندارد).
- OCR تصویر نسخه ندارد؛ فقط متن/فایل `.txt`/بات.
- ارتباط HTTP ساده است؛ برای سرور واقعی پشت HTTPS قرار دهید (رمز عبور در شبکه رمزنگاری نمی‌شود). محدودیت تعداد تلاش ورود پیاده نشده.
- دوز و شرط پیش‌فرض داروها فقط برای تسریع ثبت است و باید توسط داروساز بازبینی شود.

دارویار فقط یادآور است و توصیه‌ی پزشکی نمی‌دهد.
