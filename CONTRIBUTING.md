# 🤝 Contributing to DropAgentX

DropAgentX از مشارکت شما استقبال می‌کند! 🎉

## 🚀 شروع سریع

```bash
# 1) Fork + Clone
git clone https://github.com/<your-user>/DropAgentXmain.git
cd DropAgentXmain

# 2) محیط مجازی
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3) نصب dependencies
pip install -r requirements-dev.txt

# 4) فایل env
cp .env.example .env
# BOT_TOKEN و ADMIN_IDS رو پر کن

# 5) تست‌ها
pytest
```

## 📋 قوانین مشارکت

### 🔀 Branch Naming
- `feature/<name>` — قابلیت جدید
- `fix/<name>` — رفع باگ
- `docs/<name>` — تغییرات مستندات
- `refactor/<name>` — بازنویسی بدون تغییر عملکرد

### ✅ قبل از Pull Request
1. **تست‌ها پاس بشن:** `pytest -q`
2. **Compile بدون خطا:** `python -m compileall -q .`
3. **Dependency check:** `pip check`
4. **کد تمیز:** `ruff check .` (اختیاری ولی توصیه‌شده)
5. **هیچ secret در کد نباشه** — فقط `.env.example` آپدیت بشه

### 📝 Commit Messages
از فرمت زیر استفاده کنید:
```
<emoji> <type>: <description>

🐛 fix: رفع مشکل خرید محصول
✨ feat: اضافه کردن فیلتر جستجو
📝 docs: بروزرسانی README
♻️ refactor: بازنویسی hermes_engine
🧪 test: اضافه کردن تست‌های wallet
🐳 docker: بهبود Dockerfile
```

### 🏗️ ساختار پروژه
```
bot.py              نقطه ورود اصلی بات
config.py           تنظیمات (از .env)
database.py         لایه دیتابیس (SQLite + aiosqlite)
hermes_engine.py    موتور AI (CLI/HTTP/API)
handlers/           هندلرهای بات تلگرام
shared/             ماژول‌های مشترک (security, llm, context)
gateway/            API Gateway
web/                فرانت‌اند (vanilla JS)
web-next/           فرانت‌اند (Next.js)
deploy/             فایل‌های استقرار Docker
tests/              تست‌ها (pytest)
```

## 🔒 امنیت

- **هرگز** فایل `.env` یا کلید API را کامیت نکنید
- تغییرات امنیتی را از طریق [Security Advisories](../../security/advisories) گزارش دهید
- `shared/security/skills_guard.py` را برای هر skill جدید بررسی کنید

## 🐛 گزارش باگ

از [Issues](../../issues) با اطلاعات زیر استفاده کنید:
- نسخه DropAgentX (مثلاً v3.0.0)
- مراحل بازتولید
- خروجی خطا (بدون اطلاعات حساس!)
- محیط (Python version, OS)

## 📜 لایسنس

با مشارکت در این پروژه، موافقت می‌کنید که کد شما تحت [لایسنس MIT](LICENSE) منتشر شود.

---

ممنون از مشارکت شما! 💙
