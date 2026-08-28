"""Hermes Fleet — یک چت، یک تیم.

الهام از معماری hermes-agent (Profiles + Delegation + Memory):
- ATLAS  رئیس ستاد: مسیریابی سؤال (ساده→مستقیم / چندلایه→تیم)
- CIPHER پژوهشگر: شواهد از حافظه و مغز دوم (kb_notes)
- VEGA   استراتژیست: گزینه‌ها/سناریوها/ریسک
- QUANT  اعداد: محاسبه با ثابت‌های واقعی پلتفرم
- FORGE  مهندس: راهکار فنی/گام‌های ساخت
- ROOK   Red Team: کوبیدن فرضیه‌ها
- LIBRARIAN ذخیره دانش ارزشمند در مغز دوم
- MUSE   روایتگر نهایی (فارسی خوانا)
"""

import asyncio
import json
import logging

from config import config as cfg
from database import kb_search, kb_save, mem_recent

logger = logging.getLogger(__name__)

ROLES = ("atlas", "cipher", "vega", "quant", "forge", "rook", "librarian", "muse")
ROLE_FA = {
    "atlas": "🧭 Atlas",
    "cipher": "🔎 Cipher",
    "vega": "♟️ Vega",
    "quant": "🔢 Quant",
    "forge": "⚒️ Forge",
    "rook": "🛡️ Rook",
    "librarian": "📚 Librarian",
    "muse": "🎭 Muse",
}

COMPLEX_HINTS = (
    "چرا", "چطور", "چگونه", "برنامه", "استراتژی", "تحلیل", "مقایسه", "ارزش",
    "سود", "ریسک", "بفروشم", "قیمت بذارم", "قیمت بگذارم", "ایده", "سناریو",
    "کمکم کن بسازم", "شروع کنم", "بهتره", "یا ",
)


def platform_facts() -> str:
    return (
        f"ثابت‌های واقعی پلتفرم DropAgentX:\n"
        f"- نرخ: {cfg.CREDITS_PER_USDT} کردیت = 1 USDT؛ کمیسیون فروش {int(cfg.COMMISSION_RATE*100)}٪\n"
        f"- حداقل واریز {cfg.DEPOSIT_MIN_USDT:g}$، برداشت {cfg.WITHDRAW_MIN_USDT:g}$؛ "
        f"شبکه‌ها: TON/BSC-BASE/SOL/TRX\n"
        f"- ریفرال: جعبه شانس {cfg.REF_MYSTERY_MIN}-{cfg.REF_MYSTERY_MAX} کردیت + "
        f"{cfg.REF_INVITE_BONUS_REFERRER}/{cfg.REF_BONUS_REFEREE} پس از فعالیت + "
        f"{int(cfg.REF_COMMISSION_SHARE*100)}٪ کمیسیون مادام‌العمر\n"
        f"- رتبه‌ها: کارآموز→سرباز(اولین فروش)→کاپو({cfg.CAPO_MIN_REFS} دعوت فعال، "
        f"اوورراید {int(cfg.CAPO_OVERRIDE_PCT*100)}٪)→آندرباس(انتصابی)\n"
    )


def _role_model(role: str):
    from hermes_engine import get_dynamic_setting
    return get_dynamic_setting(f"fleet_model_{role}", "")


async def _call(role: str, system: str, user: str, max_tokens: int = 700,
                temperature: float = 0.6) -> str:
    from hermes_engine import llm_call
    model = await _role_model(role)
    try:
        return await llm_call(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            model_override=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        logger.warning("fleet %s failed: %s", role, e)
        return ""


def _looks_complex(text: str) -> bool:
    t = text.strip()
    if len(t) < 60 and t.count("?") + t.count("؟") <= 1:
        # short & single question → likely simple, but let hints override
        if not any(h in t for h in COMPLEX_HINTS):
            return False
    return True


async def atlas_route(user_text: str, has_history: bool) -> dict:
    """Cheap fast router. Returns {'mode','roles','brief','worth_saving','needs_tools'}."""
    system = """تو Atlas هستی، رئیس ستاد تیم. ورودی: پیام کاربر.
تصمیم بگیر:
- mode = "direct" اگر سؤال ساده/گفتگوئی است که یک پاسخ مستقیم کافی است.
- mode = "team" اگر مسئله چندلایه است (تحلیل/استراتژی/محصول/اعداد/ریسک).
اگر team: حداکثر ۳ نقش مناسب از این‌ها به ترتیب اجرا انتخاب کن:
cipher(شواهد), vega(استراتژی), quant(عدد), forge(ساخت), rook(نقد)
— muse همیشه آخر خودکار اجرا می‌شود، آن را لیست نکن.
brief = خلاصهٔ دو خطی مأموریت برای تیم.
worth_saving = true فقط اگر نتیجه احتمالاً ارزش ذخیره بلندمدت دارد.
needs_tools = true اگر کاربر به داده واقعی خودش نیاز دارد
(موجودی، محصولاتش، آمار، ساخت کوپن، تغییر قیمت، جستجوی مارکت/حافظه).
فقط JSON خالص برگردان:
{"mode":"direct|team","roles":["..."],"brief":"...","worth_saving":false,"needs_tools":false}"""

    raw = await _call(
        "atlas", system,
        f"پیام کاربر:\n{user_text}\n\n(تاریخچه دارد: {has_history})",
        max_tokens=240, temperature=0.2,
    )
    from hermes_engine import extract_json
    data = extract_json(raw) or {}
    mode = data.get("mode") if data.get("mode") in ("direct", "team") else None
    if not mode:
        mode = "team" if _looks_complex(user_text) else "direct"
    roles = [r for r in (data.get("roles") or []) if r in ROLES and r not in ("atlas", "muse")][:3]
    if mode == "team" and not roles:
        roles = ["cipher", "vega"]
    return {
        "mode": mode,
        "roles": roles,
        "brief": (data.get("brief") or "")[:400],
        "worth_saving": bool(data.get("worth_saving")),
        "needs_tools": bool(data.get("needs_tools")),
    }


ROLE_PROMPTS = {
    "cipher": """تو Cipher هستی؛ پژوهشگر تیم. با تکیه بر CONTEXT (ثابت‌های پلتفرم، حافظه، مغز دوم)
فقط یافته‌های مرتبط را در بولت‌های کوتاه بیاور و آخرش «اطمینان: بالا/متوسط/پایین» بنویس.
حداکثر ۱۲۰ کلمه.""",
    "vega": """تو Vega هستی؛ استراتژیست. ۲-۳ گزینه یا سناریو با pros/cons و ریسک هرکدام بده.
یک پیشنهاد نهایی مشخص. حداکثر ۱۵۰ کلمه. فارسی.""",
    "quant": """تو Quant هستی؛ تحلیلگر کمی. با اعداد دقیق از CONTEXT محاسبه کن (کردیت/USDT/کمیسیون/ریفرال).
جدول ذهنی ساده با اعداد صریح. اگر داده کافی نیست، فرضت را اعلام کن. حداکثر ۱۲۰ کلمه.""",
    "forge": """تو Forge هستی؛ مهندس. گام‌های عملی ساخت (۱ تا ۶ قدم) با ابزارهای موجود داخل بات
(ساخت محصول، Document Builder، تسک، ریفرال، ولت). هر قدم یک خط. حداکثر ۱۲۰ کلمه.""",
    "rook": """تو Rook هستی؛ Red Team. صریح و بی‌تعارف: ۲-۴ ایراد/ریسک نادیده‌گرفته‌شده در تحلیل قبلی
+ اصلاح پیشنهادی هرکدام. تعارف ممنوع. حداکثر ۱۰۰ کلمه.""",
    "muse": """تو Muse هستی؛ روایتگر نهایی. همهٔ یافته‌های تیم را به یک پاسخ فارسی واحد، گرم و خوانا
تبدیل کن: شروع با یک جملهٔ کلید، بعد بولت‌های کوتاه، پایان با «قدم بعدی». بدون ذکر نام ایجنت‌ها.
حداکثر ۳۰۰ کلمه. از ایموجی متعادل استفاده کن.""",
}


async def run_fleet(user_text: str, user_id: int, on_status) -> tuple[str, dict]:
    """Full team run. on_status(str) gets live status lines for the chat.
    Returns (final_answer, meta)."""
    history = await mem_recent(user_id, turns=4)
    hist_digest = "\n".join(f"{h['role']}: {h['content'][:200]}" for h in history[-4:])
    notes = await kb_search(user_id, user_text, limit=2)
    kb_block = "\n".join(f"📌 {n['topic']}: {n['content'][:300]}" for n in notes) or "—"

    await on_status("🧭 Atlas داره مسئله رو بررسی می‌کنه…")
    route = await atlas_route(user_text, bool(history))

    if route["mode"] != "team":
        return "", {"mode": "direct", "needs_tools": route.get("needs_tools", False)}

    context = (
        platform_facts()
        + f"\nحافظه اخیر:\n{hist_digest or '—'}\n\nمغز دوم:\n{kb_block}"
    )

    running = f"TASK: {user_text}"
    if route["brief"]:
        running += f"\nBRIEF Atlas: {route['brief']}"

    # ---- delegation (Hermes MoA-style) ----
    # NOTE: sequential by default — parallel fires N requests simultaneously
    # which triggers 429 rate-limits on OpenRouter/free tiers.
    from database import get_setting
    parallel = (await get_setting("fleet_parallel", "0")) == "1"
    independent = [r for r in route["roles"] if r != "rook"]
    critic = [r for r in route["roles"] if r == "rook"]

    async def _run_role(role: str):
        fa = ROLE_FA[role]
        out = await _call(
            role,
            ROLE_PROMPTS[role] + "\n\nCONTEXT:\n" + context,
            running,
            max_tokens=650 if role != "rook" else 500,
            temperature=0.5 if role != "vega" else 0.7,
        )
        return role, out

    if parallel and len(independent) > 1:
        await on_status("🛰️ اجرای موازی: " + " · ".join(
            ROLE_FA[r] for r in independent))
        results = await asyncio.gather(*(_run_role(r) for r in independent))
    else:
        results = []
        done_line0 = ""
        for i, role in enumerate(independent, 1):
            await on_status(f"{done_line0}{ROLE_FA[role]} در حال کار… ({i}/{len(route['roles'])+1})")
            results.append(await _run_role(role))
            done_line0 += f"{ROLE_FA[role]} ✓  "

    for role, out in results:
        if out:
            running += f"\n\n[{ROLE_FA[role]}]:\n{out}"

    done_line = "".join(f"{ROLE_FA[r]} ✓  " for r, o in results if o)

    # Red Team always runs AFTER the panel (needs full picture)
    for role in critic:
        await on_status(f"{done_line}🛡️ Rook حملهٔ Red Team…")
        out = await _call(
            "rook",
            ROLE_PROMPTS["rook"] + "\n\nCONTEXT:\n" + context,
            running,
            max_tokens=500,
        )
        if out:
            running += f"\n\n[{ROLE_FA['rook']}]:\n{out}"
            done_line += f"{ROLE_FA['rook']} ✓  "

    await on_status(f"{done_line}🎭 Muse داره نهایی می‌کنه…")
    final = await _call(
        "muse",
        ROLE_PROMPTS["muse"] + "\n\nCONTEXT:\n" + context,
        running,
        max_tokens=900, temperature=0.65,
    )
    answer = (final or "").strip()
    if not answer:
        # graceful degradation: stitch last outputs raw
        answer = running.split("\n\n[", 1)[-1][:3000]

    meta = {"mode": "team", "roles": route["roles"],
            "worth_saving": route["worth_saving"], "needs_tools": False}

    if route["worth_saving"]:
        try:
            await kb_save(
                user_id,
                topic=user_text[:120],
                content=f"{answer[:1500]}",
                source="librarian:auto",
            )
            meta["saved"] = True
        except Exception as e:
            logger.warning("kb_save failed: %s", e)

    return answer, meta


async def fleet_status_line(user_id: int) -> str:
    from database import kb_count
    n = await kb_count(user_id)
    enabled = True
    try:
        from database import get_setting
        enabled = (await get_setting("fleet_enabled", "1")) == "1"
    except Exception:
        pass
    return f"🛰️ Fleet: {'فعال' if enabled else 'غیرفعال'} | 🧠 مغز دوم: {n} یادداشت"
