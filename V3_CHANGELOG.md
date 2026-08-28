# 🆕 DropAgentX v3.0.0 — Monorepo «غولِ واحد»

> مبنا: v2.0.0 (۴۳ تست) — **بدون شکستن پایه**. این نسخه، پروژه را به یک
> monorepo چندسرویسی + شبکهی گِلو تبدیل میکند که پشت یک Gateway واحد،
> بات (ما) + روتر LLM (9router) + هارنس ایجنت (hermes-agent) + قالب استقرار
> و کشف ایجنت (radius) را به هم وصل میکند.

---

## چرا این شکل؟
سه ریپوی بیرونی به زبانها و دامنههای متفاوتاند (Python / Node / 10k-file harness).
پس «همه در یک فایل غولپیکر» ممکن نیست. راهحل: **همه در یک repo، ولی ۳ سرویس پشت یک
gateway** که از طریق قفلهای استاندارد (A2A، MCP، HTTP `/v1`) صحبت میکنند.

---

## ✅ دستاوردهای نسخه

### ۱) گیتوی واحد — `gateway/gateway.py`
- **نقطهی ورود واحد** به کل محصول: یک hostname و یک مرز auth.
- پراکسی:
  - `/v1/*` → روتر LLM (9router) ← خواستهی «9router به وباپ اضافه شود»
  - `/dashboard` → داشبورد 9router
  - `/panel` → داشبورد ادمین Next.js
  - `/agent.json` و `/.well-known/agent.json` → کشف ایجنت
- ساختهشده بر Starlette (بدون وابستگی اضافه).

### ۲) اتصال AI به 9router — `shared/llm/router_client.py`
- تمام فراخوانیهای AI میتوانند از `{ROUTER_BASE_URL}/v1/chat/completions` عبور کنند.
- بهره: **فالبک ۳سطح + کیوتا/چندکلیدی + صرفهجویی توکن** (از 9router، بدون دوبارهنویسی).
- **fail-safe**: اگر روتر نبود یا خطا داد، به `hermes_engine` مستقیم برمیگردد (نه سکوت).

### ۳) فشردهسازی کانتکست — `shared/context/context_compressor.py`
- پورت از `trajectory_compressor` هرمس: پیچهای میانی چتهای بلند را فشرده میکند و
  **اول (سیستم/انسانی) و آخر (نتیجه) را حفظ** میکند → هزینه کمتر + بدون overflow.

### ۴) مهارتگرد امنیتی — `shared/security/skills_guard.py`
- پورت از `skills_guard` هرمس: اسکن SKILL.md/پلاگین برای الگوهای خطرناک (blocked)
  و تزریق پرامپت (suspicious)، با **allow-list** برای ریپوهای قابل اعتماد و `content_hash`
  برای provenance.

### ۵) A2A v2 + کشف ایجنت — `a2a_v2.py`
- `POST /a2a/send`, `POST /a2a/stream`, `GET /agent.json`, `/.well-known/agent.json`.
- fail-closed با `A2A_TOKEN`؛ از همان موتور AI بات (`hermes_chat`) استفاده میکند.

### ۶) پل MCP — `mcp_bridge.py`
- ابزارهای بات (`tools.py`) را از طریق JSON-RPC/MCP به هرمس expose میکند.
- `tools/list`, `tools/call`, `initialize`.

### ۷) استقرار ۳سرویسی — `deploy/`
- `docker-compose.v3.yml` (gateway + bot + router/9router)، `Dockerfile`, `Dockerfile.gateway`,
  `railway.json`.

---

## 🧪 تأیید کیفیت (خود بررسی)
```
pytest                     →  57 passed  (43 پایه + 14 گلو)   
python -m compileall -q .  →  OK
```

## 📌 فایلهای تغییر یافته / جدید
**جدید:**
`gateway/gateway.py`, `shared/llm/router_client.py`,
`shared/context/context_compressor.py`, `shared/security/skills_guard.py`,
`a2a_v2.py`, `mcp_bridge.py`, `tests/test_v3_glue.py`,
`deploy/docker-compose.v3.yml`, `deploy/Dockerfile.gateway`, `deploy/Dockerfile`,
`deploy/railway.json`, `V3_CHANGELOG.md`, `V3_BLUEPRINT.md`.

**تغییریافته:** `config.py` (+روتر/A2A)، `bot.py` (راهاندازی A2A v2/MCP)،
`.env.example` (+متغیرهای v3).

---

## 🗺 فازهای بعدی (طبق blueprint)
- **P2** وصل `skills_guard` به `skills_catalog` (امنیتبخشی مهارتهای نصبشده).
- **P3** وصل `context_compressor` به `ai_chat`.
- **P6** Postgres + Redis + صف (مقیاس).
