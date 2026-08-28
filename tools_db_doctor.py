#!/usr/bin/env python3
"""0.5.1: دکتر دیتابیس — سلامت‌سنج CLI (VPS و Railway هر دو)

   python tools_db_doctor.py            # چک کامل
   python tools_db_doctor.py --fix-wal  # checkpoint + کاهش WAL
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config  # noqa


def human(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    db = config.DB_PATH
    issues = []
    if not os.path.exists(db):
        print(f"❌ دیتابیس نیست: {db}")
        return 1
    size = os.path.getsize(db)
    wal = os.path.getsize(db + "-wal") if os.path.exists(db + "-wal") else 0
    total = size + wal + (os.path.getsize(db + "-shm") if os.path.exists(db + "-shm") else 0)
    print(f"🗄 {db}")
    print(f"   main={human(size)}  wal={human(wal)}  total={human(total)}")
    if total > 400 * 1024 * 1024:
        issues.append("حجم کل بالای ۴۰۰MB — VACUUM و آرشیو تراکنش را بزن")

    con = sqlite3.connect(db)
    cur = con.cursor()
    ok = cur.execute("PRAGMA quick_check").fetchone()[0]
    print(f"   quick_check: {ok}")
    if ok != "ok":
        issues.append("quick_check خراب — بک‌اپ فوری + .recover")
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        issues.append(f"{len(fk)} نقض کلید خارجی")
    # یتیم‌ها
    orphans = {
        "purchases بدون محصول": "SELECT COUNT(*) FROM purchases p LEFT JOIN products pr ON pr.id=p.product_id WHERE pr.id IS NULL",
        "purchases بدون خریدار": "SELECT COUNT(*) FROM purchases p LEFT JOIN users u ON u.user_id=p.buyer_id WHERE u.user_id IS NULL",
        "task_completions بدون تسک": "SELECT COUNT(*) FROM task_completions tc LEFT JOIN tasks t ON t.id=tc.task_id WHERE t.id IS NULL",
    }
    for label, sql in orphans.items():
        try:
            n = cur.execute(sql).fetchone()[0]
            flag = "⚠️" if n else "✅"
            print(f"   {flag} {label}: {n}")
            if n:
                issues.append(f"{label}: {n} ردیف")
        except sqlite3.OperationalError:
            pass
    # بزرگ‌ترین تیبل‌ها
    print("   top tables:")
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    sizes = []
    for t in tables:
        n = cur.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
        sizes.append((n, t))
    for n, t in sorted(sizes, reverse=True)[:6]:
        print(f"     {t:<22} {n:>10,}")
    con.close()

    if "--fix-wal" in sys.argv and wal > 50 * 1024 * 1024:
        con = sqlite3.connect(db)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        print(f"   🔧 WAL checkpoint شد → wal={human(os.path.getsize(db+'-wal')) if os.path.exists(db+'-wal') else '0B'}")

    if issues:
        print("\n⚠️ یافته‌ها:")
        for i in issues:
            print(f"   - {i}")
        return 2
    print("\n✅ همه‌چیز سالم است")
    return 0


if __name__ == "__main__":
    sys.exit(main())
