# 🆕 DropAgentX v2.0.0 — ChangeLog

> مبنا: v1.1.0 (`DropAgentXmain`) — ۴۳ تست پایدار.
> هدف نسخه: از «پرامکانات» به «قابلاتکا + هوشمند» رفتن، بدون دستزدن به دادهی قبلی.

---

## 🧠 ۱) حافظهی چندوجهی (`memory2.py`)

- حافظه به **۷ فِستِ مجزا** تقسیم شد:
  `identity` (پایدار/چسبنده)، `factual`، `preference`، `behavioral`، `emotional`، `engagement`، `risk`.
- **امتیازدهی وزندار**: وزن هر فِست (قابل تنظیم با `MEM_FACET_*`) + اهمیت + زوال زمانی + شمارش فراخوانی + همپوشانی کلیدواژه با سؤال.
- **هویت چسبنده**: حقایقِ «نام/تولد/زبان/منطق زمانی/شغل/مکان» هرگز پاک نمیشوند؛ بقیه با `MEMORY_EVICTION_DAYS` منقضی میشوند.
- **استخراج خودکار با LLM**: بعد از هر چت، از مدل خواسته میشود حافظهها را بهصورت JSON فِستبندیشده استخراج کند (`extract_memories`).
- **تغذیهی خرید**: هر خرید به فستهای `preference`/`behavioral`/`engagement` رهنمون میشود (`record_purchase`).
- جدول جدید: `memory_facets`. **جایگزین** `memory.build_memory_context` نمیشود (برای سازگاری، call-site جدید `memory2.build_memory_context` است).

## 🎨 ۲) تصویر Gemini + سیستم OpenAI-compatible (`media_v2.py`)

- تولید تصویر با **Gemini (پلن رایگان)** از طریق REST `:generateContent` با مدل `gemini-2.5-flash-image`.
- **fallback خودکار** به هر endpoint سازگار OpenAI `/images/generations` (با `MEDIA_BASE_URL`).
- `system_chat(messages, model)` → یک فراخوانی OpenAI-compatible واحد (متن + vision + ابزار) که میتواند به Gemini-compatible (`.../v1beta/openai`) یا هر روتر دیگر اشاره کند.
- `gemini_vision(prompt, image_data_url)` → فهم تصویر (captions/تحلیل محصولات/OCR سبک).
- مسیرهای کاور (`handlers/ai_chat.py`) و ابزار `generate_cover_image` (`tools.py`) به `media_v2` وصل شدند.

## 🪵 ۳) تمامِ لاگها در ساختار پروژه (`observability.py`)

- **لاگ ساختاریافته JSON** به stdout (برای Railway/Docker drain).
- **جدول `app_logs`** برای ثبت persistent: همهی WARNING/ERROR + رویدادهای صریح (`db_log`) + audit (`audit`).
- **قفل خطای سراسری** (sys.excepthook) + **middleware خطای aiogram** → هر کرشِ هندلر دیگر بیصدا نمیماند و قابل جستجو است.
- دکوراتور `@logged(dimension, name)` برای لاگکردن شروع/پایان/شکست هر عملیات.
- `web_admin.py` endpointهای جدید: `/api/admin/logs`, `/api/admin/errors`.

## 🤖 ۴) RL شناسایی هویت (`identity_rl.py`)

- Q-learning ساده (بدون وابستگی ML) با **ε-greedy**، نرخ یادگیری و تخفیف قابل تنظیم.
- **۷ برچسب هویت**: `new_user`, `browser`, `task_earner`, `returning_buyer`, `high_value`, `supporter`, `churn_risk`.
- **State = بردار رفتار** (بازدید، خرید، تسک، برداشت، عمق چت، bucket ساعتی، تازگی).
- **Reward = رویداد واقعی** (خرید، برداشت، تسک، چت، ریفاند، mystery-box) که برچسبهای متناظر را تقویت میکند.
- **ذخیرهسازی** در جدول `rl_identity`؛ `get_identity` + `confidence`+ `signal(event)`.
- از `handlers/ai_chat.py` سیگنال `chat_message` میگیرد.

## 🛠 ۵) سیستم ادمین ارتقایافته (`handlers/admin_v2.py` + وب)

- دستورات جدید (با `send_safe` — بدون باگ Markdown): `/id`, `/mem2`, `/logs`, `/errmap`, `/rlset`, `/system`.
- پنل callback (`admin_v2_panel`).
- endpointهای وب ادمین: `/api/admin/logs`, `/api/admin/errors`, `/api/admin/identity/{uid}`, `/api/admin/rl-summary`, `/api/admin/v2health`.
- حجم ۱۲ روتر (افزودهٔ `admin_v2_router`).

## 🚢 ۶) استقرار کامل Railway

- `railway.json` (builder=DOCKERFILE، startCommand، healthcheck `/healthz`).
- `Procfile`، Dockerfile + `HEALTHCHECK`، پورت `PORT`/`WEB_PORT`، `DEPLOY_V2-railway.md`.

---

## ✅ تأیید کیفیت
- `python -m compileall -q .` → بدون خطا
- `pytest` → **43 passed**
- `/healthz` → `{ok: true, service: hermes-marketplace, version: "2.0.0"}`
- جداول v2 (app_logs, memory_facets, rl_identity, tasks_done) ساخته میشوند.
- RL بعد از رویداد purchase برچسب `returning_buyer` یاد گرفت.

## 📌 فایلهای تغییریافته / جدید
**جدید:** `observability.py`, `memory2.py`, `media_v2.py`, `identity_rl.py`, `handlers/admin_v2.py`, `railway.json`, `Procfile`, `DEPLOY_V2-railway.md`.
**تغییریافته:** `config.py`, `bot.py`, `web_admin.py`, `Dockerfile`, `.env.example`, `handlers/__init__.py`, `handlers/ai_chat.py`, `tools.py`.
