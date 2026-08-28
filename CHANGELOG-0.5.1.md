# DropAgentX — Changelog 0.5.1 «دوجهانه»

تاریخ: ۲۰۲۶-۰۸-۲۸ · یک کد، دو مقصد: **VPS + Railway** — با کیت کامل کمپین و فونت خودمیزبان

## 🐛 باگ بحرانی فیکس‌شده
- **فایل‌های PWA هیچ route استاتیکی نداشتند!** `sw.js` و `manifest` و `icon` از سرور ۴۰۴
  می‌دادند (PWA عملاً روی هاست کار نمی‌کرد) → Mount استاتیکی ریشه در `web_admin.py`
  (آخر از همه — فقط مسیرهای بدون route) → همه: ۲۰۰ ✓

## 🚀 استقرار دووجهانه — `python run.py`
- **لانچر واحد:** Railway (PORT→WEB_PORT خودکار) و VPS (systemd/nginx) با یک دستور
- `DATA_DIR` → نگاشت خودکار DB/UPLOADS/BACKUPS به Volume
- تشخیص خودکار محیط (`RAILWAY_ENVIRONMENT`) + بنر نسخه/حالت/پورت
- `Procfile` و هر دو `railway.json` → `python run.py`
- راهنمای کامل: `docs/DEPLOY-VPS-RAILWAY-FA.md` (systemd + nginx + SSE + مهاجرت)

## 🐛 فیکس: `/landing` در 0.5.0 route گرفت — تأیید مجدد در QA این نسخه ✓

## 🌐 وب: حرفه‌ای‌تر شد
- **فونت وزیرمتن خودمیزبان** (۴ وزن woff2) — فروشگاه دیگر به گوگل وابسته نیست (سریع‌تر در ایران)
- **آیکون‌های PNG برند** (۱۹۲/۵۱۲/maskable/apple) + `og-image` برای اشتراک‌گذاری زیبا
- og:image در فروشگاه/لندینگ/گالری · manifest با PNG icons (سازگاری نصب حداکثری)

## 🌍 چندزبانه (بنیان ۱.۰)
- `i18n.py` — t(key, lang) با فالبک دو مرحله‌ای · `locales/fa.json` + `locales/en.json`
  (~۹۰ کلید رابط) — آمادهٔ اتصال کد در نسخه‌های بعد

## 🧰 ابزارهای عملیات
- `tools_db_doctor.py` — سلامت‌سنج CLI: quick_check، FK، یتیم‌ها، بزرگ‌ترین تیبل‌ها، --fix-wal
- `tools_seed_skills.py` + **پک ۱۲ مهارت هرمس** (`skills_builtin/`): استاد پرامپت، لیستینگ،
  قیمت‌گذاری، مارکتینگ تلگرام، کپی‌رایتینگ، پشتیبانی، چک‌لیست لانچ، تقویم محتوا، امنیت USDT،
  ایده‌های محصول، روانشناسی فروش، سئو — آمادهٔ نصب در فروشگاه مهارت‌ها

## 📣 کیت کمپین (۸ پوستر برند)
`docs/marketing/` — لانچ، کد هدیه، قرعه‌کشی، مارکت‌پلیس، چت AI، کیف پول، ریفرال، ماموریت‌ها
+ `docs/USER-GUIDE.html` راهنمای مصور کاربر نهایی

## ✅ QA
py_compile کل ✓ · pytest **۶۸/۶۸** (+۶ تست: i18n، لانچر، پک مهارت، دکتر DB) ✓
مسیرها: sw/manifest/icon/offline/fonts/assets/landing/showcase3d/shop/healthz همه ۲۰۰ ✓
SSE بدون لاگین ۴۰۱ ✓ · healthz = 0.5.1 ✓
