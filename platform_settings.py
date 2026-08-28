"""Runtime-editable platform variables — everything the admin can change live.

Each key: (label_fa, type, validator) ; values stored in settings table and
read through hermes_engine.get_dynamic_setting (30s cache).
"""

from config import config as cfg

# key -> (label, type, min, max)
SETTINGS_META: dict[str, tuple[str, type, float, float]] = {
    "commission_rate":       ("کمیسیون فروش (۰ تا ۰.۵)", float, 0.0, 0.5),
    "credits_per_usdt":      ("نرخ تبدیل: کردیت به هر USDT", int, 1, 1_000_000),
    "welcome_credits":       ("کردیت خوش‌آمدگویی", int, 0, 100_000),
    "credits_per_follow":    ("حداقل پاداش هر تسک", int, 1, 10_000),
    "ref_invite_bonus_referrer": ("بونوس معرف پس از فعالیت", int, 0, 100_000),
    "ref_bonus_referee":     ("هدیه کاربر دعوت‌شده", int, 0, 100_000),
    "ref_mystery_min":       ("جعبه شانس حداقل", int, 0, 10_000),
    "ref_mystery_max":       ("جعبه شانس حداکثر", int, 0, 10_000),
    "ref_commission_share":  ("سهم ریفرال از کمیسیون (۰ تا ۱)", float, 0.0, 1.0),
    "ref_ms_5":              ("مایلستون ۵ نفر", int, 0, 1_000_000),
    "ref_ms_25":             ("مایلستون ۲۵ نفر", int, 0, 1_000_000),
    "ref_ms_100":            ("مایلستون ۱۰۰ نفر", int, 0, 1_000_000),
    "capo_min_refs":         ("آستانه کاپو (دعوت فعال)", int, 1, 10_000),
    "capo_override_pct":     ("اوورراید کاپو (۰ تا ۰.۵)", float, 0.0, 0.5),
    "deposit_min_usdt":      ("حداقل واریز USDT", float, 0.1, 10_000),
    "withdraw_min_usdt":     ("حداقل برداشت USDT", float, 0.1, 10_000),
    "fee_ton":               ("کارمزد برداشت TON", float, 0, 100),
    "fee_bsc":               ("کارمزد برداشت BSC/BASE", float, 0, 100),
    "fee_sol":               ("کارمزد برداشت SOL", float, 0, 100),
    "fee_trx":               ("کارمزد برداشت TRX", float, 0, 100),
    "custom_bot_price_usdt": ("قیمت Custom Bot (USDT)", int, 1, 10_000),
    "ai_cooldown_seconds":   ("فاصله مجاز چت AI (ثانیه)", int, 1, 600),
    "daily_report_hour":     ("ساعت گزارش روزانه", int, 0, 23),
    "stars_enabled":         ("پرداخت با تلگرام استارز (۱/۰)", int, 0, 1),
    "stars_per_usdt":        ("نرخ: ستاره به هر USDT", int, 1, 10_000),
}


def defaults_from_env() -> dict[str, str]:
    return {
        "commission_rate": str(cfg.COMMISSION_RATE),
        "credits_per_usdt": str(cfg.CREDITS_PER_USDT),
        "welcome_credits": str(cfg.WELCOME_CREDITS),
        "credits_per_follow": str(cfg.CREDITS_PER_FOLLOW),
        "ref_invite_bonus_referrer": str(cfg.REF_INVITE_BONUS_REFERRER),
        "ref_bonus_referee": str(cfg.REF_BONUS_REFEREE),
        "ref_mystery_min": str(cfg.REF_MYSTERY_MIN),
        "ref_mystery_max": str(cfg.REF_MYSTERY_MAX),
        "ref_commission_share": str(cfg.REF_COMMISSION_SHARE),
        "ref_ms_5": str(cfg.REF_MILESTONES.get(5, 250)),
        "ref_ms_25": str(cfg.REF_MILESTONES.get(25, 1500)),
        "ref_ms_100": str(cfg.REF_MILESTONES.get(100, 8000)),
        "capo_min_refs": str(cfg.CAPO_MIN_REFS),
        "capo_override_pct": str(cfg.CAPO_OVERRIDE_PCT),
        "deposit_min_usdt": str(cfg.DEPOSIT_MIN_USDT),
        "withdraw_min_usdt": str(cfg.WITHDRAW_MIN_USDT),
        "fee_ton": str(cfg.WITHDRAW_FEES.get("ton", 0.5)),
        "fee_bsc": str(cfg.WITHDRAW_FEES.get("bsc", 1)),
        "fee_sol": str(cfg.WITHDRAW_FEES.get("sol", 0.5)),
        "fee_trx": str(cfg.WITHDRAW_FEES.get("trx", 1)),
        "stars_enabled": "1",
        "stars_per_usdt": "100",
    }


async def dyn(key: str):
    """Typed dynamic read with env fallback."""
    from hermes_engine import get_dynamic_setting
    label, typ, lo, hi = SETTINGS_META[key]
    raw = await get_dynamic_setting(key, defaults_from_env().get(key, ""))
    try:
        v = typ(float(raw)) if typ is float else typ(raw)
    except (TypeError, ValueError):
        v = typ(defaults_from_env()[key])
    return max(lo, min(hi, v))


def validate(key: str, raw: str):
    label, typ, lo, hi = SETTINGS_META[key]
    try:
        v = typ(float(raw)) if typ is float else typ(raw)
    except (TypeError, ValueError):
        return None, f"❌ «{raw}» عدد نیست."
    if not (lo <= v <= hi):
        return None, f"❌ بازه مجاز: {lo:g} تا {hi:g}"
    return v, None
