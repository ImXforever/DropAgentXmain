# 🚀 مهاجرت DropAgentX به نسخه 2.0.0 + استقرار کامل روی Railway

> این سند، مسیرِ کاملِ «مهاجرت از v1 به v2.0.0» و «استقرار روی Railway» را میدهد.
> نسخهی 2.0.0 **بر پایهی همان دیتابیسِ v1** ساخته شده (جداول جدید اضافه میشوند و به دادهی قبلی دست نمیزند)، پس مهاجرت، **نگهداشتنِ داده** است.

---

## ۱) چه چیزهایی در v2.0.0 اضافه شد (خلاصه)

| خواسته | ماژول / تغییر | کجا |
|---|---|---|
| ۱. حافظهی چندوجهی | `memory2.py` — ۷ فِست (identity/factual/preference/behavioral/emotional/engagement/risk) + امتیازدهی وزن‌دار + استخراج خودکار با LLM + پاکسازی | جدول `memory_facets` |
| ۲. تصویر Gemini + سیستم OpenAI-compatible | `media_v2.py` — تولید تصویر Gemini (پلن رایگان) + fallback OpenAI-compatible + `system_chat` چندوجهی | `tools.py`، `handlers/ai_chat.py` (کاور) |
| ۳. لاگ در همه‌جا | `observability.py` — لاگ JSON ساخت‌یافته + جدول `app_logs` + خطای سراسری + middlewar خطای aiogram | `bot.py`، `web_admin.py` |
| ۴. RL هویت | `identity_rl.py` — Q-learning ساده (ε-greedy) با ۷ برچسب هویت | جدول `rl_identity`، `tasks_done` |
| ۵. ادمین ارتقایافته | `handlers/admin_v2.py` + endpointهای وب | `/id`, `/mem2`, `/logs`, `/errmap`, `/rlset`, `/system`, `/api/admin/*` |
| ۶. استقرار Railway | `railway.json`, `Procfile`, Dockerfile + HEALTHCHECK, پورت `PORT` | ریشهی پروژه |

---

## ۲) پیش‌نیازهای Railway

- یک **repo روی GitHub** (یا اتصال مستقیم) که پوشهی v2 در آن است.
- حساب **Railway** (+ پلن مناسب) و یک **Service** ایجادشده از این repo.
- متغیرهای محیطی (Environment Variables) در تنظیمات Service.

---

## ۳) استقرار قدم‌به‌قدم

### گام ۱ — Push کد به GitHub
```bash
cd /home/user/v2
git add -A
git commit -m "DropAgentX v2.0.0"
git remote add origin <YOUR_REPO_URL>
git push -u origin main
```

### گام ۲ — ساخت Service در Railway
1. **New Project → Deploy from GitHub → انتخاب repo**.
2. Railway به صورت خودکار `railway.json` → `Dockerfile` را می‌بیند و `docker build` می‌کند.
3. چون `startCommand` = `python bot.py` است، همان فرایند، هم **پولینگ تلگرام** و هم **سرور وب** را بالا می‌آورد.

> 💡 **مهم — پورت:** Railway متغیر `PORT` را تزریق میکند و کد v2 آن را می‌فهمد:
> `port = os.getenv("PORT") or os.getenv("WEB_PORT", "8080")`.
> نیازی به تنظیم دستی پورت نیست.

### گام ۳ — متغیرهای محیطی (Environment)
از فایل `.env.example` اینها را **حداقل** پر کن:

```ini
BOT_TOKEN=...
ADMIN_IDS=...

# AI (متن) — یا OpenRouter/OpenAI، یا Gemini از طریق OpenAI-compatible:
AI_API_KEY=<gemini_key_or_router_key>
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai   # برای استفاده از Gemini هم در متن
AI_MODEL=gemini-2.0-flash

# Gemini (تصویر + vision، پلن رایگان):
GEMINI_API_KEY=<google_api_key>
IMAGE_GEN_BACKEND=auto

# اقتصاد
COMMISSION_RATE=0.10
CREDITS_PER_USDT=1000
WELCOME_CREDITS=50

# وب
PORT=8080
WEB_PASSWORD=...
WEB_SECRET=...

# Storage (برای بالا آمدن در Railway مهم است — بذار روی حجم دائمی باشد)
DB_PATH=data/marketplace.db
UPLOAD_DIR=uploads
```

### گام ۴ — Volume دائمی برای دیتابیس (حیاتی)
SQLite با یک تک-اینستنس ریز روی Railway خوب کار میکند، اما **فایلها باید روی یک Volume بمانند** تا با هر Redeploy پاک نشوند:
- در تنظیمات Service → **Volumes** → Add Volume → mount path را `data` بگذار (یا `/app/data`).
- همین کار را برای `uploads` انجام بده (فایلهای محصول).

> اگر بدون Volume رها کنی، بعد از هر Deploy دیتابیس و آپلودها ریست میشوند. **این رایج‌ترین اشتباه در Railway است.**

### گام ۵ — Domain و Healthcheck
- Railway به صورت خودکار یک **Public URL** به این Service میدهد (مثلاً `https://xxx.up.railway.app`).
- این را در `.env` به عنوان `BOT_USERNAME` و در تنظیمات تلگرامِ Mini App ست کن.
- **Healthcheck** از `railway.json` خوانده میشود و به `/healthz` میزند (که خروجی `{ok, version}` میدهد). تا بالا نیامده، ترافیک نمیفرستد.

### گام ۶ — سرور وب تفکیکشده (اختیاری)
اگر بخواهی داشبورد Next.js (`web-next`) را جدا کنی، میتوانی یک **Service دوم** از `web-next` بسازی و `BACKEND_URL` را به URL این Service بدهی. برای شروع لازم نیست.

---

## ۴) متغیرهای جدید v2 برای `.env` (اختیاری، همه پیشفرض دارند)
```ini
# v2 — حافظه چندوجهی
MEMORY2_ENABLED=1
MEM_FACET_IDENTITY=1.5
MEMORY_EVICTION_DAYS=90

# v2 — تصویر Gemini
IMAGE_GEN_BACKEND=auto
GEMINI_API_KEY=
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image

# v2 — RL هویت
IDENTITY_RL_ENABLED=1
RL_EXPLORE=0.20
RL_LEARN_RATE=0.15
RL_GAMMA=0.90

# v2 — لاگ/دیده‌بانی
LOG_LEVEL=INFO
LOG_TO_DB=1
LOG_JSON_ENABLED=1
```

---

## ۵) مهاجرت داده از v1 به v2

**خبر خوب:** نیازی به Migration دستی نیست — v2 همان `database.py` را دارد و هنگام بالا آمدن *جداول جدید* را می‌سازد (`app_logs`، `memory_facets`، `rl_identity`، `tasks_done`). هیچ جدولی حذف یا تغییر داده نمیشود.

اگر روی Railway شروع می‌کنی و **دادهی v1 را روی یک VPS داری**، یکی از این دو روش:

### روش A (ساده): upload فایل `.db`
1. دیتابیس v1 را از VPS بیرون بکش: `scp root@VPS:/opt/hermes-marketplace/data/marketplace.db ./`
2. روی Railway در تنظیمات **File / Variables** یا از طریق Volume آن را در `data/marketplace.db` بگذار.
3. کد v2 همان فایل را باز میکند و جداول را اضافه میکند. ✅

### روش B (از طریق پنل ادمین)
پنل ادمین یک **Backup/Restore** دارد؛ از پنل v1 یک بکاپ بساز و در پنل v2 (روی Railway) Restore کن.

---

## ۶) نکات عملیاتی برای Railway

- **تک-اینستنس بمان.** SQLite روی چند Replica درست کار نمیکند. `numReplicas: 1` در `railway.json` ست شده.
- **اگر ترافیک بزرگ شد**، بعداً به Postgres برو (و `database.py` را چندخطی کنید)؛ این برای مقیاسِ اولیه لازم نیست.
- **Rate limiter** فعلاً in-memory است؛ اگر حملهای دیدی، با `Redis` در v2.1 جایگزین کن.
- **حجم و لاگ:** چون لاگ JSON به stdout میآید، Railway جریان لاگ را نگه میدارد و با `LOG_TO_DB=1` نسخهی WARNING+ داخل جدول `app_logs` هم ثبت میشود.

---

## ۷) چک‌لیست نهایی پیش از انتشار

- [x] `python -m compileall -q .` → بدون خطا
- [x] `pytest` → 43 tests pass
- [x] `/healthz` → `{ok, version: 2.0.0}`
- [x] جداول v2 ساخته میشوند
- [x] `PORT`/`WEB_PORT` سازگار با Railway
- [x] Volume برای `data` و `uploads`
- [ ] `BOT_TOKEN`، `ADMIN_IDS`، `GEMINI_API_KEY` (در صورت نیاز AI) تنظیم شود
- [ ] تست واقعی با Bot Token در یک کانال خصوصی (چند پیام، یک خرید، یک واریز)

---

## ۸) کشف خطا بعد از استقرار (از دید ادمین)
بعد از بالا آمدن v2، این دستورات ادمین را در تلگرام بزن:
```
/system        # سلامت + نسخه
/errmap        # تعداد خطاها بر اساس ماژول
/logs          # آخرین لاگ‌ها (persisted)
/id <uid>      # هویت RL + ویژگی‌های رفتاری
/mem2 <uid>    # حافظه‌ی چندوجهی
```
و در وب: `/admin` → تبهای جدید `logs`، `errors`، `identity`، `rl-summary`، `v2health`.
