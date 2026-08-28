"""0.5.1 — چندزبانه‌سازی (fa پایه، en کامل) — افزودنی، بدون شکستن کد فعلی.

مصرف در کد جدید:
    from i18n import t
    await message.answer(t("menu.wallet", lang=user_lang))
کلید غایب → فالبک به fa → خود کلید (دیباگ آسان).
"""
import json
import os

DEFAULT_LANG = os.getenv("DAX_LANG", "fa").strip() or "fa"
_LOCALES: dict = {}
_LANG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")


def _load(lang: str) -> dict:
    lang = (lang or DEFAULT_LANG).strip().lower() or "fa"
    if lang not in _LOCALES:
        path = os.path.join(_LANG_DIR, f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _LOCALES[lang] = json.load(f)
        except Exception:
            _LOCALES[lang] = {}
    return _LOCALES[lang]


def t(key: str, lang: str | None = None, **kw) -> str:
    """ترجمهٔ کلید با فالبک دو مرحله‌ای (زبان → fa → کلید)."""
    lang = (lang or DEFAULT_LANG).strip().lower()
    v = _load(lang).get(key)
    if v is None and lang != "fa":
        v = _load("fa").get(key)
    if v is None:
        return key
    try:
        return v.format(**kw) if kw else v
    except (KeyError, IndexError, ValueError):
        return v


def available() -> list:
    try:
        return sorted(f[:-5] for f in os.listdir(_LANG_DIR) if f.endswith(".json"))
    except OSError:
        return ["fa"]
