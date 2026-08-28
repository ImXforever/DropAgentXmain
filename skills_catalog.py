"""Skills Hub: pre-built skill catalog, usage tracking, and management.

Inspired by Hermes Agent's skills system with:
  - 15 built-in skill categories → 8 practical skills for DropAgentX
  - Skill catalog with install/uninstall
  - Usage tracking per skill
  - Search across catalog and installed skills
  - Hermes SKILL.md format with YAML frontmatter

Catalog lives as in-code BUILTIN_SKILLS dict (no network dependency).
Users can install/uninstall from the catalog with one command.
"""

import asyncio
import os
import re
import time

from skills import SKILL_DIR, _safe, _skill_file, parse_frontmatter, _scan_sync

# =========================================================
# Built-in Skill Catalog
# =========================================================

BUILTIN_SKILLS: dict[str, dict] = {
    "selling-tips": {
        "category": "ecommerce",
        "description": "راهنمای فروش در مارکت‌پلیس: قیمت‌گذاری، توضیحات فروشنده‌پسند و پاسخ به مشتری",
        "tags": ["فروش", "قیمت‌گذاری", "مارکت‌پلیس"],
        "version": "2.1.0",
        "author": "DropAgentX",
    },
    "product-copywriting": {
        "category": "ecommerce",
        "description": "نوشتن متن تبلیغاتی جذاب برای محصولات دیجیتال با فرمول‌های اثبات‌شده",
        "tags": ["محتوا", "تبلیغ", "توضیحات"],
        "version": "1.0.0",
        "author": "DropAgentX",
    },
    "crypto-trading": {
        "category": "finance",
        "description": "راهنمای ترید رمزارز: تحلیل تکنیکال، مدیریت ریسک و استراتژی‌های ورود/خروج",
        "tags": ["ترید", "کریپتو", "تحلیل"],
        "version": "1.2.0",
        "author": "DropAgentX",
    },
    "python-advanced": {
        "category": "coding",
        "description": "پترن‌های پیشرفته پایتون: async, decorators, metaclasses, dataclasses و بهینه‌سازی",
        "tags": ["پایتون", "پترن", "بهینه‌سازی"],
        "version": "1.1.0",
        "author": "DropAgentX",
    },
    "telegram-bot-dev": {
        "category": "coding",
        "description": "ساخت و توسعه بات تلگرام: FSM، inline keyboards، webhooks، Mini Apps و استقرار",
        "tags": ["تلگرام", "بات", "آیوگرام"],
        "version": "1.0.0",
        "author": "DropAgentX",
    },
    "web-scraping": {
        "category": "data",
        "description": "استخراج و پردازش داده از وب: HTML parsing، anti-bot evasion، و ذخیره‌سازی",
        "tags": ["وب", "اسکرپینگ", "داده"],
        "version": "1.0.0",
        "author": "DropAgentX",
    },
    "api-design": {
        "category": "coding",
        "description": "اصول طراحی REST API حرفه‌ای: امنیت، مستندات، rate limiting و versioning",
        "tags": ["api", "rest", "امنیت"],
        "version": "1.0.0",
        "author": "DropAgentX",
    },
    "data-analysis": {
        "category": "data",
        "description": "تحلیل داده با پایتون: pandas, numpy, matplotlib و گزارش‌گیری خودکار",
        "tags": ["داده", "تحلیل", "گزارش"],
        "version": "1.0.0",
        "author": "DropAgentX",
    },
}

# =========================================================
# Built-in SKILL.md content templates
# =========================================================

_BUILTIN_CONTENT: dict[str, str] = {
    "selling-tips": """---
name: selling-tips
description: "راهنمای فروش در مارکت‌پلیس: قیمت‌گذاری، توضیحات فروشنده‌پسند و پاسخ به مشتری"
version: 2.1.0
tags: [فروش, قیمت‌گذاری, مارکت‌پلیس]
---

# راهنمای فروش در DropAgentX

## قیمت‌گذاری
- نرخ مرجع: ۱۰۰۰ کردیت = ۱ USDT
- آموزش‌های جامع: ۱۵۰۰ تا ۴۵۰۰ کردیت
- قالب‌ها و فایل‌های کوچک: ۵۰۰ تا ۱۵۰۰ کردیت
- قیمت روانی: ۲۴۰۰ از ۲۵۰۰ بهتر می‌فروشد

## توضیحات محصول
- جملهٔ اول: وعدهٔ اصلی («بعد از X می‌توانی Y»)
- ۳-۵ بولت دستاورد واقعی
- آخر: دعوت به اقدام (CTA)

## پاسخ به مشتری
- زیر ۵ دقیقه جواب بده
- ارزش را یادآوری کن، تخفیف آخرین حربه
- کد تخفیف: حداکثر ۳۰٪ و فقط با دلیل منطقی

## بهینه‌سازی لیستینگ
- عنوان: حداکثر ۶۰ کاراکتر، شامل کلمه کلیدی اصلی
- عکس اول: کاور حرفه‌ای با رنگ‌های متمایز
- تگ‌ها: ۳-۵ تگ مرتبط برای جستجو
""",

    "product-copywriting": """---
name: product-copywriting
description: "نوشتن متن تبلیغاتی جذاب برای محصولات دیجیتال"
version: 1.0.0
tags: [محتوا, تبلیغ, توضیحات]
---

# فرمول‌های نوشتار تبلیغاتی

## فرمول AIDA
- Attention: سؤال یا جمله شوکه‌کننده
- Interest: آمار یا داستان کوتاه
- Desire: مزایای ویژه محصول
- Action: دکمه خرید + مهلت زمانی

## فرمول PAS (Problem-Agitate-Solve)
- مشکل را بنویس
- آن را بدتر نشان بده
- محصولت را حل مشکل معرفی کن

## نکات فنی
- از زبان اول شخص (تو/شما) استفاده کن
- اعداد مشخص بهتر از عبارات مبهم هستند
- ۵۰٪ از متن باید مزایا باشد نه ویژگی‌ها
""",

    "crypto-trading": """---
name: crypto-trading
description: "راهنمای ترید رمزارز: تحلیل تکنیکال و مدیریت ریسک"
version: 1.2.0
tags: [ترید, کریپتو, تحلیل]
---

# ⚠️ هشدار: این آموزشی است، نه توصیه سرمایه‌گذاری

## چک‌لیست ورود به معامله
1. تأیید روند (Trend Confirmation)
2. حجم معاملات (Volume Analysis)
3. سطوح حمایت/مقاومت (S/R)
4. مدیریت ریسک: حداکثر ۱٪ بانکرول در هر معامله
5. حد ضرر (Stop Loss) قبل از ورود

## مدیریت سرمایه
- ریسک ثابت: ۱٪ بانکرول
- ریسک پله‌ای: افزایش بعد از +۲R
- بازدهی هدف: حداقل ۲:۱ (Risk:Reward)
""",

    "python-advanced": """---
name: python-advanced
description: "پترن‌های پیشرفته پایتون: async, decorators, dataclasses"
version: 1.1.0
tags: [پایتون, پترن, بهینه‌سازی]
---

# پترن‌های حرفه‌ای پایتون

## Context Managers
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def managed_connection():
    db = await connect()
    try:
        yield db
    finally:
        await db.close()
```

## Singleton Pattern
```python
_instance = None

def get_instance():
    global _instance
    if _instance is None:
        _instance = MyClass()
    return _instance
```

## Classmethod Factory
```python
@classmethod
def from_string(cls, s: str):
    name, age = s.split(',')
    return cls(name=name, age=int(age))
```
""",

    "telegram-bot-dev": """---
name: telegram-bot-dev
description: "توسعه بات تلگرام: FSM، inline keyboards، webhooks"
version: 1.0.0
tags: [تلگرام, بات, آیوگرام]
---

# راهنمای ساخت بات تلگرام با aiogram

## ساختار پروژه
```
bot.py       → نقطه ورود
handlers/    → هندلرها
database.py  → دیتابیس
config.py    → تنظیمات
```

## الگوی FSM
```python
class Form(StatesGroup):
    name = State()
    age = State()

@router.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.set_state(Form.name)
    await msg.answer("نامتو بگو:")
```

## inline keyboards
```python
kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Option 1", callback_data="opt1")]
])
await msg.answer("Choose:", reply_markup=kb)
```
""",

    "web-scraping": """---
name: web-scraping
description: "استخراج و پردازش داده از وب"
version: 1.0.0
tags: [وب, اسکرپینگ, داده]
---

# راهنمای اسکرپینگ وب

## ابزارها
- httpx: درخواست‌های async
- beautifulsoup4: پارس HTML
- playwright: رندر JS

## الگوی امنیتی
```python
import httpx
headers = {"User-Agent": "Mozilla/5.0 ..."}
async with httpx.AsyncClient() as c:
    r = await c.get(url, headers=headers, timeout=30)
    r.raise_for_status()
```

## ضد مسدودسازی
- تأخیر تصادفی ۱-۳ ثانیه بین درخواست‌ها
- Rotate User-Agent
- respect robots.txt
""",

    "api-design": """---
name: api-design
description: "اصول طراحی REST API حرفه‌ای"
version: 1.0.0
tags: [api, rest, امنیت]
---

# طراحی API حرفه‌ای

## اصول REST
- Resources plural: /users, /products
- HTTP methods: GET=read, POST=create, PUT=update, DELETE=delete
- Status codes معنادار: 200, 201, 400, 404, 500

## امنیت
- JWT برای احراز هویت
- Rate limiting per user
- Input validation (Pydantic/FastAPI)
- CORS policy

## مستندات
- OpenAPI/Swagger
- نمونه درخواست/پاسخ
- Error response format
""",

    "data-analysis": """---
name: data-analysis
description: "تحلیل داده با پایتون"
version: 1.0.0
tags: [داده, تحلیل, گزارش]
---

# تحلیل داده با پایتون

## ابزارهای اصلی
- pandas: DataFrame operations
- numpy: محاسبات عددی
- matplotlib/plotly: نمودارها

## الگوی تحلیل
1. بارگذاری داده (CSV, JSON, DB)
2. تمیزکاری (NaN, duplicate, format)
3. تحلیل توصیفی (describe, groupby, pivot)
4. بصری‌سازی (bar, pie, line, heatmap)
5. گزارش نهایی (HTML/PDF)
""",
}


# =========================================================
# Hub operations
# =========================================================

async def hub_list(category: str = "") -> list[dict]:
    """List all catalog skills with install status."""
    installed = {}
    for name in BUILTIN_SKILLS:
        installed[name] = _skill_file(name) is not None

    state_map = {}
    try:
        from skills import _state_map as sm
        state_map = await sm()
    except Exception:
        pass

    catalog = []
    for name, meta in BUILTIN_SKILLS.items():
        if category and meta["category"] != category:
            continue
        catalog.append({
            "name": name,
            "description": meta["description"],
            "tags": meta["tags"],
            "version": meta["version"],
            "author": meta["author"],
            "category": meta["category"],
            "installed": installed.get(name, False),
            "enabled": state_map.get(name, 1) == 1 if installed.get(name) else False,
        })
    return catalog


async def hub_install(name: str) -> tuple[bool, str]:
    """Install a skill from the built-in catalog."""
    n = _safe(name)
    if not n or n not in BUILTIN_SKILLS:
        return False, f"مهارت '{name}' در کاتالوگ وجود ندارد."

    content = _BUILTIN_CONTENT.get(n)
    if not content:
        return False, f"محتوای '{name}' یافت نشد."

    from skills import skill_write
    ok, err = await skill_write(n, content)
    if ok:
        return True, f"✅ مهارت '{n}' با موفقیت نصب شد."
    return False, err or "خطا در نصب."


async def hub_uninstall(name: str) -> tuple[bool, str]:
    """Uninstall a skill."""
    from skills import skill_delete
    ok = await skill_delete(name)
    if ok:
        return True, f"🗑 مهارت '{name}' حذف شد."
    return False, "مهارت پیدا نشد."


async def hub_install_all() -> tuple[int, int]:
    """Install all built-in skills. Returns (success, fail) counts."""
    ok = fail = 0
    for name in BUILTIN_SKILLS:
        success, _ = await hub_install(name)
        if success:
            ok += 1
        else:
            fail += 1
    return ok, fail


async def hub_search(query: str, include_installed: bool = True) -> list[dict]:
    """Search catalog and optionally installed skills."""
    results = []
    catalog = await hub_list()
    tokens = [t.lower() for t in re.findall(r"[\w\u0600-\u06FF]{3,}", query or "")]

    for item in catalog:
        if tokens:
            hay = f"{item['name']} {item['description']} {' '.join(item['tags'])}".lower()
            score = sum(3 for t in tokens if t in hay)
            if score > 0:
                item["_score"] = score
                results.append(item)
        else:
            results.append(item)

    if include_installed:
        installed = await asyncio.to_thread(_scan_sync)
        for name, fm, body, path in installed:
            if any(r["name"] == name for r in results):
                continue
            desc = str(fm.get("description") or "")
            tags = fm.get("tags") or []
            tags_str = " ".join(str(t) for t in tags)
            score = sum(3 for t in tokens if t in f"{name} {desc} {tags_str}".lower()) if tokens else 0
            if score > 0 or not tokens:
                results.append({
                    "name": name, "description": desc, "tags": tags,
                    "installed": True, "_score": score,
                })

    results.sort(key=lambda x: (-x.get("_score", 0), x["name"]))
    for r in results:
        r.pop("_score", None)
    return results[:20]


# =========================================================
# Usage tracking
# =========================================================

async def record_skill_use(name: str):
    """Record that a skill was injected into a prompt."""
    try:
        from database import raw_db
        async with raw_db() as db:
            # ensure uses column exists
            try:
                await db.execute("ALTER TABLE skills_state ADD COLUMN uses INTEGER DEFAULT 0")
            except Exception:
                pass
            await db.execute(
                "INSERT INTO skills_state (name, enabled, uses) VALUES (?, 1, 1) "
                "ON CONFLICT(name) DO UPDATE SET uses = COALESCE(uses, 0) + 1",
                (name,))
            await db.commit()
    except Exception:
        pass


async def skill_stats() -> list[dict]:
    """Get usage stats for all installed skills."""
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS skills_state "
                "(name TEXT PRIMARY KEY, enabled INTEGER DEFAULT 1, uses INTEGER DEFAULT 0)")
            cur = await db.execute(
                "SELECT name, enabled, uses FROM skills_state ORDER BY uses DESC")
            return [{"name": r[0], "enabled": bool(r[1]), "uses": r[2] or 0}
                    for r in await cur.fetchall()]
    except Exception:
        return []
