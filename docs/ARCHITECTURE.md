# 🏗 معماری DropAgentX v4.0.0

## نقشه ماژول‌ها
```
bot.py                     ورود: دیسپچر + هندلر خطای سه‌منبعی + observability hooks
config.py                  همه تنظیمات از env (dataclass Config)
database.py (2,700+ خط)    لایه داده: ۳۰+ تیبل، مایگریشن خودکار، بخش‌های:
                           · Commerce (خرید، کمیسیون، کد تخفیف سربازی)
                           · Referral (مسترلینگ، جعبه‌شانس)
                           · v2.0 Capacity (14 ابزار نگهداری)
                           · v3.5 Growth (بونوس روزانه، promo، win-back)
                           · v4.0 Tickets/Quests/Reports/Analytics
handlers/ (15 روتر)        start · tasks · products · marketplace · ai_chat · wallet
                           referral · profile · help · org · admin · admin_v2
                           growth · quests · support
hermes_engine.py           مغز AI: چندمدلی، redact secrets، dynamic settings
memory2.py                 حافظه ۷فستی با وزن/زوال/استخراج LLM
observability.py           لاگ JSON + app_logs + ErrorCapture middleware
identity_rl.py             Q-learning هویت کاربر (۷ برچسب)
gateway/ + shared/         مونوریپو: روتر LLM، فشرده‌ساز کانتکست، skills_guard
```

## جریان داده (خريد تا تحويل)
```
کاربر → marketplace (کارت محصول) → commerce.purchase_with_credits
  → تراکنش ATOMIC (کردیت، کمیسیون پلتفرم، کمیسیون ریفرال)
  → تحویل: file_fileid تلگرام → فالبک دیسک → کپشن امن ۱۰۲۴ + توضیح تکه‌۴۰۹۶
  → دکمه ⭐ امتیاز (v3.5) → reviews → میانگین در analytics فروشنده (v4)
```

## قراردادهای مهم
- **هر پیام کاربر**: `get_or_create_user` → last_seen (سبک، ۱۵دقیقه‌ای)
- **ارسال متن**: فقط `send_safe`/`edit_safe` (فالبک دولایه parse_mode)
- **callbackها**: همیشه try/except پارس + `callback.answer` بازخورد
- **پول**: فقط `update_credits` (تراکنش + ثبت ledger) — هرگز UPDATE مستقیم
- **مایگریشن**: فقط `ALTER TABLE ... ADD COLUMN` با try در init_db — idempotent
- **ماموریت‌ها**: خودمحاسبه از تیبل‌های واقعی (بدون هوک) → بدون ریسک ناسازگاری
