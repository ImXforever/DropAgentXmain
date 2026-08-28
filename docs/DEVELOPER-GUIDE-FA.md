# 🧑‍💻 راهنمای توسعه‌دهنده

## افزودن یک هندلر جدید
1. `handlers/xxx.py` → `router = Router()`
2. ثبت در `handlers/__init__.py` (ایمپورت + all_routers)
3. قانون‌ها: FSM با StatesGroup · همه‌جا edit_safe · callback پارس با try/except
4. تست: `tests/test_xxx.py` با فیکسچر isolated_db (کپی الگوی test_v4_modules.py)

## افزودن تیبل/مایگریشن
- CREATE در `init_db` (idempotent با IF NOT EXISTS)
- فقط `ALTER TABLE ADD COLUMN` در بلوک مایگریشن — با try/except per-statement
- هرگز نوع ستون عوض نکن — ستون جدید اضافه کن

## سقف‌های ظرفیت (دیتابیس ۵۰۰MB)
- چت: ۲۵ پیام × ۲۰۰۰/۱۵۰۰ کاراکتر · FTS فقط کاربر · sweep هفتگی راکدها
- متن‌های کاربر هرگز بدون سقف INSERT نشوند (`[:N]` در همه insertها)
- ریتین‌ها: app_logs ۱۴روز/۵۰k · فستی‌ها TTL · cron شبانه

## اجرا و تست
```bash
python -m pytest tests/ -q          # ۶۲ تست
python tools_capacity_sim.py        # شبیه‌سازی ۸۰۰۰ کاربر
python tools_seed_demo.py           # داده دمو برای اسکرین‌شات
```

## چک‌لیست PR
- [ ] py_compile کل ریپو · [ ] pytest ۶۲/۶۲ · [ ] بدون import استفاده‌نشده
- [ ] متن‌های کاربر esc/سقف‌دار · [ ] پول فقط از update_credits
- [ ] متن‌های UI فارسی + دکمه‌محور (بدون فرمت تایپی سخت)
