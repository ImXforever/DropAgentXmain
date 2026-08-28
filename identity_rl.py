"""
DropAgentX v2.0.0 — Identity reinforcement-learning agent.

Goal: learn a *small, actionable* identity label per user from their behaviour,
so the bot can personalise (wording, onboarding, offers) and so admins can spot
farming / high-value users without hand-labelling.

Approach (lightweight, no ML deps, pure Python):

  * State   = a discretised feature vector of the user's behaviour
              (visit count, purchases, tasks done, withdrawals, freshness,
               chat depth, session cadence).
  * Actions = a fixed set of identity labels.
  * Reward  = an event-driven signal: when we observe a real behaviour event we
              reward the labels that behaviour implies.
  * Update  = Q-learning (tabulated) with epsilon-greedy exploration, a learning
              rate and a discount factor. All tuned via env/config.

Persistence: a `rl_identity` table stores per-user Q-values and the live label,
so learning survives restarts and can be inspected by admins.
"""

import json
import math
import random
import time

from config import config
from observability import db_log

ACTIONS = [
    "new_user",         # freshly joined, few signals yet
    "browser",          # looks around, low intent
    "task_earner",      # farms credits via tasks (advertising)
    "returning_buyer",  # comes back and buys
    "high_value",       # withraws / big spender
    "supporter",        # engages deeply with the assistant / products
    "churn_risk",       # about to leave or refund
]

# Event -> reward per action. Missing entries = 0 reward (no update effect).
_EVENT_REWARD = {
    "purchase":       {"returning_buyer": 5.0, "high_value": 2.0, "supporter": 1.0},
    "withdraw":       {"high_value": 5.0, "returning_buyer": 1.0},
    "task_done":      {"task_earner": 4.0, "new_user": 0.5},
    "visit":          {"returning_buyer": 1.0, "supporter": 0.5, "new_user": 0.3},
    "chat_message":   {"supporter": 1.5, "returning_buyer": 0.5},
    "refund":         {"churn_risk": 3.0, "high_value": -1.0},
    "chargeback":     {"churn_risk": 5.0, "task_earner": -1.0},
    "mystery_box":    {"task_earner": 1.5, "returning_buyer": -0.5},
}

# Feature bucket boundaries (features are normalised 0..N into buckets).
_BUCKETS = {"visits": 4, "purchases": 4, "tasks": 4, "withdraws": 3,
            "chat_level": 4, "session_bucket": 4, "freshness": 2}


class IdentityRL:
    """Tabulated Q-learning identity classifier (persisted per user)."""

    def __init__(self, user_id: int):
        self.user_id = int(user_id)
        self.alpha = config.RL_LEARN_RATE
        self.gamma = config.RL_GAMMA
        self.epsilon = config.RL_EXPLORE

    # ---- feature/state --------------------------------
    async def _features(self) -> dict:
        from database import raw_db
        async with raw_db() as db:
            u = await db.execute(
                "SELECT created_at, products_sold FROM users WHERE user_id=?", (self.user_id,))
            user = await u.fetchone()
            bought = await db.execute(
                "SELECT COUNT(*) FROM purchases WHERE buyer_id=?", (self.user_id,))
            n_bought = (await bought.fetchone())[0]
            chats = await db.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id=?", (self.user_id,))
            n_chat = (await chats.fetchone())[0]
            tasks = await db.execute(
                "SELECT COUNT(*) FROM tasks_done WHERE user_id=?",
                (self.user_id,)) if _has_tasks_done() else None
            n_tasks = (await tasks.fetchone())[0] if tasks else 0
            # withdrawal success from (unique) withdraws
            wd = await db.execute(
                "SELECT COUNT(*) FROM withdrawals WHERE user_id=? AND status='paid'",
                (self.user_id,))
            n_wd = (await wd.fetchone())[0]
        created = float(user[0] or time.time()) if user else time.time()
        age_days = max(0.0, (time.time() - created) / 86400)
        feats = {
            "visits": n_chat + n_bought,          # proxy for returning activity
            "purchases": n_bought,
            "tasks": n_tasks,
            "withdraws": n_wd,
            "chat_level": n_chat,
            "session_bucket": int(time.localtime().tm_hour / 6),
            "freshness": 1 if age_days < 2 else 0,
        }
        return feats

    def _state(self, feats: dict) -> str:
        parts = []
        for k, b in _BUCKETS.items():
            v = int(min(feats.get(k, 0), b - 1))
            parts.append(f"{k}:{v}")
        return "|".join(parts)

    @staticmethod
    def _hash_state(state: str) -> int:
        # F4-0.6.0: hash() پایتون در هر پروسه تصادفی است (PYTHONHASHSEED) — بعد از
        # هر ری‌استارت bucketها عوض و حافظهٔ RL ذخیره‌شده در DB بی‌اعتبار می‌شد.
        import hashlib as _hl
        return int.from_bytes(_hl.blake2b(state.encode(), digest_size=4).digest(), "big") % 100000

    # ---- Q persistence ---------------------------------
    async def _load_q(self) -> dict:
        from database import raw_db
        async with raw_db() as db:
            cur = await db.execute(
                "SELECT qvalues, label FROM rl_identity WHERE user_id=?", (self.user_id,))
            row = await cur.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return {}
        return {}

    async def _save_q(self, q: dict, label: str) -> None:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO rl_identity (user_id, qvalues, label, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET qvalues=excluded.qvalues, "
                "label=excluded.label, updated_at=excluded.updated_at",
                (self.user_id, json.dumps(q, ensure_ascii=False), label, time.time()))
            await db.commit()

    # ---- core RL ---------------------------------------
    async def act(self) -> str:
        """Pick the current identity label (epsilon-greedy)."""
        q = await self._load_q()
        if not q or random.random() < self.epsilon:
            return random.choice(ACTIONS)
        state = self._state(await self._features())
        h = self._hash_state(state)
        qs = q.get(str(h), {})
        return max(ACTIONS, key=lambda a: qs.get(a, 0.0))

    async def learn(self, event: str) -> str:
        """Apply a reward from a real behaviour event. Returns updated label."""
        reward = _EVENT_REWARD.get(event)
        if not reward:
            return await self.profile_label()
        feats = await self._features()
        state = self._state(feats)
        h = str(self._hash_state(state))
        q = await self._load_q()
        qs = q.setdefault(h, {a: 0.0 for a in ACTIONS})
        # current best next-state value (same state loop: use current max)
        max_next = max(qs.values()) if qs else 0.0
        for action, r in reward.items():
            if action not in qs:
                qs[action] = 0.0
            qs[action] += self.alpha * (r + self.gamma * max_next - qs[action])
        # decay the others a touch so the winner dominates
        label = max(ACTIONS, key=lambda a: qs.get(a, 0.0))
        await self._save_q(q, label)
        await db_log("identity_rl", f"learn event={event}", user_id=self.user_id,
                     level="INFO", data={"label": label})
        return label

    async def profile_label(self) -> str:
        q = await self._load_q()
        if not q:
            return "new_user"
        # majority vote across all recorded states
        totals = {a: 0.0 for a in ACTIONS}
        for qs in q.values():
            for a, v in qs.items():
                totals[a] = totals.get(a, 0.0) + v
        return max(ACTIONS, key=lambda a: totals.get(a, 0.0))

    async def confidence(self) -> float:
        """Softmax-ish confidence in the winning label (0..1)."""
        q = await self._load_q()
        if not q:
            return 0.0
        totals = {a: 0.0 for a in ACTIONS}
        for qs in q.values():
            for a, v in qs.items():
                totals[a] = totals.get(a, 0.0) + v
        best = max(totals.values())
        denom = sum(math.exp(v) for v in totals.values() if v >= best - 20)
        return min(1.0, round(math.exp(best) / denom, 3)) if denom else 0.0

    async def snapshot(self) -> dict:
        feats = await self._features()
        return {
            "user_id": self.user_id,
            "label": await self.profile_label(),
            "confidence": await self.confidence(),
            "q": await self._load_q(),
            "features": feats,
            "state": self._state(feats),
        }


def _has_tasks_done() -> bool:
    # tasks_done may not exist on older schemas; the caller guards with this flag.
    try:
        import os
        return os.getenv("RL_TASKS_TABLE", "1") == "1"
    except Exception:
        return True


async def init_tables() -> None:
    from database import raw_db
    async with raw_db() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rl_identity (
                user_id INTEGER PRIMARY KEY,
                qvalues TEXT DEFAULT '{}',
                label TEXT DEFAULT 'new_user',
                updated_at REAL DEFAULT (strftime('%s','now'))
            )""")
        # tasks_done table (used for reward signal) is created only if missing.
        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks_done (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER,
                    reward INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )""")
            await db.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Convenience API used by handlers / startup
# ---------------------------------------------------------------------------

async def get_identity(user_id: int) -> dict:
    agent = IdentityRL(user_id)
    return await agent.snapshot()


async def signal(user_id: int, event: str) -> None:
    """Fire-and-forget reward signal on a real behaviour event."""
    if not config.IDENTITY_RL_ENABLED:
        return
    try:
        agent = IdentityRL(user_id)
        await agent.learn(event)
    except Exception as e:
        await db_log("identity_rl", "signal failed", user_id=user_id,
                     level="WARNING", data={"err": str(e)[:300]})
