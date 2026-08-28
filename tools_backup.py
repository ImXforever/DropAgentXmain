#!/usr/bin/env python3
"""v4.0.0: بک‌اپ امن CLI — sqlite3 .backup بدون داون‌تایم + CSV مخاطبان
   مصرف: python tools_backup.py [مسیرخروجی پیش‌فرض backups/]"""
import asyncio, csv, os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config  # noqa


def safe_backup(db_path: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(out_dir, f"marketplace-{stamp}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)          # API رسمی — سازگار با WAL، بدون قفل طولانی
    dst.close(); src.close()
    return dest


def users_csv(db_path: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(out_dir, f"users-{stamp}.csv")
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT user_id, first_name, username, credits, total_earned, referred_by, "
        "is_banned, role, created_at FROM users ORDER BY user_id").fetchall()
    con.close()
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "first_name", "username", "credits", "total_earned",
                    "referred_by", "banned", "role", "joined_at"])
        w.writerows(rows)
    return dest, len(rows)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "backups"
    dbp = config.DB_PATH
    if not os.path.exists(dbp):
        print(f"دیتابیس پیدا نشد: {dbp}")
        sys.exit(1)
    db = safe_backup(dbp, out)
    print(f"✓ بک‌اپ DB: {db} ({os.path.getsize(db):,} بایت)")
    csvp, n = users_csv(dbp, out)
    print(f"✓ CSV مخاطبان: {csvp} ({n} کاربر)")
    print("💡 این فایل‌ها را جای امن (خارج سرور) ذخیره کن.")
