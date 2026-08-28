"""
DropAgentX v2.0.0 — Multi-faceted long-term memory.

The v1 memory was a single "facts" bucket. v2 splits memory into facets so the
agent can recall *the right kind of thing at the right time*:

    identity     who they are (name, birthday, language, timezone, life status)  [sticky]
    factual      what they know / told us (fields, habits, projects, addresses)
    preference   what they like (categories, pricing, brands, tone)
    behavioral   how they act (buy cadence, task cadence, hesitation, session time)
    emotional    how they feel (frustration, excitement, trust signals)
    engagement   what they engage with (top products, top categories, click rate)
    risk         fraud/farm flags (mystery-box farming, chargeback, multi-account)

Each facet is scored with a weighted blend of:
    - facet weight (config.MEMORY_FACET_W)
    - importance (1-5)
    - recency (exponential decay)
    - recall count (reinforcement)
    - semantic-ish keyword overlap with the current query

Sticky identity facts never evict. Everything else has a configurable TTL.
"""

import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from config import config
from observability import db_log

FACETS = ("identity", "factual", "preference", "behavioral", "emotional",
          "engagement", "risk")

# Sticky identity claims that must never be pruned.
_STICKY_KINDS = {"name", "birthday", "language", "timezone", "relationship",
                 "gender", "occupation", "location"}

_FACET_ALIAS = {
    "id": "identity", "identity": "identity",
    "fact": "factual", "factual": "factual",
    "pref": "preference", "preference": "preference",
    "behave": "behavioral", "behavioral": "behavioral",
    "emo": "emotional", "emotional": "emotional",
    "engage": "engagement", "engagement": "engagement",
    "risk": "risk", "trust": "risk",
}


def _canon_facet(facet: str) -> str:
    return _FACET_ALIAS.get((facet or "").strip().lower(), "factual")


def _dedup_key(content: str) -> str:
    import hashlib
    return hashlib.sha1(content.strip().lower().encode("utf-8")).hexdigest()[:16]


@dataclass
class Memory:
    id: int
    user_id: int
    facet: str
    kind: str
    content: str
    importance: float
    source: str
    metadata: dict
    created_at: float
    updated_at: float
    recall_count: int
    sticky: bool


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def init_tables() -> None:
    from database import raw_db
    async with raw_db() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_facets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                facet TEXT NOT NULL,
                kind TEXT DEFAULT '',
                content TEXT NOT NULL,
                importance REAL DEFAULT 3.0,
                source TEXT DEFAULT 'chat',
                metadata TEXT DEFAULT '{}',
                dedup_key TEXT,
                recall_count INTEGER DEFAULT 0,
                last_recalled_at REAL,
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE(user_id, facet, dedup_key)
            )""")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem2_user ON memory_facets(user_id, facet, importance)")
        await db.commit()


async def remember(user_id: int, facet: str, content: str, kind: str = "",
                   importance: float = 3.0, source: str = "chat",
                   metadata: dict | None = None, sticky: bool = False) -> bool:
    """Upsert a memory. `sticky` marks durable identity facts."""
    facet = _canon_facet(facet)
    if not content or not content.strip():
        return False
    key = _dedup_key(content)
    importance = max(1.0, min(5.0, float(importance)))
    meta = json.dumps(metadata or {}, ensure_ascii=False)
    from database import raw_db
    async with raw_db() as db:
        row = await db.execute(
            "SELECT id FROM memory_facets WHERE user_id=? AND facet=? AND dedup_key=?",
            (user_id, facet, key))
        cur = await row.fetchone()
        if cur:
            await db.execute(
                "UPDATE memory_facets SET content=?, importance=MAX(importance, ?), "
                "source=?, metadata=?, updated_at=strftime('%s','now') WHERE id=?",
                (content.strip()[:600], importance, source, meta, cur[0]))
        else:
            await db.execute(
                "INSERT INTO memory_facets "
                "(user_id, facet, kind, content, importance, source, metadata, dedup_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, facet, kind[:60], content.strip()[:600], importance,
                 source, meta, key))
        await db.commit()
    return True


def _row_to_mem(r) -> Memory:
    """Accept a sqlite Row (positional) OR a dict keyed by column name."""
    if isinstance(r, dict):
        return Memory(
            id=int(r["id"]), user_id=int(r["user_id"]), facet=r["facet"],
            kind=r["kind"], content=r["content"], importance=float(r["importance"]),
            source=r["source"], metadata=json.loads(r["metadata"]) if r.get("metadata") else {},
            created_at=float(r["created_at"] or 0), updated_at=float(r["updated_at"] or 0),
            recall_count=int(r["recall_count"] or 0),
            sticky=(r["kind"] in _STICKY_KINDS),
        )
    return Memory(
        id=r[0], user_id=r[1], facet=r[2], kind=r[3], content=r[4],
        importance=float(r[5]), source=r[6],
        metadata=json.loads(r[7]) if r[7] else {},
        created_at=float(r[8] or 0), updated_at=float(r[9] or 0),
        recall_count=int(r[10] or 0),
        sticky=(r[3] in _STICKY_KINDS),
    )


async def recall(user_id: int, query: str = "", limit: int = 8,
                 facet_filter: str | None = None) -> list[Memory]:
    """Score + fetch the most relevant memories across all facets."""
    from database import raw_db
    async with raw_db() as db:
        fq = "SELECT id,user_id,facet,kind,content,importance,source,metadata,created_at,updated_at,recall_count " \
             "FROM memory_facets WHERE user_id=?"
        params = [user_id]
        if facet_filter:
            fq += " AND facet=?"
            params.append(_canon_facet(facet_filter))
        fq += " ORDER BY importance DESC, updated_at DESC LIMIT 120"
        cur = await db.execute(fq, params)
        rows = [dict(zip(("id", "user_id", "facet", "kind", "content", "importance",
                           "source", "metadata", "created_at", "updated_at", "recall_count"),
                         r)) for r in await cur.fetchall()]

    now = time.time()
    tokens = [t.lower() for t in re.findall(r"[\w\u0600-\u06FF]{3,}", query or "")][:10]
    weights = config.MEMORY_FACET_W if config.MEMORY_FACET_W else {}
    scored = []
    for row in rows:
        age_days = max(0.0, (now - (row["updated_at"] or now)) / 86400)
        if not row["content"]:
            continue
        sticky = row["kind"] in _STICKY_KINDS
        # recency decay: 30-day half-life for normal, sticky stays
        recency = 1.0 if sticky else math.exp(-age_days / 30)
        # emotional/risk reinforce importance a bit for novelty
        score = (float(row["importance"]) * 10
                 + (weights.get(row["facet"], 1.0) * 8)
                 + recency * 25
                 + min(int(row["recall_count"] or 0), 5))
        c = row["content"].lower()
        score += sum(18 for t in tokens if t in c)
        if sticky:
            score += 15
        scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    ids = [r["id"] for _, r in top if r["id"]]
    if ids:
        from database import raw_db as _rdb
        async with _rdb() as db:
            await db.execute(
                f"UPDATE memory_facets SET recall_count=recall_count+1, "
                f"last_recalled_at=strftime('%s','now') "
                f"WHERE id IN ({','.join('?' * len(ids))})", ids)
            await db.commit()
    return [_row_to_mem(r) for _, r in top]


async def list_all(user_id: int, limit: int = 200) -> list[Memory]:
    from database import raw_db
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT id,user_id,facet,kind,content,importance,source,metadata,created_at,updated_at,recall_count "
            "FROM memory_facets WHERE user_id=? ORDER BY facet, importance DESC LIMIT ?",
            (user_id, limit))
        rows = await cur.fetchall()
    return [_row_to_mem(r) for r in rows]


async def forget_facet(user_id: int, facet: str | None = None) -> int:
    from database import raw_db
    async with raw_db() as db:
        if facet:
            cur = await db.execute("DELETE FROM memory_facets WHERE user_id=? AND facet=?",
                                   (user_id, _canon_facet(facet)))
        else:
            cur = await db.execute("DELETE FROM memory_facets WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount


async def delete_one(user_id: int, mem_id: int) -> bool:
    from database import raw_db
    async with raw_db() as db:
        cur = await db.execute("DELETE FROM memory_facets WHERE id=? AND user_id=?",
                               (mem_id, user_id))
        await db.commit()
        return cur.rowcount > 0


async def facet_stats(user_id: int) -> dict:
    from database import raw_db
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT facet, COUNT(*), ROUND(AVG(importance),2) FROM memory_facets "
            "WHERE user_id=? GROUP BY facet", (user_id,))
    stats = {f: {"count": c, "avg_importance": a} for f, c, a in await cur.fetchall()}
    return stats


# ---------------------------------------------------------------------------
# Context builder (augmented prompt section)
# ---------------------------------------------------------------------------

def build_context(memories: list[Memory], budget_chars: int = 900) -> str:
    """Render memories into a compact, facet-tagged prompt section."""
    if not memories:
        return ""
    lines = []
    used = 0
    for m in memories:
        tag = m.facet
        prefix = f"[{tag}:{m.kind}]" if m.kind else f"[{tag}]"
        line = f"{prefix} {m.content}"
        if used + len(line) + 1 > budget_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


async def build_memory_context(user_id: int, query: str = "", budget: int = 900) -> str:
    """Drop-in replacement for memory.build_memory_context using multi-facet recall."""
    if not config.MEMORY2_ENABLED:
        return ""
    try:
        mems = await recall(user_id, query, limit=10)
        return build_context(mems, budget)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Auto-extraction via LLM (Gemini/OpenAI-compatible)
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = (
    "You are a long-term memory extractor. From the user's message(s) below, "
    "extract durable, useful facts and classify each into ONE facet: "
    "identity (name/birthday/language/timezone/occupation/location), factual, "
    "preference, behavioral, emotional, engagement, risk. "
    "Return ONLY a JSON array (no markdown) of objects: "
    '{"facet": "<facet>", "kind": "<short kind>", "content": "<short fact>", '
    '"importance": <1-5>}. Skip greetings, chit-chat, and transient text. '
    "If nothing durable, return []."
)


async def extract_memories(user_id: int, user_text: str, assistant_text: str = "") -> list[dict]:
    """Ask the agent to extract structured memories from a conversation turn."""
    if not config.MEMORY2_ENABLED or not user_text.strip():
        return []
    try:
        from media_v2 import system_chat
        messages = [
            {"role": "system", "content": _EXTRACT_PROMPT},
            {"role": "user", "content": f"USER: {user_text[:1500]}\n\nASSISTANT: {assistant_text[:800]}"},
        ]
        raw = await system_chat(messages, temperature=0.0, max_tokens=700)
        raw = raw.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.I | re.M).strip()
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("memories") or data.get("items") or []
        if not isinstance(data, list):
            return []
        out = []
        for item in data[:12]:
            if isinstance(item, dict):
                out.append({
                    "facet": _canon_facet(item.get("facet", "factual")),
                    "kind": item.get("kind", ""),
                    "content": item.get("content", ""),
                    "importance": float(item.get("importance", 3)),
                })
        return out
    except Exception as e:
        await db_log("memory2", "extraction failed", user_id=user_id, level="WARNING",
                     data={"err": str(e)[:300]})
        return []


def schedule_extraction(user_id: int, user_text: str, assistant_text: str = "") -> None:
    """Fire-and-forget extraction onto the running loop (safe to call anywhere)."""
    try:
        import asyncio
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(_extract_and_store(user_id, user_text, assistant_text))


async def _extract_and_store(user_id: int, user_text: str, assistant_text: str = "") -> None:
    items = await extract_memories(user_id, user_text, assistant_text)
    for it in items:
        if it.get("content"):
            sticky = it["facet"] == "identity" and it["kind"] in _STICKY_KINDS
            await remember(user_id, it["facet"], it["content"], it.get("kind", ""),
                           it.get("importance", 3), source="s2", sticky=sticky)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def evict_expired() -> int:
    """Prune non-sticky memories past config.MEMORY_EVICTION_DAYS."""
    from database import raw_db
    ttl = config.MEMORY_EVICTION_DAYS * 86400
    cutoff = time.time() - ttl
    async with raw_db() as db:
        cur = await db.execute(
            "DELETE FROM memory_facets WHERE updated_at < ? AND kind NOT IN "
            f"({','.join(repr(k) for k in _STICKY_KINDS)}) AND importance < 3", (cutoff,))
        await db.commit()
        return cur.rowcount


async def record_purchase(user_id: int, product: dict) -> None:
    """Feed purchase signals into engagement + behavioral + preference facets."""
    try:
        cat = (product or {}).get("category", "")
        title = (product or {}).get("title", "")
        price = (product or {}).get("price_credits") or (product or {}).get("price", 0)
        if cat:
            await remember(user_id, "preference", f"عاشق دستهٔ {cat}", kind="category",
                           importance=4, source="purchase")
        if title:
            await remember(user_id, "behavioral", f"خرید از محصول «{title}»", kind="purchase",
                           importance=3, source="purchase")
        await remember(user_id, "engagement", "خرید موفق انجام شد", kind="purchase",
                       importance=4, source="purchase",
                       metadata={"category": cat, "price": price})
        await db_log("memory2", "purchase->facet", user_id=user_id,
                     data={"category": cat, "price": price})
    except Exception:
        pass
