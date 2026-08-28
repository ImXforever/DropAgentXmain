# 🧩 نقشهی «پروژهی چندگانه» — معماری کل ترکیبی (v3.0.0)

> این سند **طراحی/نقشهکشی** است، نه کد. هدف: همپوشانی هر ۴ مجموعه (our-bot v2، hermes-agent، radius، 9router) را جلوی چشم بگذاریم، مشخص کنیم «هر کدام دقیقاً چه دارد/ندارد»، و **نقشهی اتصال (پازل)** را بچینیم. بعد از تأیید تو، کد را فازبهفاز مینویسم.

---

## ۱) چکیدهی تصمیم کلیدی (لطفاً اول این را بخوان)

«همه در یک فایل/سرویس غولپیکر» **نه** راهحل درست و نه ممکن است، چون:

- **زبانهای متفاوت**: بات + وب ادمین + AI = **Python (FastAPI/aiogram)**؛ داشبورد 9router و web-next = **Node.js / Next.js**.
- **دامنههای متفاوت**: hermes-agent یک **هارنس ایجنت خودمختار ۱۰هزار فایلی** است که بهعنوان سرویس مستقل اجرا میشود؛ اگر داخل بات map کنیم، کل پروژه میشکند.
- **تکدیتابیس مشترک** بین باتِ پولدار و هارنس هرمس خطرناک است.

**راهحل درست: «غولِ واحد» = Monorepo + پشت یک Gateway واحد.** همهی سرویسها در یک repo (v3) میآیند، هر کدام تصویر خودش را دارد، و فقط **یک نقطهی ورود (`gateway`) و یک خوشهی زیرساخت مشترک** دارند.

```
                       ┌─────────────────────────────┐
  کاربر/کلاینت  ───────▶   GATEWAY (single entry)      │  /  /admin  /dashboard  /v1/*  /well-known/*
                       │  reverse-proxy + auth + SSL │
                       └──────┬─────────┬───────┬─────┘
                              │         │       │
                     ┌────────▼───┐ ┌───▼─────┐ ┌▼────────────┐
                     │ BOT + WEB  │ │ 9router │ │ hermes-agent│
                     │ (Python)   │ │ (Node)  │ │ (Python)    │
                     │ aiogram    │ │ proxy + │ │ agent harness│
                     │ FastAPI    │ │ dashbd  │ │ (adjacent)  │
                     └────────────┘ └─────────┘ └─────────────┘
                         │ shared infra: Redis/queue, observability, secrets
```

**چرا به این شکل؟** چون این تنها راهی است که واقعاً «همهی قطعات با هم کار کنند» بدون اینکه کدها کلاً یکدیگر را بشکنند. هر قطعه از طریق **سوکتهای استاندارد** (`A2A`، `MCP`، `HTTP /v1`) وصل میشود — مثل پازل با قفلهای مشخص.

---

## ۲) «هر کدام دقیقاً چه دارد و چه ندارد» (ممیزی)

### ما (DropAgentX v2)
| دارد | ندارد |
|---|---|
| بات تلگرام + هندلرها (۱۲ روتر) | پروفایل/مهارت امن با provenance |
| مارکت، پرداخت دوگانه، کیف پول، تسک، ریفرال، ارگان | صرفهجویی توکن (حالا `token_saver` اضافه شد) |
| حافظهی چندوجهی (`memory2`)، RL هویت (`identity_rl`) | فشردهسازی تاریخچهی بلند |
| لاگساختاری `observability` + `app_logs` | کشف/هویت ایجنت (`.well-known`، A2A card) |
| وب ادمین FastAPI + Mini App RTL + storefront | LLM روتر با فالبک ۳-سطح |
| استقرار Railway + Dockerfile + healthcheck | داشبورد یکپارچه (Node) و روتر LLM |

### radius-hermes-railway-template
| دارد | ندارد |
|---|---|
| استقرار Railway به شکل worker + `requiredMountPath=/data` | دامنهی مارکت/پول (اصلاً ندارد) |
| کشف ایجنت: `.well-known/*`، ERC-8004، A2A agent card | مینیاپ تلگرام و اقتصاد |
| A2A messaging: `message/send` + `message/stream` + delegated | Mini App فارسی RTL |
| هویت رمزنگاریشده از keystore کیف پول | تصویر Gemini (پلن رایگان) |
| لاگ JSON ساختاریافته | حافظهی چندوجهی و RL |

### hermes-agent
| دارد | ندارد |
|---|---|
| هارنس ایجنت کامل (tool-use، terminal، browser، vision، image، TTS) | مارکتپلیس/پول/مینیاپ |
| **Skills Hub** با provenance + **Skills Guard** + **Skill Ledger** | پلتفرم تلگرامِ تجاریِ خودش |
| **Trajectory Compressor** (تاریخچهی بلند) | RL هویت و حافظهی فستبندیشدهی سفارشی |
| **SessionDB با FTS5/trigram/CJK** (بسیار پیشرفتهتر از ما) | دادۀ اقتصاد دوتایی |
| `tool_output_limits`, `tool_result_storage`, `tool_search` | Mini App |
| gateway چندپلتفرمی (`gateway/platforms`: signal, whatsapp, qq, wechat, webhook…) | — |
| ۱۰هزار فایل → سبک نیست | — |

### 9router
| دارد | ندارد |
|---|---|
| **LLM Router تکتک**: `/v1/{chat,embeddings,images,messages,models,responses,videos,web,search,audio}` | مارکت/پول/مینیاپ |
| **RTK Token Saver** (فشردهسازی خروجی ابزار) | — (میتواند بیصدا به بقیه سرویس بدهد) |
| **فالبک ۳سطح** (subscription→cheap→free) + multi-account round-robin | — |
| **Quota tracking** + `usage/` charts + request logs | — |
| **فرمتترجمه** (OpenAI↔Claude↔Gemini↔Cursor↔Kiro) | — |
| **داشبورد Next.js** با proxy دوردست | — |
| Docker + `20128` | — |

---

## ۳) نقشهی «وصلشدن قطعات مثل پازل» (سوکتهای اتصال)

بخش مهم: **هر قطعه از چه کانالی وصل میشود** تا به هم نخورد.

| از | به | کانال / «قفل پازل» | توضیح |
|---|---|---|---|
| بات (Python) | LLM | **`/v1` 9router** (بهجای تماس مستقیم provider) | یک `router_client` — همهی فراخوانی AI از `hermes_engine` از 9router رد میشود. فالبک/سهمیه/صرفهجویی را 9router مدیریت میکند. |
| بات | داشبورد Node | **`gateway` subpath** | 9router dash و web-next زیر `/dashboard` و `/panel` mount میشوند. |
| بات | hermes-agent | **A2A** (`/agent.json`, `message/send`, `message/stream`) + **MCP** | بازجویی ابزارهای ما به هرمس، و استفاده از Skills/Compressor هرمس. |
| بات | ابزارهای هرمس | **MCP server** (`mcp_serve.py` هرمس) | ما `tools.py` خودمان را بهعنوان MCP expose میکنیم؛ هرمس میتواند صدا بزند. |
| بات | storage/cache | **Redis queue/res** (اختیاری) | rate limiter، صف cron/treasury، کش. |
| بات | internal state | **Postgres** (فاز ۳) | جایگزین SQLite برای مقیاس؛ از `migration` لایهبندیشده. |
| (همه) | observability | **`observability` + `app_logs` + Sentry** | یک جریان لاگ واحد، جایی که `gateway` لاگ هر سرویس را جمع میکند. |
| (همه) | کشف ایجنت | **`.well-known/*`** | agent card + ERC-8004 (فقط اگر بخواهیم در اکوسیستم radius دیده شویم). |

### 🔑 ستونفقراتِ «گِلو» (ماژولهای جدیدی که خواهیم نوشت — بعداً)
این ۶ ماژول، پازل را واقعاً به هم گره میزنند:

1. `gateway.py` — reverse-proxy واحد، auth، SSL، routing (Python/استارلت or nginx).
2. `router_client.py` — جایگزین `_post_chat`/`system_chat`، همه را از `9router /v1` عبور میدهد (fain-safe با fallback مستقیم).
3. `a2a_server.py` (ارتقا) — افزودن `agent.json` + `.well-known` + `message/send`/`stream`.
4. `mcp_bridge.py` — expose کردن `tools.py` ما به هرمس + فراخوانی مهارتهای هرمس.
5. `context_compressor.py` — port از `trajectory_compressor` هرمس برای چتهای بلند.
6. `skills_guard.py` — port از `skills_guard.py` هرمس، به `skills_catalog` ما.

---

## ۴) درختِ ساختارِ «کلِ جمعشده» (عواقب monorepo v3)

```
DropAgentX-v3/                          ← monorepo (همه در یک repo، اما سرویسهای مجزا)
│
├── gateway/                            ← نقطهی ورود تنها + گلو
│   ├── gateway.py                      ← reverse-proxy (/POST /v1  به 9router، /admin و /dashboard، /well-known)
│   ├── auth.py                         ← کوکی/توکن مشترک + JWT ایجنت
│   ├── routing.yaml                    ← مسیرها: چیست به کدام سرویس میرود
│   └── alerting.py                     ← جمعآوری لاگ/هشدار هر سرویس
│
├── bot/                                ← DropAgentX (ما؛ همان v2، منظمشده)
│   ├── bot.py, config.py, database.py, observability.py
│   ├── handlers/                       ← start/tasks/products/marketplace/ai_chat/wallet/admin/admin_v2/...
│   ├── engine/                         ← hermes_engine.py, ai_agent.py, fleet.py, prompt_cache.py
│   ├── agent_core/                     ← memory2.py, identity_rl.py, skills.py, skills_catalog.py, tools.py
│   ├── commerce/                       ← commerce.py, treasury_worker.py, blockchain.py, approval.py
│   ├── media/                          ← media_v2.py (gemini), media_ai.py (stt/tts)
│   ├── web/                            ← admin.html, login.html, storefront.html, mini-app/ (RTL SPA)
│   ├── web_api/                        ← web_admin.py (FastAPI), app_api.py, a2a_server.py
│   └── server/                         ← web-next (Dashboard) — subpath: /panel
│
├── router/                             ← 9router (Node/Next.js)   [خواسته: اضافه به web app]
│   ├── src/app/api/{v1,chat,images,embeddings,usage,proxy-pools,combos,health,...}
│   ├── src/lib/{rtk,headroom,quota,format-translation,...}
│   ├── src/sse/services/backgroundTokenRefresh.js
│   ├── src/app/(dashboard)/            ← داشبورد 9router
│   ├── custom-server.js, next.config.mjs, package.json, Dockerfile
│   └── skills/                         ← skills/9router, 9router-image, 9router-tts, ...
│
├── agent/                              ← hermes-agent (سرویس مجاور، ۱۰K فایل)
│   ├── tools/                          ← web_tools, skills_hub, skills_guard, trajectory_compressor (SELECTED)
│   ├── skill_ledger.py, skill_usage.py, skills_guard.py, tool_output_limits.py
│   ├── hermes_state*.py, providers/, gateway/platforms/, agent/, plugins/
│   ├── optional-skills/                ← blockchain, finance, payments, security, ...
│   └── Dockerfile, hermes_entry.sh
│
├── radius/                             ← قالب استقرار Railway (کشف ایجنت + A2A)
│   ├── plugins/{erc8004-registry, a2a-send, agent-info, gen-jwt, radius-cast}
│   ├── skills/{a2a-comms.md, radius-wallet.md, registering-agent.md, ...}
│   ├── railway.toml, deploy.sh, tests/
│   └── templates/agent.json, .well-known/
│
├── shared/                             ← زیرساخت مشترک (گلو واقعی همه)
│   ├── infra/                          ← config, logging(observability), db, rate_limit, secrets
│   ├── queue/                          ← Redis-backed async task queue (cron/treasury/worker)
│   ├── rl/                             ← identity_rl.py (برگردانده، مشترک بین سرویسها)
│   ├── memory/                         ← memory2.py + memory.py (برگردانده)
│   ├── llm/                            ← router_client.py (تماس 9router /v1)
│   ├── security/                       ← skills_guard, path_security, threat_patterns, url_safety
│   └── mcp/                            ← a2a (agent card, /well-known), mcp_bridge
│
├── deploy/
│   ├── railway.json, Procfile, docker-compose.yml (3 service: bot, router, agent)
│   ├── Dockerfile (root), Dockerfile.router, Dockerfile.agent
│   └── secrets.example.env, volumes/{data,uploads,router-data,hermes-home}
│
├── docs/                               ← README, CHANGELOG, BLUEPRINT, running-architecture.md
└── tests/                              ← integración: test_bot.py, test_router.py, test_a2a.py
```

> 💡 **نکتهی مستقیم:** این «درختِ فیزیکیِ» repo است (همه در یک پوشه میآیند). اما تصویر داکر **سه سرویس** میسازد (bot، router، agent) که پشت gateway قرار میگیرند. پس درخت تک repo است، ولی runtime سهکپسولی.

---

## ۵) خواستهی تو: «9router به web app اضافه شود» — دقیقاً چطور

9router یک **داشبورد Node/Next.js** + یک **روتر `/v1`** است. «اضافه به وباپ» یعنی دو کار:

1. **روتر LLM -> سرویس بات:** تمام فراخوانیهای AI از `hermes_engine` بهجای `AI_BASE_URL` مستقیم، از `9router /v1/chat` عبور کنند. این به معنی:
   - **فالبک ۳سطح** (subscription→cheap→free) → دیگر هیچ وقت AI بیپاسخ نمیماند.
   - **کیوتا/چندکلیدی** → مدیریت هزینه و limit.
   - **صرفهجویی توکن** → `token_saver` (قبلاً ساختم) + RTK 9router.
2. **داشبورد 9router -> وب:** mount شدن زیر `/dashboard` در gateway؛ کوکی/admin مشترک با وب ادمین ما؛ و یک «UI واحد» که از `/admin` (پنل مالی) و `/dashboard` (روتر/کیوتا) با هم قابل دسترسی باشد.

**سوختِ این تصمیم:** ما `router_client` را نمینویسیم که دوباره فالبک بسازد؛ صرفاً به 9router delegate میکنیم و در صورت قطعی، fail-safe به `AI_BASE_URL` مستقیم برمیگردیم.

---

## ۶) فازبندی پیشنهادی (کد را بعد از تأییدت مینویسم)

| فاز | کار | خروجی قابلتست |
|---|---|---|
| **P0** | `gateway` + `router_client` → اتصال AI به 9router | یک تماس AI از `/v1` با فالبک ۳سطح |
| **P1** | mount داشبورد 9router زیر `/dashboard` + SSO | ورود ادمین مشترک به هر دو پنل |
| **P2** | `skills_guard` + `skill_ledger` (پورت از هرمس) | مهارتهای نصبشده اسکن و امن شوند |
| **P3** | `context_compressor` (پورت trajectory_compressor) | چتهای بلند هزینه کمتر |
| **P4** | `a2a` + `.well-known` + `agent.json` (پورت از radius) | `.well-known/agent.json` پاسخ میدهد |
| **P5** | `mcp_bridge` → expose ابزارهای ما به هرمس | هرمس بتواند ابزار بات را صدا بزند |
| **P6** | Postgres + Redis + صف (زیرساخت مقیاس) | چند-replica بدون مغایرت |

---

## ۷) چند نکتهی صادقانه و مهم

- **hermes-agent را full-fork نمیکنیم.** ۱۰هزار فایل + وابستگی Node، داخل باتِ تلگرامی ما ناسازگار است. **گزینش** میکنیم: فقط ماژولهای انتخابی (skills_guard، trajectory_compressor، session state، tool_output_limits) را port میکنیم؛ بقیهی هرمس بهعنوان سرویس مجاور از طریق A2A/MCP صحبت میکند. این هم برای ما کمهزینه است هم پروژه را نمیشکند.
- **۹router Node است**؛ نمیتواند «داخل» پایتون باشد؛ پس با `gateway` proxy میشود (بخشی از همان «پازل با قفل»).
- **یک دیتابیس مشترک به همه نمیدهیم.** بات دیتابیس خودش، هرمس state خودش، 9router دیتای خودش؛ اتصال از طریق API/A2A/MCP. (بههمریخته شدن state پولهایی است که میتواند همهچیز را بشکند.)
- **دو UI فارسی/RTL و انگلیسی**: Mini App و storefront ما RTL است؛ داشبورد 9router/Next انگلیسی. هر دو زنده میمانند، فقط زیر یک ورودی.

---

## ۸) وقتی بگویی «کد بزن»، شروع میکنم از:
1. `gateway.py` + `router_client.py` (اتصال AI به 9router) — **بالاترین اثر فوری.**
2. mount 9router زیر `/dashboard`.
3. بعد بر اساس فازها.

**درخت و نقشه آماده است.** حالا در مرحلهی تأیید: آیا این معماری (monorepo + ۳ سرویس پشت gateway + اتصال A2A/MCP/HTTP) را میپذیری؟ اگر بله، بگو **از کدام فاز شروع کنم**؛ پیشنهاد من: **P0 (اتصال AI به 9router)**، چون سریع، امن و با بیشترین سود هزینه است.
