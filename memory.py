"""Long-term user memory — Hermes-style memory providers + purchase profile.

Layers:
    1. user_memories   → durable facts extracted from chat (preference/interest/
                         skill/goal), deduplicated, importance-scored
    2. user_profile    → purchase aggregates (buys, spend, categories) + LLM persona
    3. recall          → relevance-ranked injection into AI prompts
    4. recommend       → "برای تو" products from category affinity

Providers are pluggable (MemoryProvider ABC). Default: sqlite. Register another
provider (mem0/honcho/…) via register_provider() and pick it with the
`memory_provider` setting or MEMORY_PROVIDER env var.

Everything degrades gracefully: if the AI backend is down, extraction is simply
skipped; if memory is disabled (`memory_enabled` setting = 0), context is empty.
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time

logger = logging.getLogger(__name__)

MEMORY_BUDGET_CHARS = 800
RECALL_CANDIDATES = 60
PERSONA_MIN_MEMORIES = 4


# ---------------------------------------------------------------------------
# Provider abstraction (Hermes plugins/memory pattern, single-file edition)
# ---------------------------------------------------------------------------

class MemoryProvider:
    """Base class for pluggable long-term memory backends."""
    name = "abstract"

    async def remember(self, user_id: int, kind: str, content: str,
                       importance: int, source: str) -> bool: ...
    async def recall(self, user_id: int, query: str, limit: int) -> list[dict]: ...
    async def forget_all(self, user_id: int) -> int: ...
    async def list_all(self, user_id: int, limit: int = 100) -> list[dict]: ...
    async def delete_one(self, user_id: int, mem_id: int) -> bool: ...
    async def add_note(self, user_id: int, kind: str, content: str) -> bool: ...


class SQLiteMemoryProvider(MemoryProvider):
    name = "sqlite"

    async def remember(self, user_id, kind, content, importance, source):
        from database import get_db
        key = _dedup_key(content)
        async with get_db() as db:
            cur = await db.execute(
                """INSERT OR IGNORE INTO user_memories
                   (user_id, kind, content, importance, source, dedup_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, kind, content.strip()[:400], max(1, min(5, importance)),
                 source, key))
            return cur.rowcount > 0

    async def recall(self, user_id, query, limit):
        from database import get_db, escape_like
        async with get_db() as db:
            cur = await db.execute(
                f"""SELECT id, kind, content, importance, source,
                           COALESCE(recall_count,0), created_at
                    FROM user_memories WHERE user_id = ?
                    ORDER BY importance DESC, id DESC LIMIT ?""",
                (user_id, RECALL_CANDIDATES))
            rows = await cur.fetchall()
        now = time.time()
        tokens = [t.lower() for t in re.findall(r"[\w\u0600-\u06FF]{4,}", query or "")][:8]
        scored = []
        for mid, kind, content, imp, src, rc, created in rows:
            age_days = max(0.0, (now - (created or now)) / 86400)
            score = imp * 10 + 30 * math.exp(-age_days / 45) + min(rc, 5)
            c = (content or "").lower()
            score += sum(15 for t in tokens if t in c)
            scored.append((score, {"id": mid, "kind": kind, "content": content,
                                   "importance": imp, "source": src}))
        scored.sort(key=lambda x: -x[0])
        out = [m for _, m in scored[:limit]]
        if out:
            ids = [m["id"] for m in out]
            async with get_db() as db:
                await db.execute(
                    f"""UPDATE user_memories SET recall_count = recall_count + 1,
                        last_recalled_at = strftime('%s','now')
                        WHERE id IN ({','.join('?' * len(ids))})""", ids)
        return out

    async def forget_all(self, user_id):
        from database import get_db
        async with get_db() as db:
            cur = await db.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM user_profile WHERE user_id = ?", (user_id,))
            return cur.rowcount

    async def list_all(self, user_id, limit=100):
        from database import get_db
        async with get_db() as db:
            cur = await db.execute(
                """SELECT id, kind, content, importance, source, created_at, recall_count
                   FROM user_memories WHERE user_id = ?
                   ORDER BY id DESC LIMIT ?""", (user_id, limit))
            cols = ("id", "kind", "content", "importance", "source", "created_at",
                    "recall_count")
            return [dict(zip(cols, r)) for r in await cur.fetchall()]

    async def delete_one(self, user_id, mem_id):
        from database import get_db
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM user_memories WHERE id = ? AND user_id = ?",
                (mem_id, user_id))
            return cur.rowcount > 0

    async def add_note(self, user_id, kind, content):
        return await self.remember(user_id, kind, content, 4, "admin")


_PROVIDERS: dict[str, type] = {"sqlite": SQLiteMemoryProvider}


def register_provider(provider_cls):
    """Plugin hook: register_provider(MyMem0Provider) then set
    `memory_provider` setting / MEMORY_PROVIDER env to its .name."""
    _PROVIDERS[provider_cls.name] = provider_cls


async def get_provider() -> MemoryProvider:
    import os
    from database import get_setting
    name = await get_setting("memory_provider", "") or os.getenv("MEMORY_PROVIDER", "sqlite")
    cls = _PROVIDERS.get(name) or SQLiteMemoryProvider
    return cls()


# ---------------------------------------------------------------------------

def _dedup_key(content: str) -> str:
    norm = re.sub(r"\s+", " ", (content or "").strip().lower())[:160]
    return hashlib.sha1(norm.encode()).hexdigest()[:24]


async def memory_enabled() -> bool:
    from hermes_engine import get_dynamic_setting
    try:
        return (await get_dynamic_setting("memory_enabled", "1")) == "1"
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Purchase profile
# ---------------------------------------------------------------------------

async def record_purchase_event(user_id: int, product: dict):
    """Called after every successful buy — no LLM involved, pure SQL."""
    if not product:
        return
    cat = product.get("category") or "general"
    price = int(product.get("price_credits") or 0)
    try:
        from database import get_db
        async with get_db() as db:
            await db.execute(
                """INSERT INTO user_profile (user_id, buys_count, total_spent_credits,
                                            last_categories, updated_at)
                   VALUES (?, 1, ?, '', strftime('%s','now'))
                   ON CONFLICT(user_id) DO UPDATE SET
                     buys_count = buys_count + 1,
                     total_spent_credits = total_spent_credits + excluded.total_spent_credits,
                     updated_at = strftime('%s','now')""",
                (user_id, price))
            # refresh rolling category history (newest first, keep 12)
            cur = await db.execute(
                "SELECT last_categories FROM user_profile WHERE user_id = ?",
                (user_id,))
            hist = ((await cur.fetchone())[0] or "").split(",")
            hist = [c.strip() for c in hist if c.strip()]
            if cat in hist:
                hist.remove(cat)
            hist.insert(0, cat)
            await db.execute(
                "UPDATE user_profile SET last_categories = ? WHERE user_id = ?",
                (",".join(hist[:12]), user_id))
    except Exception:
        logger.debug("purchase profile update failed", exc_info=True)

    p = await get_provider()
    await p.remember(user_id, "interest",
                     f"به محصولات دسته «{cat}» علاقه نشان داد (خرید)",
                     importance=3, source="purchase")


async def purchase_profile(user_id: int) -> dict:
    """Live purchases are source of truth; user_profile caches rolling
    category history + persona (and covers brand-new buyers instantly)."""
    from database import get_db
    async with get_db() as db:
        cur = await db.execute(
            """SELECT COUNT(*), COALESCE(SUM(pc.price_credits),0),
                      COALESCE(AVG(pc.price_credits),0),
                      GROUP_CONCAT(DISTINCT pr.category)
               FROM purchases pc JOIN products pr ON pr.id = pc.product_id
               WHERE pc.buyer_id = ?""", (user_id,))
        n, spent, avg, cats = await cur.fetchone()
        cur = await db.execute(
            """SELECT buys_count, total_spent_credits, last_categories,
                      persona, interests
               FROM user_profile WHERE user_id = ?""", (user_id,))
        cb, cspend, ccats, persona, interests = (
            (await cur.fetchone()) or (0, 0, "", "", ""))

    # merge: newest-first unique categories (live first, cache fills the rest)
    seen, merged = set(), []
    for c in ((cats or "").split(",") + [c.strip() for c in (ccats or "").split(",")]):
        c = c.strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            merged.append(c)
    # cache and live normally agree (both tick on every real buy);
    # max() keeps us safe if one side is briefly behind
    return {
        "buys": max(n or 0, cb or 0),
        "spent": max(spent or 0, cspend or 0),
        "avg_ticket": round(avg or 0),
        "categories": merged[:8],
        "persona": persona or "",
        "interests": interests or "",
    }


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

_KIND_ICON = {"preference": "⭐", "interest": "🎯", "fact": "📌",
              "skill": "🛠️", "goal": "🎯", "habit": "🔁", "admin": "🛡️"}


async def build_memory_context(user_id: int, query: str = "") -> str:
    """Compact block injected into the system prompt (~budget-capped)."""
    if not await memory_enabled():
        return ""
    try:
        p = await get_provider()
        memories = await p.recall(user_id, query, limit=6)
        prof = await purchase_profile(user_id)
    except Exception:
        logger.debug("memory context failed", exc_info=True)
        return ""

    lines = []
    if memories:
        seen = set()
        for m in memories:
            c = m["content"].strip()
            if c.lower() in seen:
                continue
            seen.add(c.lower())
            lines.append(f"{_KIND_ICON.get(m['kind'], '•')} {c}")
    pp = []
    if prof["buys"]:
        pp.append(f"{prof['buys']} خرید")
        pp.append(f"میانگین سبد {prof['avg_ticket']:,} کردیت")
        if prof["categories"]:
            pp.append("دسته‌های خرید: " + "، ".join(prof["categories"][:4]))
    if prof["persona"]:
        lines.insert(0, f"👤 {prof['persona'][:220]}")

    block = ""
    if lines:
        block += "\n".join(f"- {l}" for l in lines)
    if pp:
        block += ("\n\n🛒 پروفایل خرید:\n- " + " | ".join(pp)) if block else \
                 "\n".join(f"- 🛒 {x}" for x in pp)
    if not block:
        return ""
    return ("\n\n🧠 حافظهٔ بلندمدت این کاربر (از گفتگوها و خریدهای قبلی — برای "
            "شخصی‌سازی پاسخ استفاده کن، بدون اینکه اعلام کنی از حافظه می‌خوانی):\n"
            + block)[:MEMORY_BUDGET_CHARS]


# ---------------------------------------------------------------------------
# Extraction pipeline (cost-guarded, fire-and-forget)
# ---------------------------------------------------------------------------

_EXTRACT_CONTRACT = """فقط JSON خالص برگردان، بدون هیچ توضیح اضافه:
{"facts": [{"kind": "preference|interest|skill|goal|fact", "content": "...", "importance": 1-5}]}
قواعد:
- فقط اطلاعات ماندگار دربارهٔ خودِ کاربر (ترجیح، مهارت، هدف، زمینه کاری) — نه اطلاعات موقت گفتگو
- اگر چیز ماندگاری وجود ندارد: {"facts": []}
- حداکثر ۳ مورد؛ هر content زیر ۱۲۰ کاراکتر فارسی روان"""


async def maybe_extract_memories(user_id: int, user_text: str, assistant_text: str):
    """Cheap periodic extraction — schedule with asyncio.create_task()."""
    try:
        if not user_text or len(user_text) < 25 or user_text.startswith("/"):
            return
        if not await memory_enabled():
            return
        from database import mem_count, get_setting
        turns = await mem_count(user_id)
        every = int(float(await get_setting("memory_extract_every", "6")) or 6)
        if turns < 2 or turns % every != 0:
            return

        from hermes_engine import hermes_chat
        convo = (f"کاربر: {user_text[:600]}\nدستیار: {(assistant_text or '')[:600]}")
        raw = await hermes_chat(
            convo, system_prompt=_EXTRACT_CONTRACT, user_key=user_id)
        data = _safe_json(raw)
        facts = (data or {}).get("facts") or []
        p = await get_provider()
        added = 0
        for f in facts[:3]:
            if not isinstance(f, dict):
                continue
            content = str(f.get("content", "")).strip()
            if len(content) < 6:
                continue
            kind = str(f.get("kind", "fact"))
            if kind not in ("preference", "interest", "skill", "goal", "fact"):
                kind = "fact"
            if await p.remember(user_id, kind, content,
                                int(f.get("importance") or 3), "chat"):
                added += 1

        # persona refresh: occasionally, once enough material exists
        total = await _count_memories(user_id)
        if total >= PERSONA_MIN_MEMORIES and (turns % (every * 4) == 0 or not
                                              (await purchase_profile(user_id))["persona"]):
            await persona_refresh(user_id)
        if added:
            logger.info("memory: +%d facts for %s", added, user_id)
    except Exception:
        logger.debug("memory extraction skipped", exc_info=True)


def _safe_json(raw: str) -> dict | None:
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def _count_memories(user_id: int) -> int:
    from database import get_db
    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM user_memories WHERE user_id = ?", (user_id,))
        return (await cur.fetchone())[0]


async def persona_refresh(user_id: int):
    """LLM-written one-liner stored on user_profile.persona."""
    try:
        p = await get_provider()
        items = await p.list_all(user_id, limit=20)
        if len(items) < PERSONA_MIN_MEMORIES:
            return
        prof = await purchase_profile(user_id)
        bullets = "\n".join(f"- {i['content']}" for i in items[:14])
        extra = f"\nالگوی خرید: {prof['buys']} خرید، دسته‌ها: {'، '.join(prof['categories'][:4])}" \
            if prof["buys"] else ""
        from hermes_engine import hermes_chat
        text = await hermes_chat(
            bullets + extra,
            system_prompt="در یک جملهٔ فارسیِ کوتاه (زیر ۲۵ کلمه) این کاربر را "
                          "توصیف کن تا دستیار بتواند شخصی‌سازی کند. فقط جمله.",
        )
        persona = text.strip().splitlines()[0][:240]
        from database import get_db
        async with get_db() as db:
            await db.execute(
                """INSERT INTO user_profile (user_id, persona, persona_at, updated_at)
                   VALUES (?, ?, strftime('%s','now'), strftime('%s','now'))
                   ON CONFLICT(user_id) DO UPDATE SET
                     persona = excluded.persona,
                     persona_at = excluded.persona_at,
                     updated_at = excluded.updated_at""",
                (user_id, persona))
    except Exception:
        logger.debug("persona refresh failed", exc_info=True)


# ---------------------------------------------------------------------------
# Recommendations ("🎯 برای تو")
# ---------------------------------------------------------------------------

async def recommend_for_user(user_id: int, limit: int = 5) -> list[dict]:
    if not await memory_enabled():
        return []
    try:
        prof = await purchase_profile(user_id)
        p = await get_provider()
        memories = await p.recall(user_id, "", limit=10)
    except Exception:
        return []

    affinity: dict[str, float] = {}
    cats = prof.get("categories") or []
    for i, c in enumerate(cats):
        affinity[c] = affinity.get(c, 0) + 3.0 / (1 + i * 0.3)
    text = " ".join([prof.get("interests") or ""] +
                    [m["content"] for m in memories]).lower()
    for c in ("education", "coding", "graphics", "content", "template", "tools"):
        if c in text:
            affinity[c] = affinity.get(c, 0) + 2.0
    if not affinity:
        return []

    from database import get_db
    placeholders = ",".join("?" * len(affinity))
    async with get_db() as db:
        cur = await db.execute(
            f"""SELECT p.id, p.title, p.price_credits, p.sales_count,
                       p.category, p.is_featured, u.first_name, u.username
                 FROM products p LEFT JOIN users u ON u.user_id = p.creator_id
                 WHERE p.is_active = 1 AND p.status='approved'
                   AND p.creator_id != ?
                   AND COALESCE(u.is_banned,0)=0 AND p.category IN ({placeholders})
                 ORDER BY p.created_at DESC LIMIT 40""",
            [user_id] + list(affinity))
        rows = await cur.fetchall()
        if not rows:
            return []
        owned_cur = await db.execute(
            f"SELECT product_id FROM purchases WHERE buyer_id = ? "
            f"AND product_id IN ({','.join('?' * len(rows))})",
            [user_id] + [r[0] for r in rows])
        owned = {r[0] for r in await owned_cur.fetchall()}
        rated_cur = await db.execute(
            f"""SELECT product_id, AVG(stars) FROM reviews
                WHERE product_id IN ({','.join('?' * len(rows))})
                GROUP BY product_id""", [r[0] for r in rows])
        stars = {pid: avg for pid, avg in await rated_cur.fetchall()}

    out = []
    for pid, title, price, sales, cat, featured, fname, uname in rows:
        if pid in owned:
            continue
        score = affinity.get(cat, 0) * 3 + (stars.get(pid, 0) or 0) * 2 \
            + math.log1p(sales or 0) + (1.5 if featured else 0)
        out.append((score, {"id": pid, "title": title, "price_credits": price,
                            "sales_count": sales or 0, "category": cat,
                            "creator_name": fname or uname or ""}))
    out.sort(key=lambda x: -x[0])
    return [item for _, item in out[:limit]]


# ---------------------------------------------------------------------------
# User-facing summary («حافظه من»)
# ---------------------------------------------------------------------------

async def my_memory_summary(user_id: int) -> tuple[str, int]:
    if not await memory_enabled():
        return "حافظهٔ بلندمدت فعلاً غیرفعال است.", 0
    p = await get_provider()
    items = await p.list_all(user_id, limit=12)
    prof = await purchase_profile(user_id)
    total = await _count_memories(user_id)

    lines = []
    if prof["persona"]:
        lines.append(f"👤 {prof['persona']}\n")
    if items:
        for m in items[:8]:
            icon = _KIND_ICON.get(m["kind"], "•")
            lines.append(f"{icon} {m['content']}")
    else:
        lines.append("هنوز چیزی یادنگرفتم — با همین چت هرمس گپ بده تا کم‌کم "
                     "سلیقه‌ات را یاد بگیرم.")
    if prof["buys"]:
        lines.append("")
        lines.append(f"🛒 پروفایل خرید: {prof['buys']} خرید · میانگین سبد "
                     f"{prof['avg_ticket']:,} کردیت"
                     + (f" · دسته‌ها: {'، '.join(prof['categories'][:4])}" if prof["categories"] else ""))
    return "\n".join(lines), total


async def forget_me(user_id: int) -> int:
    """GDPR-style right to be forgotten (long-term layer only)."""
    p = await get_provider()
    return await p.forget_all(user_id)


# background task helper used by handlers ------------------------------------

def schedule_extraction(user_id: int, user_text: str, assistant_text: str):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(maybe_extract_memories(user_id, user_text, assistant_text))
    except RuntimeError:
        pass
