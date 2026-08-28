# گزارش Hardening v2 — DropAgentXBot

تاریخ: ۲۷ اوت ۲۰۲۶  
شاخه محلی: `hardening-v2`  
مبنای تغییرات: commit `6f5c2ef`

## تصمیم‌های اعمال‌شده

- شبکه‌ها: TON، BSC، Base، Solana و TRON
- استقرار: Docker Compose و Railway
- Discord: dependency و gateway واقعی اضافه شد
- مجوز: MIT

## آمار شاخه فعلی بعد از Hardening

- ۸۳ فایل tracked: ۸۱ فایل متنی/کدی + ۲ تصویر
- ۲۷٬۰۸۹ خط فیزیکی متن/کد و مستندات
- ۲۴٬۲۵۰ خط غیرخالی
- ۷۵ route در build وب فعلی؛ شامل route جدید اجرای یک‌باره treasury
- تغییرات در commit محلی `9a8e513` ثبت شده است.

## مواردی که برطرف شد

### امنیت و دسترسی

- مسیر عمومی `/media` دیگر هر فایل موجود در `UPLOAD_DIR` را سرو نمی‌کند.
- فایل دیجیتال فقط برای Mini App user دارای purchase معتبر تحویل می‌شود.
- `file_path` و مسیرهای داخلی از public catalog/product JSON حذف شدند.
- URL تحویل فایل برای فایل‌های تو در تو درست تولید می‌شود.
- `A2A_TOKEN` اجباری و fail-closed شد.
- `APP_DEV_LOGIN` فقط با هر دو فلگ `APP_ENV=dev|test|local` و `APP_DEV_LOGIN=1` فعال می‌شود.
- cookieها در Production به‌صورت `Secure` تنظیم می‌شوند.
- Sandbox روی host در Production بسته است؛ Docker با `network=none` مسیر پیش‌فرض امن است.
- foreign keyهای SQLite فعال شدند.

### Commerce و مالی

- خرید Telegram و Mini App از primitive مشترک `commerce.py` استفاده می‌کنند.
- خرید، جلوگیری از خرید تکراری، شرط موجودی، commission، ledger، `sales_count` و
  `products_sold` در یک تراکنش اتمیک انجام می‌شود.
- Referral share، capo override و promotion از مسیر مشترک اجرا می‌شود.
- مصرف coupon داخل تراکنش خرید انجام می‌شود تا در صورت شکست خرید، coupon نسوزد.
- approve دستی deposit و refund برداشت ردشده اتمیک شدند.
- در صورت شکست ایجاد withdrawal، hold موجودی آزاد می‌شود.
- پرداخت Telegram Stars وضعیت محصول، مبلغ invoice، duplicate payment و `total_earned`
  را کنترل می‌کند.
- پرداخت موفق withdrawal، `has_withdrawn` را ثبت می‌کند.

### Blockchain و payout

`blockchain.py` اضافه شد و verification خواندنی برای این مسیرها دارد:

- EVM: BSC و Base با `eth_getTransactionReceipt`، log مربوط به ERC-20 Transfer،
  contract address و confirmation count
- TRON: TronGrid و TRC-20 Transfer event
- Solana: JSON-RPC `getTransaction` و token balance delta
- TON: indexer نرمال‌شده Jetton transfers

`treasury_worker.py` اضافه شد:

- depositهای pending را دوره‌ای بررسی می‌کند.
- فقط تراکنش موفق، مقصد درست، توکن درست، مبلغ کافی و confirmation کافی را approve می‌کند.
- retry و idempotency از طریق unique TXID و status transition کنترل می‌شود.
- payout را به provider خارجی با `Idempotency-Key` می‌فرستد.
- private key عمداً داخل بات قرار نگرفته است؛ signer/custody provider باید در
  `PAYOUT_API_URL` پیاده‌سازی شود و `{ok:true,txid}` برگرداند.

این یعنی **معماری پرداخت خودکار آماده و fail-closed است**؛ برای ارسال پول واقعی
باید RPC/indexer، آدرس توکن‌ها، walletها و payout signer واقعی تنظیم شوند.

### کیفیت و عملیات

- `requirements.lock` و `requirements-dev.lock` اضافه شدند.
- تست‌های pytest/async اضافه شدند.
- GitHub Actions در `.github/workflows/ci.yml` اضافه شد.
- `LICENSE` با MIT اضافه شد.
- Compose پورت `${WEB_PORT:-8080}` را publish می‌کند و `init: true` دارد.
- `MEDIA_BASE_URL` و `MEDIA_API_KEY` برای provider مستقل Image/STT/TTS اضافه شدند؛
  بنابراین OpenRouter برای text می‌ماند و media می‌تواند از provider سازگار جداگانه استفاده کند.
- `admin_hunter_add` و `admin_hunter_perm` اصلاح شدند.
- doctor پنل، تنظیمات ناقص treasury را گزارش می‌کند.

## تست‌های اجراشده

```text
python -m compileall -q .    OK
pytest -q                    5 passed
pip check                    No broken requirements found
```

همچنین smoke test محلی انجام شد:

- ساخت دیتابیس خالی بدون `ADMIN_IDS` دیگر crash نمی‌کند.
- build اپ وب موفق شد.
- routeهای public و admin تست شدند.
- catalog عمومی دیگر `file_path` را برنمی‌گرداند.
- دسترسی فایل بدون purchase با HTTP 403 رد شد.
- دسترسی فایل با signed Mini App cookie و purchase معتبر موفق شد.

## مواردی که عمداً به credential واقعی وابسته مانده‌اند

1. `BOT_TOKEN` واقعی برای polling تلگرام
2. RPC و token contract/mint واقعی هر شبکه
3. `TON_INDEXER_URL` معتبر برای Jetton transfer API
4. `PAYOUT_API_URL` و signer/custody سرویس دارای idempotency
5. `AI_API_KEY` و در صورت نیاز `MEDIA_API_KEY`
6. `DISCORD_TOKEN` و فعال‌سازی Message Content Intent در Discord Developer Portal
7. دامنه و HTTPS برای Railway/VPS

بدون این credentialها، کد به‌صورت fail-closed اجرا می‌شود و credit یا payout جعلی
ایجاد نمی‌کند.

## نحوه اجرا

### Local

```bash
cp .env.example .env
# BOT_TOKEN، ADMIN_IDS، AI_* و تنظیمات لازم را پر کن
python -m pip install -r requirements-dev.txt
pytest
python bot.py
```

### Docker

```bash
docker compose up -d --build
docker compose logs -f
```

برای فعال‌سازی خودکار خزانه، بعد از تست staging:

```env
TREASURY_AUTO_ENABLED=1
APP_ENV=production
COOKIE_SECURE=1
A2A_PORT=9000
A2A_TOKEN=یک-توکن-قوی
```

## محدودیت این اجرای Agent

روی GitHub یک fork عمومی/push انجام ندادم، چون دسترسی GitHub کاربر در این محیط
وجود ندارد. معادل fork به‌صورت branch محلی `hardening-v2` ساخته شده و تمام تغییرات
در `/home/user/DropAgentXBot` قرار دارد. برای انتشار:

```bash
git remote add hardened https://github.com/YOUR_ACCOUNT/DropAgentXBot.git
git push -u hardened hardening-v2
```

## Next.js VisionWEB expansion

بر اساس فایل پیوست `VisionWEB.txt`، اپلیکیشن جدید در `web-next/` ساخته شد:

- Next.js App Router + TypeScript + Tailwind/PostCSS
- responsive mobile-first shell با RTL فارسی
- Home، Stories، Feed، Explore، Marketplace، Create Studio، Profile، Messages، Wallet، Orders، Saved، Collections، Analytics، Settings و Admin
- تعامل‌های واقعی داخل demo: like، save، follow، publish، search، cart و theme switch
- Feature Lab با **دقیقاً ۱۰۰ قابلیت** در چهار گروه Social Graph، Commerce Engine، Creator Economy و Platform Layer
- proxy امن `/backend/*` برای اتصال آینده به Python API با `BACKEND_URL`
- Dockerfile مستقل و سرویس `dropagentx-web` در Compose روی port 3000
- `npm run lint` موفق
- `npm run build` موفق

این نسخه «لایه محصول/Frontend قابل اجرا» است؛ برای وسعت واقعی Instagram باید در فازهای بعدی
PostgreSQL، Redis، S3/CDN، queue، search index، realtime gateway و APIهای production برای
همین ۱۰۰ قابلیت متصل شوند. Demo data عمداً local است و بدون credential قابل مشاهده است.
