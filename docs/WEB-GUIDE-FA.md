# 🌐 راهنمای لایه وب — صفحات، PWA و استقرار روی VPS

## نقشه صفحات
| مسیر | فایل | چیست |
|---|---|---|
| `/` و `/shop` | `web/storefront.html` | فروشگاه عمومی — **ارتقا v4.2**: تیلت سه‌بعدی کارت‌ها، جستجوی صوتی 🎙 (fa-IR)، صدای تعامل، انیمیشن اسکرول، PWA |
| `/showcase3d` | `web/showcase3d.html` | 🆕 گالری سه‌بعدی محصولات (Three.js) — پادینم چرخان با درگ، برای تبلیغ و اشتراک‌گذاری |
| `/landing.html` | `web/landing.html` | لندینگ کهکشانی سه‌بعدی (از v4.1) + PWA |
| `/live` ⚠️ | `web/live.html` | 🆕 داشبورد زنده ادمین — SSE هر ۳ ثانیه، گیج‌های Canvas، فالبک خودکار به polling |
| `/admin` | `web/admin.html` | پنل مدیریت وب (قبلی) |
| `/manifest.webmanifest` + `/sw.js` + `/offline.html` + `/icon.svg` | 🆕 PWA کامل | نصب‌شدنی روی گوشی، کار آفلاین صفحات دیده‌شده |

⚠️ `/live` از گارد ادمین وب استفاده می‌کند (کوکی hweb) — پس از `/login` وارد شو.

## تکنولوژی‌های HTML5 استفاده‌شده (ممیزی کامل)
WebGL/Three.js (لندینگ + گالری) · Pointer Events (درگ سه‌بعدی) · IntersectionObserver (ریویل+شمارنده)
· Web Audio (صدای تعاملی) · SpeechRecognition (سرچ صوتی fa-IR) · Canvas2D (گیج‌ها + فالبک ستاره‌ای)
· EventSource/SSE (داشبورد زنده) · MutationObserver (ارتقای غیرمخرب کارت‌ها) · Service Worker + Cache API + manifest (PWA)
· localStorage (ترجیحات) — **عمداً نه:** getUserMedia (بدون کاربرد واقعی) و Geolocation (حریم خصوصی)

## استقرار VPS (پیشنهادی)
```bash
# سرویس وب ادمین (fastapi/uvicorn داخل ریپو هست)
uvicorn web_admin:app --host 0.0.0.0 --port 8080   # یا: python web_admin.py

# nginx جلوی آن (TLS با certbot):
#   location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host; }
#   location /api/admin/stream { proxy_pass http://127.0.0.1:8080;
#     proxy_buffering off;          # ← برای SSE ضروری است
#     proxy_read_timeout 3600; }
```
نکته‌ها:
- PWA و Service Worker فقط روی **HTTPS** (یا localhost) فعال می‌شوند — روی http ساده مرورگر ثبت نمی‌کند.
- SSE روی nginx باید `proxy_buffering off` داشته باشد (بالا).
- قبل از انتشار، `BOT_URL` داخل `landing.html` و `showcase3d.html` را به یوزرنیم بات واقعی تغییر بده.
- `vendor/three.min.js` برای صفحاتی است که به‌صورت `<script src>` استفاده کنند؛ لندینگ و گالری نسخه اینلاین دارند تا تک‌فایلی و قابل‌پیش‌نمایش باشند.

## تست سریع پس از استقرار
1. `/healthz` → `{"ok": true, "version": "4.2.0"}`
2. `/shop` → F12 → Application → Service Workers: فعال؟
3. `/live` پس از login → نقطه سبز «زنده» + گیج‌ها هر ۳ ثانیه
4. `/showcase3d` → درگ و چرخش + کلیک → لینک بات
