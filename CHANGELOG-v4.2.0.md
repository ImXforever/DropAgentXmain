# DropAgentX — Changelog v4.2.0 «فول‌وب»

هدف: تکمیل کل خلأهای HTML5/Web ممیزی‌شده — بدون سقف حجم (مهاجرت به VPS پیش رو)

## 🆕 گالری سه‌بعدی محصولات — `/showcase3d`
پادینم چرخان شش‌محصولی با Three.js: درگ واقعی (Pointer Events)، اسنپ خودکار به کارت فعال،
هسته هشت‌وجهی پالس‌دار، حلقه مداری، نقطه‌های ناوبری، صدای انتخاب (Web Audio)،
فالبک ۲بعدی Canvas، لینک خرید مستقیم به بات با پارامتر ردیابی `?start=shop3d_N`

## 🛍 ارتقای فروشگاه — `/shop` (الحاقی، بدون شکستن کد قبلی)
- **تیلت سه‌بعدی** کارت‌ها با Pointer Events (فقط موس دقیق؛ لمس دست‌نخورده)
- **جستجوی صوتی** 🎙 با SpeechRecognition فارسی (fa-IR) — دکمه داخل نوار جستجو
- **صدای تعامل** (Web Audio) روی کارت/چیپ/دکمه تلگرام
- **انیمیشن اسکرول** (IntersectionObserver) با MutationObserver غیرمخرب روی کارت‌های داینامیک
- ثبت **PWA**: مانیفست + Service Worker (فقط روی http/https واقعی)

## 📡 داشبورد زنده — `/live` (جدید)
- **SSE واقعی** (`/api/admin/stream` در web_admin.py): اسنپ‌شات کامل هر ۳ ثانیه — کاربران،
  فروش امروز، حجم DB، کردیت در گردش، صف‌های واریز/برداشت/تأیید محصول، تیکت باز
- گیج‌های Canvas دست‌ساز (هدف ۸۰۰۰ کاربر + سقف ۵۰۰MB با رنگ‌بندی هشدار)
- قطعی/وصل خودکار EventSource + **فالبک خودکار به polling** بعد از ۳ شکست + ریدایرکت لاگین روی ۴۰۱
- گارد همان auth ادمین وب (کوکی HMAC)

## 📲 PWA کامل (جدید)
`manifest.webmanifest` (RTL، standalone، آیکون SVG گرادیانی) · `sw.js`
(استاتیک: stale-while-revalidate · API: همیشه شبکه · ناوبری: فالبک آفلاین) · `offline.html` فارسی
· ثبت گارد‌شده در shop و landing · `vendor/three.min.js` مشترک برای هاست واقعی

## 🔧 متفرقه
- `/showcase3d` route در web_admin.py
- `docs/WEB-GUIDE-FA.md` — راهنمای کامل صفحات + استقرار VPS (nginx، نکته proxy_buffering برای SSE)
- تست: TestClient — ۲۰۰ برای showcase/shop، ۴۰۱ گارد SSE، وجود SW/tilt/voice ✓ · pytest ۶۲/۶۲ ✓
