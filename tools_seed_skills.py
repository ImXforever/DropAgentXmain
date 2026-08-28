#!/usr/bin/env python3
"""0.5.1: نصب پک مهارت‌های داخلی به data/skills (برای فروشگاه مهارت هرمس)
   python tools_seed_skills.py [--force]"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "skills_builtin")
DST = os.path.join(ROOT, "data", "skills")


def main() -> None:
    if not os.path.isdir(SRC):
        print("پک مهارتی پیدا نشد:", SRC)
        sys.exit(1)
    os.makedirs(DST, exist_ok=True)
    force = "--force" in sys.argv
    n = 0
    for name in sorted(os.listdir(SRC)):
        src = os.path.join(SRC, name)
        dst = os.path.join(DST, name)
        if not os.path.isdir(src):
            continue
        if os.path.exists(dst) and not force:
            print(f"  ↷ {name} (از قبل هست — --force برای بازنویسی)")
            continue
        shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"  ✅ {name}")
        n += 1
    print(f"\n{n} مهارت نصب شد → data/skills/")


if __name__ == "__main__":
    main()
