# 🚀 گزارش تحویل — DropAgentX v3.3.3 «غولِ پایدار»

## ✅ خروجی‌ها
| فایل | توضیح |
|---|---|
| 📦 `DropAgentXBot-v3.3.3-unified.zip` | **نسخه نهایی** — ۱۷۹ فایل (۵۴۴KB) |
| 🌳 `bot-v333/` | ریپوی ادغام‌شده — ۱۵ فایل تغییر نسبت به v3.0.0 (+۱,۱۵۵/−۶۴) |
| 📝 `bot-v333/CHANGELOG-v3.3.3.md` | چنج‌لاگ کامل ادغام |
| 🧪 `bot-v333/tools_capacity_sim.py` | شبیه‌ساز ظرفیت v3.3.3 (با تیبل‌های مونوریپو) |

## 🔀 چه چیزی از کجا آمد؟
- **از v3.0.0 خودت (دست‌نخورده):** gateway، shared/llm، memory2، observability، identity_rl، media_v2، a2a_v2، mcp_bridge، admin_v2، deploy، هر ۵۷ تست
- **از لایه عملیاتی ما (پورت‌شده):** ۶ فیکس لاگ · داوری گزینه‌به‌گزینه تسک · فایل ابری file_id · سقف‌های چت ۲۵×(2000/1500) · FTS کاربر-فقط · ۱۰ ابزار ادمین · نگهداری خودکار cron
- **🆕 مخصوص v3.3.3 (خلأهایی که خودت گفتی):**
  - `prune_app_logs` — ریتین ۱۴روز/۵۰k ردیف برای app_logs (در v3.0.0 رشد بی‌سقف داشت!)
  - سیم‌کشی `memory2.evict_expired` در cron (تعریف شده بود ولی هیچ‌جا صدا زده نمی‌شد)
  - `starlette` به requirements.txt (تست‌های gateway بدونش red بودن — باگ دیپلوی v3)
  - `APP_LOG_RETENTION_DAYS` / `APP_LOG_MAX_ROWS` در config و .env.example

## ✅ اعتبارسنجی (۳ لایه)
1. **تست‌های خودت:** pytest مونوریپو → **۵۷/۵۷ passed** بعد از ادغام
2. **تست لایه ما:** ۱۳/۱۳ عملکردی روی SQLite واقعی (صف داوری، پاداش، رد، prune_app_logs با داده واقعی، sweep، VACUUM، آمارها، مایگریشن file_fileid، سقف‌ها)
3. **ریسیمولیشن ظرفیت** روی اسکیمای کامل جدید:
   - واقع‌بینانه ۸۰۰۰ کاربر = **۱۹۵ MB ✅** (سقف ~۲۰,۹۰۰)
   - AI-سنگین ۸۰۰۰ کاربر = **۴۰۹ MB ✅** زیر سقف ۵۰۰ — داخل ناحیه هشدار ۴۰۰ → هشدار روزانه به ادمین فعال می‌شود (طراحی همین بود)
   - تیبل‌های جدیدت فقط +۲KB/کاربر اضافه کردند (با ریتین، پایا ≈ ۷MB ثابت)

## 🐛 باگ‌هایی که در مسیر ادغام گرفتم و فیکس شدند
- `starlette` جاافتاده در requirements (v3.0.0 روی دیپلوی تمیز کرش می‌کرد)
- `config`→`cfg` در بلوک ریتین cron (NameError ساکت می‌شد)
- `config.VERSION` روی آبجکت در admin_v2 (/system) و mcp_bridge → AttributeError (حالا اتریبیوت کلاس هم هست)
- gateway/a2a نسخه را همیشه 3.0.0 نشان می‌دادند (fallback getattr) → حالا 3.3.3 واقعی
- welcome به raw Markdown برگشته بود → دوباره `send_safe`

## 🚀 دیپلوی
1. ZIP را باز کن → Railway/Docker (طبق DEPLOY_V2-railway.md خودت)
2. `.env` از `.env.example` (جدید: APP_LOG_*، FILE_STORAGE_CHANNEL_ID و...)
3. بعد از استارت: بات را ادمین کانال ذخیره فایل کن + `FILE_STORAGE_CHANNEL_ID` را ست کن
4. `VERSION = 3.3.3` در config — healthz و کشف ایجنت خودش گزارش می‌دهند
