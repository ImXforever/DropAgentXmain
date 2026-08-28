# گزارش ارزیابی DropAgentXBot / Hermes Marketplace Bot

تاریخ بررسی: ۲۷ اوت ۲۰۲۶ — نسخه بررسی‌شده: `6f5c2ef`

## جمع‌بندی مدیریتی

این مخزن یک **پروتوتایپ نسبتاً کامل و feature-rich** برای بات تلگرام مارکت‌پلیس محصولات دیجیتال است؛ از نظر حجم و دامنه کار ارزشمند است، اما هنوز برای نگهداری پول واقعی و انتشار عمومی، production-ready نیست. مشکل اصلی کمبود قابلیت نیست؛ **یکپارچگی بین مسیرهای خرید، احراز هویت/دسترسی فایل، پرداخت کریپتو و تست خودکار** است.

### نمره پیشنهادی

- ارزش فنی پروتوتایپ: **۶٫۵ از ۱۰**
- آمادگی استفاده با پول واقعی: **۳٫۵ از ۱۰** تا قبل از اصلاح موارد High/Blocker
- وضعیت اجرا: **کد Python کامپایل می‌شود و داشبورد وب محلی بالا آمد؛ بات تلگرام بدون BOT_TOKEN قابل اجرای واقعی نیست.**

## آمار دقیق مخزن

- فایل tracked: **۷۱ فایل**؛ شامل ۶۹ فایل متنی/کدی و ۲ تصویر JPG تکراری.
- خطوط فیزیکی متن/کد: **25,607**
- خطوط غیرخالی: **22,973**
- Python: ۳۴ فایل / ۱۳٬۵۴۷ خط فیزیکی / ۱۱٬۶۰۴ غیرخالی
- JavaScript: ۱۴ فایل / ۵٬۶۸۷ خط
- HTML: ۸ فایل / ۲٬۸۶۲ خط
- CSS: ۳ فایل / ۳٬۰۶۱ خط
- مستندات/تنظیمات/اسکریپت: ۱۰ فایل / ۴۵۰ خط
- دیتابیس: **۲۶ جدول SQLite + یک FTS5 virtual table**
- API: در build فعلی **۷۴ route**؛ ۲۱ route مربوط به Mini App و حدود ۵۲ route وب/ادمین به‌علاوه صفحات/health
- هندلرهای aiogram: **۱۶۳ decorator route**
- ابزارهای AI تعریف‌شده: **۱۶ tool spec**

## چه چیزهایی دارد؟

### Backend و بات تلگرام
- ثبت‌نام، منوی اصلی، Force-channel gate و پروفایل.
- سیستم task/تبلیغ برای follow/subscribe/like/comment و پرداخت پاداش با credit.
- ساخت محصول با مسیر AI یا دستی، آپلود فایل، تصویر/کاور، ویرایش و moderation.
- مارکت، جستجو، دسته‌بندی، خرید با credit، coupon، review و commission.
- کیف پول داخلی credit↔USDT، ثبت دستی deposit/withdrawal و تأیید توسط ادمین.
- پرداخت Telegram Stars در مسیر بات.
- referral، milestone، رتبه‌های associate/soldier/capo/underboss و hunter permissions.

### AI و داده
- Hermes engine با حالت‌های `cli`، `http` و `api`، fallback، retry و استریم SSE.
- حافظه کوتاه/بلندمدت، purchase profile، persona و سیستم skill با فرمت `SKILL.md`.
- Fleet چندایجنتی، tool calling، جستجوی وب، خواندن صفحه وب و sandbox پایتون.
- endpoint تشخیصی `ai_probe.py`، MCP client سبک و A2A server اختیاری.

### Web و عملیات
- Mini App فارسی RTL با SPA، feed/explore/search/product/profile/wallet/activity/create.
- storefront عمومی، پنل ادمین، moderation، مالی، backup/restore و cockpit به نام SenPai.
- Dockerfile، docker-compose، اسکریپت نصب Linux/Windows، log rotation و cron گزارش/backup.

## چه چیزهایی ندارد یا ناقص است؟

- **تأیید خودکار زنجیره‌ای ندارد:** deposit فقط TXID می‌گیرد و ادمین دستی approve می‌کند؛ wallet provider، on-chain verification، payout automation، escrow و refund کامل وجود ندارد.
- **تست خودکار، CI/CD، lockfile و license ندارد:** در مخزن test/pytest، GitHub Actions، `poetry.lock`/`uv.lock` یا `LICENSE` دیده نشد.
- **مقیاس‌پذیری واقعی ندارد:** SQLite singleton برای یک instance مناسب است، نه چند worker/چند replica؛ rate limit هم in-memory است.
- **Discord بیشتر scaffold است:** `discord.py` در requirements نیست و مسیر جداگانه production/deployment ندارد.
- **Media AI از OpenRouter کار نمی‌کند:** خود `media_ai.py` تصویر/STT/TTS را برای OpenRouter غیرفعال اعلام کرده و برای provider دیگر نیاز به تنظیم جداگانه دارد.
- **Dashboard در docker-compose پورت publish نمی‌کند:** برای دسترسی مستقیم به web باید reverse proxy/port mapping جدا اضافه شود.
- HTTPS termination، 2FA ادمین، secret manager، audit actor واقعی و مانیتورینگ/alerting production ارائه نشده است.

## یافته‌های مهم فنی و امنیتی

### Blocker / High
1. **راه‌اندازی بدون ADMIN_IDS می‌شکند.** `seed_products()` مقدار `creator_id=None` می‌سازد، در حالی که ستون `products.creator_id`، `NOT NULL` است. این خطا در تست clean database مشاهده شد. مقدار `ADMIN_IDS` در env باید حتماً ست شود و بهتر است خود کد نیز seed را بدون owner رد یا owner سیستم بسازد.
2. **خرید Mini App با خرید بات هم‌تراز نیست.** `app_api.py` در `/api/app/buy/{pid}` موجودی و فروش را تغییر می‌دهد، ولی transactionهای خرید/فروش، `products_sold`، referral share و capo override را ثبت/اعمال نمی‌کند. نتیجه: wallet/analytics/leaderboard و گزارش‌ها برای دو مسیر متفاوت می‌شوند.
3. **فایل‌های آپلودی عمومی‌اند.** route عمومی `/media/{fpath:path}` هیچ auth یا purchase check ندارد و API عمومی نیز `file_path` را در JSON برمی‌گرداند. فایل محصول در صورت حدس/افشای مسیر، قابل دانلود است؛ باید فایل دیجیتال با endpoint احراز‌شده و check خرید تحویل شود و فقط تصویرهای public از `/media` آزاد باشند.
4. **A2A احراز هویت اجباری ندارد.** اگر `A2A_PORT` روشن و `A2A_TOKEN` خالی باشد، هر کلاینت شبکه می‌تواند endpoint هوش مصنوعی را صدا بزند و هزینه/داده ایجاد کند. در production باید نبود token باعث fail-closed شود.
5. **`APP_DEV_LOGIN=1` خطرناک است.** در این حالت کاربر می‌تواند یک Telegram ID دلخواه به عنوان login بفرستد؛ این فقط باید برای dev local بماند و در deployment با guard/deny صریح بسته شود.
6. **local sandbox مرز امنیتی نیست.** `sandbox_mode=local` کد Python را روی host اجرا می‌کند. اگر `sandbox_for_users=1` شود یا تنظیمات اشتباه باشند، عملاً مسیر اجرای کد روی سرور باز می‌شود. فقط Docker با network off و محدودیت منابع یا سرویس sandbox واقعی مناسب است.

### Medium / مهم
7. دو endpoint مدیریت hunter در وب باگ اجرایی دارند: در `admin_hunter_add` عبارت `me=None` به دسترسی نامعتبر می‌رسد؛ در `admin_hunter_perm` نام `database` بدون import استفاده شده است.
8. `app_api.app_buy` برای file URL فقط basename را برمی‌گرداند؛ فایل‌های داخل subdirectory ممکن است لینک خراب یا ambiguous داشته باشند.
9. migrationها در چند جا با `except Exception: pass` بلعیده می‌شوند؛ خطای schema می‌تواند تا زمان وقوع feature پنهان بماند. migration versioning و fail-fast لازم است.
10. `reviewed_by=0` در مسیر وب، هویت واقعی ادمین را در audit/finance ثبت نمی‌کند.
11. خرید/task/create و بعضی rewardها باید با transaction/ledger واحد و تست رقابت هم پوشش داده شوند؛ SQLite guardهای فعلی خوب شروع شده‌اند ولی تمام side effectها اتمیک نیستند.

## نصب و اجرای انجام‌شده در CLI

کارهایی که انجام شد:

1. clone از GitHub در `/home/user/DropAgentXBot`.
2. ساخت virtualenv محلی `.venv` و نصب موفق `requirements.txt`.
3. `pip check`: بدون dependency conflict.
4. `python -m compileall -q .`: موفق.
5. import smoke test برای ماژول‌های اصلی: موفق؛ build اپ با ۷۴ route موفق.
6. اجرای smoke database با env تست: موفق و کاربر آزمایشی credit اولیه گرفت.
7. اجرای dashboard روی `0.0.0.0:8080`: موفق؛ `GET /healthz`، catalog عمومی و login/admin stats پاسخ دادند. یک live preview از داشبورد اجراست.

### محدودیت اجرای واقعی

بات Telegram را عمداً با token جعلی اجرا نکردم. اجرای `python bot.py` بدون `BOT_TOKEN` طبق انتظار با پیام «BOT_TOKEN تنظیم نشده» متوقف می‌شود. برای اجرای واقعی باید `.env` را با `BOT_TOKEN`، `ADMIN_IDS` و در صورت نیاز `AI_API_KEY`/walletها پر کرد. live preview فعلی با دیتابیس و رمز **test-only** در `/tmp` است و داده واقعی شما نیست.

## روش برآورد قیمت کد

قیمت زیر **هزینه تقریبی بازسازی/جایگزینی کد** است، نه قیمت قطعی فروش. برای هر فایل بر اساس پیچیدگی، نوع فایل و تعداد خطوط، نرخ blended حدود **$0.35 تا $2.40 برای هر خط فیزیکی** اعمال و به نزدیک‌ترین $50 گرد شده است؛ تست، طراحی محصول، نگهداری، زیرساخت، API bill، کاربر/درآمد و مالکیت برند در آن نیست.

- ارزش جایگزینی تقریبی کل کد: **$39,500**
- Backend/Python: **$26,500**
- Frontend (JS/HTML/CSS): **$12,500**
- Docs/config/scripts: **$500**
- ارزش فروش as-is بدون کاربر/درآمد: حدود **$8,000 تا $15,000**؛ به تمیزی مالکیت، demo، تعداد مشتری و اصلاح یافته‌های High وابسته است.
- بودجه سخت‌سازی تا سطح قابل اتکا برای پول واقعی: حدود **$10,000 تا $20,000** علاوه بر کد فعلی.

## قیمت تقریبی هر فایل

| فایل | خط | غیرخالی | برآورد جایگزینی |
|---|---:|---:|---:|
| `.dockerignore` | 14 | 14 | $50 |
| `.env.example` | 79 | 66 | $50 |
| `.gitignore` | 21 | 17 | $50 |
| `DEPLOY.md` | 57 | 45 | $50 |
| `Dockerfile` | 29 | 21 | $50 |
| `README.md` | 165 | 130 | $50 |
| `_fix_guards.py` | 50 | 47 | $50 |
| `a2a_server.py` | 78 | 62 | $100 |
| `ai_agent.py` | 270 | 221 | $550 |
| `ai_probe.py` | 273 | 242 | $400 |
| `app_api.py` | 954 | 882 | $2,100 |
| `bot.py` | 164 | 140 | $250 |
| `config.py` | 89 | 73 | $100 |
| `cron_jobs.py` | 179 | 147 | $250 |
| `database.py` | 1,758 | 1,480 | $4,200 |
| `docker-compose.yml` | 16 | 15 | $50 |
| `fleet.py` | 255 | 218 | $500 |
| `handlers/__init__.py` | 25 | 24 | $50 |
| `handlers/admin.py` | 1,120 | 948 | $2,150 |
| `handlers/ai_chat.py` | 1,042 | 865 | $2,000 |
| `handlers/help.py` | 302 | 253 | $550 |
| `handlers/marketplace.py` | 740 | 646 | $1,400 |
| `handlers/org.py` | 233 | 202 | $450 |
| `handlers/products.py` | 812 | 697 | $1,550 |
| `handlers/profile.py` | 169 | 143 | $300 |
| `handlers/referral.py` | 197 | 168 | $350 |
| `handlers/start.py` | 181 | 156 | $350 |
| `handlers/tasks.py` | 355 | 295 | $650 |
| `handlers/wallet.py` | 462 | 386 | $900 |
| `hermes_engine.py` | 624 | 551 | $1,250 |
| `install.sh` | 23 | 20 | $50 |
| `mcp_lite.py` | 136 | 115 | $200 |
| `media_ai.py` | 117 | 103 | $200 |
| `memory.py` | 507 | 436 | $1,000 |
| `platform_settings.py` | 86 | 77 | $100 |
| `platforms.py` | 44 | 35 | $50 |
| `requirements.txt` | 10 | 8 | $50 |
| `run.bat` | 36 | 30 | $50 |
| `sandbox.py` | 119 | 103 | $200 |
| `skills.py` | 377 | 305 | $750 |
| `tools.py` | 258 | 231 | $500 |
| `utils.py` | 349 | 300 | $400 |
| `web/_backup_20260825-0053/admin.html` | 390 | 371 | $350 |
| `web/_backup_20260825-0053/login.html` | 46 | 46 | $50 |
| `web/_backup_20260825-0053/storefront.html` | 171 | 156 | $150 |
| `web/admin.html` | 975 | 946 | $900 |
| `web/app/css/design-system.css` | 160 | 144 | $150 |
| `web/app/css/pages.css` | 124 | 115 | $100 |
| `web/app/index.html` | 57 | 55 | $50 |
| `web/app/js/core/api.js` | 172 | 160 | $200 |
| `web/app/js/core/router.js` | 64 | 61 | $50 |
| `web/app/js/core/tg.js` | 62 | 54 | $50 |
| `web/app/js/core/ui.js` | 107 | 99 | $100 |
| `web/app/js/pages/activity.js` | 50 | 46 | $50 |
| `web/app/js/pages/agent.js` | 58 | 54 | $50 |
| `web/app/js/pages/create.js` | 215 | 200 | $250 |
| `web/app/js/pages/explore.js` | 74 | 68 | $100 |
| `web/app/js/pages/home.js` | 121 | 112 | $150 |
| `web/app/js/pages/product.js` | 86 | 79 | $100 |
| `web/app/js/pages/profile.js` | 94 | 87 | $100 |
| `web/app/js/pages/search.js` | 65 | 61 | $50 |
| `web/app/js/pages/wallet.js` | 69 | 59 | $100 |
| `web/login.html` | 137 | 132 | $100 |
| `web/senpai/app.css` | 2,777 | 2,710 | $2,350 |
| `web/senpai/app.html` | 673 | 630 | $600 |
| `web/senpai/app.js` | 4,450 | 4,165 | $6,000 |
| `web/storefront.html` | 413 | 393 | $350 |
| `web_admin.py` | 1,064 | 916 | $2,350 |
| `webtools.py` | 158 | 137 | $300 |

### دارایی غیرکدی

- `DropAgentXBot.jpg` و `web/app/assets/logo.jpg`: دو کپی باینری از یک تصویر، مجموعاً حدود ۲۶۰KB؛ ارزش کدگذاری جداگانه ندارند و فقط asset/branding محسوب می‌شوند.

## اولویت اصلاح پیشنهادی

1. محافظت فایل و حذف `file_path` از public JSON.
2. یکسان‌سازی checkout بات و Mini App با ledger/transaction service واحد.
3. اجباری کردن A2A token، بستن dev login، Docker-only sandbox و افزودن HTTPS/2FA.
4. رفع hunter endpoints، seed بدون admin، port mapping/reverse proxy.
5. افزودن تست‌های concurrency برای buy/task/withdraw/deposit، API auth tests و CI با dependency lock.
6. سپس audit مستقل مالی/امنیتی و deploy آزمایشی با داده ساختگی.

_این گزارش بر اساس کد موجود در commit بررسی‌شده و smoke test محلی تهیه شده است؛ قیمت‌ها تخمینی‌اند و جای ارزیابی حقوقی/حسابرسی امنیتی/ارزش‌گذاری کسب‌وکار را نمی‌گیرند._
