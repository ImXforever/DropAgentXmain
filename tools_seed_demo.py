#!/usr/bin/env python3
"""v4.0.0: داده دمو برای اسکرین‌شات لانچ — python tools_seed_demo.py"""
import asyncio, os, sys, time, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config  # noqa

random.seed(42)
NAMES = [("Ali", "علی"), ("Sara", "سارا"), ("Reza", "رضا"), ("Nima", "نیما"),
         ("Mina", "مینا"), ("Amir", "امیر"), ("Hana", "هانا"), ("Kian", "کیان")]
PRODUCTS = [
    ("پک ۲۰۰ پرامپت حرفه‌ای AI", "مجموعه کامل پرامپت برای چت‌جی‌پی‌تی و کلاد — دسته‌بندی‌شده", 150),
    ("دوره فریلنسری صفر تا صد", "قدم‌به‌قدم درآمد دلاری از فریلنسری + قالب‌های قرارداد", 400),
    ("قالب‌های کانستانت کنتکت", "۵۰ قالب استوری و پست آماده برای کسب‌وکار", 120),
    ("کتاب مارکتینگ تلگرام", "راهنمای عملی رشد کانال و فروش در تلگرام", 200),
]
TASKS = [
    ("عضویت در کانال رسمی", "subscribe", "https://t.me/dropagentx", 5, 1000),
    ("فالو پیج اینستاگرام", "follow", "https://instagram.com/dropagentx", 8, 500),
]


async def main():
    import database as db
    await db.init_db()
    print("── ساخت کاربران دمو ──")
    for i, (u, f) in enumerate(NAMES, 10):
        await db.create_user(user_id=i, username=f"demo_{u.lower()}", first_name=f)
        await db.update_credits(i, random.randint(100, 900), "demo_seed", "داده دمو")
    print(f"OK {len(NAMES)} کاربر")
    admin = config.ADMIN_IDS[0] if config.ADMIN_IDS else 10
    print("── محصولات دمو (ادمین) ──")
    async with db.raw_db() as con:
        for i, (t, dsc, price) in enumerate(PRODUCTS, 1):
            await con.execute(
                "INSERT OR IGNORE INTO products (id, creator_id, title, description, price_credits, "
                "status, views, impressions, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (i, admin, t, dsc, price, "approved", random.randint(50, 400),
                 random.randint(100, 800), time.time()))
        await con.commit()
    print(f"OK {len(PRODUCTS)} محصول (تأییدشده)")
    print("── تسک‌های دمو ──")
    async with db.raw_db() as con:
        for t, tt, url, c, mx in TASKS:
            await con.execute(
                "INSERT OR IGNORE INTO tasks (title, task_type, target_url, credits_reward, "
                "max_completions, creator_id) VALUES (?,?,?,?,?,?)", (t, tt, url, c, mx, admin))
        await con.commit()
    print(f"OK {len(TASKS)} تسک")
    print("\n🎉 داده دمو آماده — برای پاک‌سازی: demo_* و محصول‌های ۱-۴ را حذف کن")


if __name__ == "__main__":
    asyncio.run(main())
