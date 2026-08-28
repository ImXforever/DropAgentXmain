"""0.5.1 — i18n، لانچر، دکتر DB، پک مهارت."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_i18n_fa_en_and_fallback():
    from i18n import t, available
    assert "fa" in available() and "en" in available()
    assert "کیف" in t("menu.wallet")
    assert "Wallet" in t("menu.wallet", "en")
    assert "کیف" in t("menu.wallet", "fr")          # فالبک به fa
    assert t("nope.key") == "nope.key"               # کلید غایب
    assert "۱۵۰" in t("bonus.daily_claimed", amount="۱۵۰", streak=3) or "150" in t(
        "bonus.daily_claimed", amount=150, streak=3)


def test_i18n_format_bad_kwargs_safe():
    from i18n import t
    # قالب با پارامتر ولی بدون kwarg → نباید کرش کند
    assert "کردیت" in t("quests.claimed_ok")


def test_launcher_normalize_env(monkeypatch):
    import importlib
    import run as runmod
    monkeypatch.delenv("WEB_PORT", raising=False)
    monkeypatch.setenv("PORT", "7080")
    runmod.normalize_env()
    assert os.environ.get("WEB_PORT") == "7080"
    monkeypatch.setenv("DATA_DIR", "/tmp/daxdata")
    runmod.normalize_env()
    assert os.environ.get("DB_PATH", "").startswith("/tmp/daxdata")


def test_launcher_detect_mode(monkeypatch):
    import run as runmod
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert runmod.detect_mode() == "railway"
    monkeypatch.delenv("RAILWAY_ENVIRONMENT")
    monkeypatch.delenv("DAX_MODE", raising=False)
    assert runmod.detect_mode() == "vps"


def test_skills_pack_valid(tmp_path):
    root = os.path.join(os.path.dirname(__file__), "..", "skills_builtin")
    names = sorted(os.listdir(root))
    assert len(names) >= 12
    for n in names:
        body = open(os.path.join(root, n, "SKILL.md"), encoding="utf-8").read()
        assert body.startswith("---"), n
        assert "name:" in body and "description:" in body and "keywords:" in body
        assert len(body) > 450, f"{n} خیلی کوتاه است"


def test_db_doctor_runs_clean(tmp_path, monkeypatch):
    import sqlite3
    import importlib
    import config as cfgmod
    cfg = cfgmod.config
    dbp = str(tmp_path / "doc.db")
    con = sqlite3.connect(dbp)
    con.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, created_at REAL DEFAULT 0)")
    con.execute("INSERT INTO users (user_id, credits) VALUES (1, 10)")
    con.commit(); con.close()
    monkeypatch.setattr(cfg, "DB_PATH", dbp)
    import tools_db_doctor as doc
    monkeypatch.setattr(sys, "argv", ["x"])
    assert doc.main() in (0, 2)   # ۰=سالم، ۲=یافته (ولی هرگز کرش نمی‌کند)
