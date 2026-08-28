# 🚀 استقرار روی VPS

## پیش‌نیازها
- VPS اوبونتو 22/24 با حداقل 1GB RAM
- دامنه لازم نیست (polling خروجی است، پورت هم لازم ندارد!)

## راه‌اندازی در ۴ قدم

```bash
ssh root@YOUR_VPS_IP

# ۱) نصب داکر + پروژه
apt update && apt install -y git
git clone <repo-url> /opt/hermes-marketplace && cd /opt/hermes-marketplace
bash install.sh

# ۲) فایل env را پر کن
nano .env     # BOT_TOKEN, ADMIN_IDS, AI_* , WALLET_*

# ۳) اجرا
docker compose up -d --build

# ۴) لاگ زنده
docker compose logs -f
```

## آپدیت نسخه جدید
```bash
cd /opt/hermes-marketplace
git pull
docker compose up -d --build
```

## دستورات مفید
```bash
docker compose ps              # وضعیت
docker compose logs -f --tail 100
docker compose restart
docker compose down            # توقف کامل
sqlite3 data/marketplace.db    # دسترسی مستقیم دیتابیس
```

## ⚠️ نکته حیاتی
بات فقط باید **یک جا** اجرا شود! اگر روی VPS بالا آمد، نسخه ویندوزی محلی را خاموش کن
(دو polling با یک توکن = خطای 409 Conflict).

## بکاپ روزانه خودکار (اختیاری)
```bash
crontab -e
# اضافه کن:
0 3 * * * cd /opt/hermes-marketplace && sqlite3 data/marketplace.db ".backup data/backup-$(date +\%F).db" && find data -name 'backup-*.db' -mtime +7 -delete
```

## گزارش روزانه
متغیر `DAILY_REPORT_HOUR` در `.env` ساعت ارسال گزارش به ادمین‌هاست (پیش‌فرض ۹ صبح به وقت سرور).
برای تهران: سرور را روی timezone ایران ست کن یا عدد مناسب بگذار:
`timedatectl set-timezone Asia/Tehran`

## Hardening v2 — production checklist

قبل از فعال‌کردن `TREASURY_AUTO_ENABLED=1`:

1. برای هر شبکه RPC/indexer و آدرس توکن USDT را تنظیم کن.
2. مقدار `CHAIN_CONFIRMATIONS` و مقدار اختصاصی هر شبکه را بررسی کن.
3. `PAYOUT_API_URL` را به signer/custody service دارای idempotency وصل کن؛ private key را داخل این پروژه قرار نده.
4. `APP_ENV=production`، `APP_DEV_LOGIN=0`، `COOKIE_SECURE=1` و `A2A_TOKEN` قوی بگذار.
5. پشت Caddy/Nginx با HTTPS اجرا کن و در صورت استفاده از Compose پورت `WEB_PORT` را publish کن.
6. ابتدا با تراکنش‌های staging و دیتابیس آزمایشی، duplicate TX، reorg، underpayment، retry و payout timeout را تست کن.

## Next.js web experience

The new frontend is in `web-next/`. It runs as a separate service so the existing
Telegram backend can be migrated without a flag day:

```bash
cd web-next
npm ci
npm run dev       # local preview on :3000
npm run lint
npm run build
```

Compose runs it as `dropagentx-web` on port `3000` and proxies relative
`/backend/*` requests to the Python service. Set `BACKEND_URL` in a separate
hosting environment when deploying Next.js to Railway or another platform.
The browser never calls `localhost` directly.
