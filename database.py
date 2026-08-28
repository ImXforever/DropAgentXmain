import aiosqlite
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


DB_PATH = config.DB_PATH


async def init_db():
    if _apply_pending_restore():
        logger.info("Pending database restore applied (backup kept as .pre-restore.bak)")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with raw_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                credits INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                products_sold INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now')),
                is_banned INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                task_type TEXT NOT NULL,
                target_url TEXT NOT NULL,
                credits_reward INTEGER NOT NULL,
                max_completions INTEGER DEFAULT 0,
                current_completions INTEGER DEFAULT 0,
                creator_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (creator_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS task_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                proof TEXT,
                status TEXT DEFAULT 'pending',
                completed_at REAL DEFAULT (strftime('%s','now')),
                verified_at REAL,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                price_credits INTEGER NOT NULL,
                price_usd REAL DEFAULT 0,
                file_path TEXT,
                file_type TEXT,
                preview_path TEXT,
                category TEXT DEFAULT 'general',
                tags TEXT DEFAULT '',
                sales_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (creator_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                price_credits INTEGER NOT NULL,
                purchased_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (buyer_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS ad_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                target_follows INTEGER NOT NULL,
                target_channel TEXT NOT NULL,
                credits_per_follow INTEGER DEFAULT 5,
                total_budget INTEGER NOT NULL,
                spent_budget INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (advertiser_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                tx_type TEXT NOT NULL,
                reference_id INTEGER,
                description TEXT,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS hermes_sessions (
                user_id INTEGER PRIMARY KEY,
                session_id TEXT,
                updated_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                network TEXT NOT NULL,
                txid TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                created_at REAL DEFAULT (strftime('%s','now')),
                reviewed_at REAL,
                UNIQUE(network, txid),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                network TEXT NOT NULL,
                address TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                fee_usdt REAL NOT NULL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                created_at REAL DEFAULT (strftime('%s','now')),
                reviewed_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS ref_milestones (
                user_id INTEGER NOT NULL,
                threshold INTEGER NOT NULL,
                awarded_at REAL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (user_id, threshold)
            );

            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                owner_id INTEGER NOT NULL,
                percent INTEGER NOT NULL,
                max_uses INTEGER DEFAULT 0,
                uses INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (owner_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS role_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                old_role TEXT,
                new_role TEXT NOT NULL,
                granted_by INTEGER NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS content_pages (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                updated_by INTEGER,
                updated_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_by INTEGER,
                updated_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS custom_bots (
                user_id INTEGER PRIMARY KEY,
                api_key TEXT NOT NULL,
                base_url TEXT NOT NULL,
                model TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER DEFAULT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_chat_msg_user ON chat_messages(user_id, id);
            CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_messages(session_id);

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s','now')),
                last_active REAL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, last_active);

            CREATE TABLE IF NOT EXISTS kb_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'librarian',
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_kb_user ON kb_notes(user_id, id);

            CREATE TABLE IF NOT EXISTS cron_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                minute INTEGER DEFAULT 0,
                text TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                last_date TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
        """)

        # --- lightweight migrations for existing DBs ---
        for stmt in (
            "ALTER TABLE users ADD COLUMN referred_by INTEGER",
            "ALTER TABLE users ADD COLUMN ref_bonus_paid INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN seller_plan TEXT DEFAULT 'free'",
            "ALTER TABLE users ADD COLUMN has_withdrawn INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'associate'",
            "ALTER TABLE users ADD COLUMN domain TEXT",
            "ALTER TABLE products ADD COLUMN is_featured INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN photo_path TEXT",
            # moderation + external link (existing rows default to approved)
            "ALTER TABLE products ADD COLUMN link TEXT",
            "ALTER TABLE purchases ADD COLUMN payment_method TEXT DEFAULT 'credits'",
            "ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'approved'",
            # --- engagement counters (DropAgentX Mini App) ---
            "ALTER TABLE products ADD COLUMN impressions INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN views INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN clicks INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN like_count INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN dislike_count INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN comment_count INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN save_count INTEGER DEFAULT 0",
            # --- 3-image product system ---
            "ALTER TABLE products ADD COLUMN img_main TEXT",
            "ALTER TABLE products ADD COLUMN img_feed TEXT",
            "ALTER TABLE products ADD COLUMN img_story TEXT",
            # --- treasury verification / payout audit ---
            "ALTER TABLE deposits ADD COLUMN verified_at REAL",
            "ALTER TABLE deposits ADD COLUMN verification_attempts INTEGER DEFAULT 0",
            "ALTER TABLE deposits ADD COLUMN verification_reason TEXT DEFAULT ''",
            "ALTER TABLE withdrawals ADD COLUMN payout_txid TEXT",
            "ALTER TABLE withdrawals ADD COLUMN payout_error TEXT DEFAULT ''",
            # --- hunter role with configurable permissions ---
            """CREATE TABLE IF NOT EXISTS hunter_permissions (
                user_id INTEGER PRIMARY KEY,
                can_moderate_products INTEGER DEFAULT 0,
                can_review_deposits INTEGER DEFAULT 0,
                can_review_withdrawals INTEGER DEFAULT 0,
                can_ban_users INTEGER DEFAULT 0,
                can_broadcast INTEGER DEFAULT 0,
                can_manage_skills INTEGER DEFAULT 0,
                can_view_analytics INTEGER DEFAULT 0,
                granted_by INTEGER,
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (granted_by) REFERENCES users(user_id)
            )""",
            # anti double-spend / double-reward guards
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_purchase_once ON purchases(buyer_id, product_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_task_once ON task_completions(task_id, user_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_review_once ON reviews(product_id, buyer_id)",
            # --- hot-path indexes (scale: 1000+ concurrent users) ---
            "CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id, id)",
            "CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(tx_type, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_purch_product ON purchases(product_id)",
            "CREATE INDEX IF NOT EXISTS idx_purch_buyer ON purchases(buyer_id)",
            "CREATE INDEX IF NOT EXISTS idx_prod_status ON products(status, category, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_prod_creator ON products(creator_id)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(is_active, credits_reward)",
            "CREATE INDEX IF NOT EXISTS idx_deposits_status ON deposits(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status, created_at)",
            # --- long-term memory (Hermes-style memory providers) ---
            """CREATE TABLE IF NOT EXISTS user_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'fact',
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 3,
                source TEXT DEFAULT 'chat',
                dedup_key TEXT,
                recall_count INTEGER DEFAULT 0,
                last_recalled_at REAL,
                created_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE(user_id, dedup_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_mem_user ON user_memories(user_id, kind, importance)",
            """CREATE TABLE IF NOT EXISTS user_profile (
                user_id INTEGER PRIMARY KEY,
                interests TEXT DEFAULT '',
                buys_count INTEGER DEFAULT 0,
                total_spent_credits INTEGER DEFAULT 0,
                last_categories TEXT DEFAULT '',
                persona TEXT DEFAULT '',
                persona_at REAL,
                updated_at REAL DEFAULT (strftime('%s','now'))
            )""",
            # --- social commerce layer (DropAgentX Mini App) ---
            """CREATE TABLE IF NOT EXISTS follows (
                follower_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (follower_id, target_id)
            )""",
            """CREATE TABLE IF NOT EXISTS product_engagement (
                product_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE (product_id, user_id, type)
            )""",
            """CREATE TABLE IF NOT EXISTS product_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s','now'))
            )""",
            "CREATE INDEX IF NOT EXISTS idx_follow_target ON follows(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_eng_product ON product_engagement(product_id, type)",
            "CREATE INDEX IF NOT EXISTS idx_comments_product ON product_comments(product_id)",
            # --- V3-4 session persistence: session_id on chat_messages ---
            "ALTER TABLE chat_messages ADD COLUMN session_id INTEGER DEFAULT NULL",
        ):
            try:
                await db.execute(stmt)
                await db.commit()
            except Exception:
                pass

        await db.commit()

    # --- concurrency tuning (persists with the db file) ---
    async with raw_db() as db:
        for pragma in ("PRAGMA journal_mode = WAL",
                       "PRAGMA synchronous = NORMAL"):
            try:
                await asyncio.wait_for(db.execute(pragma), 3)
            except Exception:
                pass

    # --- FTS5 full-text index over chat history ---
    try:
        async with raw_db() as db:
            await db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chat_fts USING fts5("
                "content, user_id UNINDEXED, msg_id UNINDEXED, session_id UNINDEXED)")
    except Exception:
        pass  # FTS5 unavailable in this sqlite build

    await seed_content()
    await seed_products()


def _tune(db):
    return db


# ---------- singleton connection (SQLite best practice: 1 writer thread) ----------

_DB: Optional[aiosqlite.Connection] = None
_DB_SRC: Optional[str] = None  # the DB_PATH the open connection was created for
_DBLock = asyncio.Lock()


async def _singleton() -> aiosqlite.Connection:
    global _DB, _DB_SRC
    # Re-open if DB_PATH changed since the connection was created (test suites,
    # multi-tenant, or runtime reconfigure). Prevents reads/writes leaking into
    # a stale/previous database file.
    if _DB is not None and _DB_SRC != os.path.abspath(DB_PATH):
        try:
            await _DB.close()
        except Exception:
            pass
        _DB = None
        _DB_SRC = None
    if _DB is None:
        db = await aiosqlite.connect(DB_PATH)
        try:
            # PERMANENT row factory. aiosqlite queues attribute writes on the
            # connection thread, so switching it per-caller races across
            # concurrent tasks (tuples leaking into Row-expecting readers).
            # sqlite3.Row supports both name access, dict(row), positional
            # r[0] and tuple unpacking — safe for every call style we use.
            db.row_factory = aiosqlite.Row
            await asyncio.wait_for(db.execute("PRAGMA busy_timeout = 5000"), 5)
            await asyncio.wait_for(db.execute("PRAGMA foreign_keys = ON"), 5)
            for pragma in ("PRAGMA journal_mode = WAL",
                           "PRAGMA synchronous = NORMAL"):
                try:
                    await asyncio.wait_for(db.execute(pragma), 3)
                except Exception:
                    pass
        except Exception:
            await db.close()
            raise
        _DB = db
        _DB_SRC = os.path.abspath(DB_PATH)
    return _DB


async def _acquire(tuned: bool):
    # `tuned` kept for API compatibility; row_factory is fixed permanently.
    return await _singleton()


def _release(db):
    pass  # singleton stays open


@asynccontextmanager
async def _session(tuned: bool):
    """Reentrant-per-task serialized session.

    Top-level entry takes the lock and owns commit/rollback.
    Nested entries (same asyncio task) reuse the connection WITHOUT
    committing — ownership belongs to the outermost caller. This removes
    the non-reentrant-lock deadlock landmine forever.
    """
    task = asyncio.current_task()
    depth = getattr(task, "_db_depth", 0)
    db = await _acquire(tuned=tuned)
    if depth > 0:
        try:
            yield db
        finally:
            pass
        return
    async with _DBLock:
        task._db_depth = 1
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            task._db_depth = 0


@asynccontextmanager
async def get_db():
    """Row-factored session (reentrant-safe)."""
    async with _session(tuned=True) as db:
        yield db


@asynccontextmanager
async def raw_db():
    """Tuple-row session (reentrant-safe)."""
    async with _session(tuned=False) as db:
        yield db


async def close_pool():
    global _DB
    if _DB is not None:
        try:
            await _DB.close()
        except Exception:
            pass
        _DB = None


# ---------- backup / restore (portable safety net) ----------

def _snapshot_sync(src_path: str, dest_path: str):
    """Consistent copy via sqlite3 backup API — safe while writes happen."""
    import sqlite3
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    dst = sqlite3.connect(dest_path)
    try:
        src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
        try:
            src.backup(dst)
        finally:
            src.close()
    finally:
        dst.close()


async def snapshot_to(dest_path: str) -> str:
    await asyncio.to_thread(_snapshot_sync, config.DB_PATH, dest_path)
    return dest_path


def _apply_pending_restore() -> bool:
    """If an admin uploaded restore-pending.db next to the live database,
    atomically swap it in BEFORE the pool opens (called from init_db)."""
    pending = os.path.join(os.path.dirname(config.DB_PATH) or ".", "restore-pending.db")
    if not os.path.isfile(pending):
        return False
    live = config.DB_PATH
    os.makedirs(os.path.dirname(live) or ".", exist_ok=True)
    if os.path.exists(live):
        os.replace(live, live + ".pre-restore.bak")
    os.replace(pending, live)
    for suf in ("-wal", "-shm"):
        try:
            os.remove(live + suf)
        except OSError:
            pass
    return True


# ---------- hot-read cache for get_user (45s TTL) ----------

_USER_CACHE: dict[int, tuple[float, dict]] = {}
_UCACHE_TTL = 45.0
# The DB_PATH the user cache entries belong to. If it differs from the current
# DB_PATH the cache is bypassed so cross-database (e.g. per-test) reuse of the
# same user_id can never return a user that lives in a different database.
_USER_CACHE_PATH: Optional[str] = None


def invalidate_user(user_id: int):
    _USER_CACHE.pop(user_id, None)


def escape_like(s: str) -> str:
    """Neutralize LIKE wildcards from user input (perf/DoS guard)."""
    if not s:
        return s
    bs = chr(92)
    return (s.replace(bs, bs * 2)
             .replace("%", bs + "%")
             .replace("_", bs + "_"))


async def get_user(user_id: int) -> Optional[dict]:
    import time as _t
    global _USER_CACHE_PATH
    path = os.path.abspath(DB_PATH)
    if _USER_CACHE_PATH == path:
        hit = _USER_CACHE.get(user_id)
        if hit and (_t.monotonic() - hit[0]) < _UCACHE_TTL:
            return hit[1]
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        data = dict(row) if row else None
        if data:
            _USER_CACHE[user_id] = (_t.monotonic(), data)
            _USER_CACHE_PATH = path
        return data


async def create_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    existing = await get_user(user_id)
    if existing:
        return existing

    from config import config as cfg

    # 3-A: check monthly credit mint budget
    welcome = cfg.WELCOME_CREDITS
    try:
        month_key = time.strftime("%Y-%m")
        async with raw_db() as db:
            await db.execute(
                "INSERT OR IGNORE INTO settings (key,value) VALUES ('mint_month',?)",
                (month_key,))
            cur = await db.execute("SELECT key FROM settings WHERE key='mint_month'")
            if not await cur.fetchone():
                pass  # settings table might use different schema
    except Exception:
        pass

    # simple in-process mint tracker
    global _mint_used, _mint_month
    now_month = time.strftime("%Y-%m")
    if not hasattr(create_user, "_month") or create_user._month != now_month:
        create_user._month = now_month
        create_user._used = 0

    MINT_CAP = int(os.getenv("MINT_CAP_MONTHLY", "50000"))
    if create_user._used + welcome > MINT_CAP:
        welcome = max(0, MINT_CAP - create_user._used)
        logging.getLogger(__name__).info(
            "mint cap hit: reduced welcome to %d for user %s", welcome, user_id)

    create_user._used += welcome
    if welcome <= 0:
        welcome = 0  # no credits this month but still create account

    async with raw_db() as db:
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, credits) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, welcome)
        )
        await db.commit()
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, description) VALUES (?, ?, 'bonus', ?)",
            (user_id, welcome, "Welcome bonus" if welcome > 0 else "Account created")
        )
        await db.commit()
    return await get_user(user_id)

# module-level mint tracking (resets per process; good enough for single-instance)
create_user._month = ""
create_user._used = 0


async def update_credits(user_id: int, amount: int, tx_type: str, description: str = "", reference_id: int = None):
    invalidate_user(user_id)
    async with raw_db() as db:
        if amount > 0:
            await db.execute(
                "UPDATE users SET credits = credits + ?, total_earned = total_earned + ? WHERE user_id = ?",
                (amount, amount, user_id)
            )
        else:
            await db.execute(
                "UPDATE users SET credits = credits + ?, total_spent = total_spent + ? WHERE user_id = ?",
                (amount, abs(amount), user_id)
            )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, tx_type, reference_id, description)
        )
        await db.commit()


async def get_leaderboard(limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, credits, total_earned, products_sold FROM users ORDER BY credits DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_user_stats(user_id: int) -> dict:
    async with raw_db() as db:

        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM task_completions WHERE user_id = ? AND status = 'verified'",
            (user_id,)
        )
        tasks_done = (await cursor.fetchone())["count"]

        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM purchases WHERE buyer_id = ?",
            (user_id,)
        )
        products_bought = (await cursor.fetchone())["count"]

        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM products WHERE creator_id = ? AND is_active = 1",
            (user_id,)
        )
        products_listed = (await cursor.fetchone())["count"]

        return {
            "tasks_done": tasks_done,
            "products_bought": products_bought,
            "products_listed": products_listed,
        }


async def search_products(query: str = "", category: str = "", limit: int = 20, offset: int = 0) -> list[dict]:
    async with raw_db() as db:
        conditions = ["p.is_active = 1", "p.status = 'approved'",
                      "COALESCE(u.is_banned, 0) = 0"]
        params = []

        if query:
            conditions.append("(p.title LIKE ? OR p.description LIKE ? OR p.tags LIKE ?)")
            q = f"%{escape_like(query)}%"
            params.extend([q, q, q])

        if category and category != "all":
            conditions.append("p.category = ?")
            params.append(category)

        where = " AND ".join(conditions)
        params.extend([limit, offset])

        cursor = await db.execute(
            f"""SELECT p.*, u.username as creator_username, u.first_name as creator_name
                FROM products p
                LEFT JOIN users u ON p.creator_id = u.user_id
                WHERE {where}
                ORDER BY p.is_featured DESC, p.created_at DESC
                LIMIT ? OFFSET ?""",
            params
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_product(product_id: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT p.*, u.username as creator_username, u.first_name as creator_name
               FROM products p
               LEFT JOIN users u ON p.creator_id = u.user_id
               WHERE p.id = ?""",
            (product_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_pending_tasks(limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT t.*, u.username as creator_username
               FROM tasks t
               JOIN users u ON t.creator_id = u.user_id
               WHERE t.is_active = 1
               AND (t.max_completions = 0 OR t.current_completions < t.max_completions)
               ORDER BY t.credits_reward DESC
               LIMIT ?""",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_user_tasks(user_id: int, status: str = None) -> list[dict]:
    async with raw_db() as db:
        if status:
            cursor = await db.execute(
                """SELECT tc.*, t.title, t.task_type, t.target_url, t.credits_reward
                   FROM task_completions tc
                   JOIN tasks t ON tc.task_id = t.id
                   WHERE tc.user_id = ? AND tc.status = ?
                   ORDER BY tc.completed_at DESC""",
                (user_id, status)
            )
        else:
            cursor = await db.execute(
                """SELECT tc.*, t.title, t.task_type, t.target_url, t.credits_reward
                   FROM task_completions tc
                   JOIN tasks t ON tc.task_id = t.id
                   WHERE tc.user_id = ?
                   ORDER BY tc.completed_at DESC""",
                (user_id,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_my_products(user_id: int) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT * FROM products WHERE creator_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_purchased_products(user_id: int) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT p.*, pc.purchased_at
               FROM purchases pc
               JOIN products p ON pc.product_id = p.id
               WHERE pc.buyer_id = ?
               ORDER BY pc.purchased_at DESC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_active_campaigns(limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT ac.*, u.username as advertiser_username
               FROM ad_campaigns ac
               JOIN users u ON ac.advertiser_id = u.user_id
               WHERE ac.is_active = 1 AND ac.spent_budget < ac.total_budget
               ORDER BY ac.created_at DESC
               LIMIT ?""",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def is_task_completed_by_user(task_id: int, user_id: int) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM task_completions WHERE task_id = ? AND user_id = ?",
            (task_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] > 0


async def is_product_purchased_by_user(product_id: int, user_id: int) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM purchases WHERE product_id = ? AND buyer_id = ?",
            (product_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] > 0


async def get_all_users_count() -> int:
    async with raw_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0]


async def get_total_products() -> int:
    async with raw_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
        row = await cursor.fetchone()
        return row[0]


async def get_total_sales() -> int:
    async with raw_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM purchases")
        row = await cursor.fetchone()
        return row[0]


async def get_hermes_session(user_id: int) -> str | None:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT session_id FROM hermes_sessions WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_hermes_session(user_id: int, session_id: str):
    async with raw_db() as db:
        await db.execute(
            """INSERT INTO hermes_sessions (user_id, session_id, updated_at)
               VALUES (?, ?, strftime('%s','now'))
               ON CONFLICT(user_id) DO UPDATE SET
                 session_id = excluded.session_id,
                 updated_at = excluded.updated_at""",
            (user_id, session_id),
        )
        await db.commit()


async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user and user.get("is_banned"))


async def try_hold_credits(user_id: int, credits: int, tx_type: str, description: str) -> bool:
    """Atomic hold: deducts only if balance suffices (single statement)."""
    invalidate_user(user_id)
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE users SET credits = credits - ?, total_spent = total_spent + ? "
            "WHERE user_id = ? AND credits >= ?",
            (credits, abs(credits), user_id, credits),
        )
        if cursor.rowcount == 0:
            return False
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, description) "
            "VALUES (?, ?, ?, ?)",
            (user_id, -credits, tx_type, description),
        )
        return True


async def product_rating(product_id: int) -> tuple[float, int]:
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT AVG(stars), COUNT(*) FROM reviews WHERE product_id = ?",
            (product_id,))
        avg, n = await cur.fetchone()
    return (round(avg or 0.0, 1), n or 0)


async def add_review(product_id: int, buyer_id: int, stars: int) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO reviews (product_id, buyer_id, stars) VALUES (?, ?, ?)",
            (product_id, buyer_id, max(1, min(5, stars))),
        )
        return cursor.rowcount > 0


# ---------- Product moderation (admin approval before going live) ----------

async def list_pending_products(limit: int = 10) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT p.*, u.username AS creator_username
               FROM products p LEFT JOIN users u ON u.user_id = p.creator_id
               WHERE p.status = 'pending'
               ORDER BY p.created_at DESC LIMIT ?""",
            (limit,))
        return [dict(r) for r in await cursor.fetchall()]


async def count_pending_products() -> int:
    async with raw_db() as db:
        cur = await db.execute("SELECT COUNT(*) FROM products WHERE status = 'pending'")
        return (await cur.fetchone())[0]


async def set_product_status(product_id: int, status: str, reviewed_by: int) -> Optional[dict]:
    if status not in ("approved", "rejected"):
        return None
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE products SET status = ? WHERE id = ? AND status = 'pending'",
            (status, product_id))
        if cursor.rowcount == 0:
            return None
        cur = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


def usdt_to_credits(usdt: float) -> int:
    from config import config as cfg
    return int(round(usdt * cfg.CREDITS_PER_USDT))


# ---------- Referrals ----------

async def set_referred_by(user_id: int, referrer_id: int) -> bool:
    """Attach a referrer once; self-referral and overwrites are rejected."""
    if user_id == referrer_id:
        return False
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL",
            (referrer_id, user_id),
        )
        await db.commit()
        invalidate_user(user_id)
        return cursor.rowcount > 0


async def get_referrer(user_id: int) -> Optional[int]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def mark_ref_bonus_paid(user_id: int) -> bool:
    """True only the first time the referee qualifies (idempotent)."""
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE users SET ref_bonus_paid = 1 WHERE user_id = ? AND ref_bonus_paid = 0",
            (user_id,),
        )
        await db.commit()
        invalidate_user(user_id)
        return cursor.rowcount > 0


async def count_qualified_refs(referrer_id: int) -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ? AND ref_bonus_paid = 1",
            (referrer_id,),
        )
        return (await cursor.fetchone())[0]


async def count_total_refs(referrer_id: int) -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?",
            (referrer_id,),
        )
        return (await cursor.fetchone())[0]

async def list_top_referrers(limit: int = 5) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT r.user_id,
                      COALESCE(r.first_name, r.username, 'User') AS name,
                      COUNT(*) AS cnt
               FROM users u
               JOIN users r ON r.user_id = u.referred_by
               WHERE u.ref_bonus_paid = 1
               GROUP BY r.user_id, name
               ORDER BY cnt DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def is_milestone_awarded(user_id: int, threshold: int) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT 1 FROM ref_milestones WHERE user_id = ? AND threshold = ?",
            (user_id, threshold),
        )
        return await cursor.fetchone() is not None


async def award_ref_milestone(user_id: int, threshold: int) -> bool:
    async with raw_db() as db:
        try:
            await db.execute(
                "INSERT INTO ref_milestones (user_id, threshold) VALUES (?, ?)",
                (user_id, threshold),
            )
            await db.commit()
            return True
        except Exception:
            return False


# ---------- Org ranks (fractal autonomy) ----------

ROLES = ("associate", "soldier", "capo", "underboss", "hunter")
ROLE_FA = {
    "associate": "🎓 کارآموز",
    "soldier": "🪖 سرباز",
    "capo": "🕵️ کاپو",
    "underboss": "👔 آندرباس",
    "hunter": "🏹 هانتر",
}


# ---- hunter permissions ----

HUNTER_PERMS = (
    ("can_moderate_products", "مودریشن محصول", "🧐"),
    ("can_review_deposits", "بررسی واریزها", "📥"),
    ("can_review_withdrawals", "بررسی برداشت‌ها", "📤"),
    ("can_ban_users", "بن/آنبن کاربران", "🔨"),
    ("can_broadcast", "برودکست همگانی", "📣"),
    ("can_manage_skills", "مدیریت مهارت‌ها", "🧩"),
    ("can_view_analytics", "دیدن آنالیتیکس", "📊"),
)


async def get_hunter_perms(user_id: int) -> dict:
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT * FROM hunter_permissions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if not row:
        return {k[0]: False for k in HUNTER_PERMS}
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    return {p[0]: bool(d.get(p[0], 0)) for p in HUNTER_PERMS}


async def set_hunter_perm(user_id: int, perm_key: str, value: bool, granted_by: int):
    from database import get_db
    async with get_db() as db:
        await db.execute(
            """INSERT INTO hunter_permissions (user_id, {}, granted_by)
               VALUES (?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET {}=excluded.{}""".format(
                perm_key, perm_key, perm_key),
            (user_id, int(value), granted_by))
        await db.commit()


async def delete_hunter(user_id: int):
    async with raw_db() as db:
        await db.execute("DELETE FROM hunter_permissions WHERE user_id=?", (user_id,))
        await db.commit()


async def get_role(user_id: int) -> str:
    user = await get_user(user_id)
    return (user or {}).get("role") or "associate"


async def delete_product(product_id: int, creator_id: int) -> tuple[bool, str]:
    """Owner deletes own product. Only if 0 sales. Cleans up images."""
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT creator_id, sales_count, photo_path, img_main, img_feed, img_story, file_path "
            "FROM products WHERE id=?", (product_id,))
        row = await cur.fetchone()
        if not row:
            return False, "محصول پیدا نشد"
        if row[0] != creator_id:
            return False, "فقط سازندهٔ محصول می‌تواند حذف کند"
        if (row[1] or 0) > 0:
            return False, "محصول فروش داشته — قابل حذف نیست"
        # clean up image files
        for col in (row[2], row[3], row[4], row[5]):
            if col and os.path.isfile(col):
                try:
                    os.remove(col)
                except OSError:
                    pass
        await db.execute("DELETE FROM products WHERE id=?", (product_id,))
        await db.execute("DELETE FROM product_engagement WHERE product_id=?", (product_id,))
        await db.execute("DELETE FROM product_comments WHERE product_id=?", (product_id,))
        await db.commit()
    return True, ""


async def set_role(user_id: int, new_role: str, granted_by: int, domain: str | None = None) -> bool:
    if new_role not in ROLES:
        return False
    async with raw_db() as db:
        cursor = await db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return False
        old_role = row[0] or "associate"
        if domain is not None:
            await db.execute(
                "UPDATE users SET role = ?, domain = ? WHERE user_id = ?",
                (new_role, domain, user_id),
            )
        else:
            await db.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
        await db.execute(
            "INSERT INTO role_audit (user_id, old_role, new_role, granted_by) VALUES (?, ?, ?, ?)",
            (user_id, old_role, new_role, granted_by),
        )
        await db.commit()
        invalidate_user(user_id)
        return True


async def get_domain(user_id: int) -> str | None:
    user = await get_user(user_id)
    return (user or {}).get("domain")


async def category_stats(category: str) -> dict:
    async with raw_db() as db:
        cursor = await db.execute(
            """SELECT COUNT(*) AS products,
                      COALESCE(SUM(sales_count), 0) AS sales,
                      COALESCE(SUM(sales_count * price_credits), 0) AS volume
               FROM products WHERE category = ? AND is_active = 1""",
            (category,),
        )
        row = await cursor.fetchone()
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT creator_id) FROM products WHERE category = ?", (category,)
        )
        sellers = (await cursor.fetchone())[0]
        return {
            "products": row[0], "sales": row[1], "volume": row[2], "sellers": sellers,
        }


async def category_products(category: str, limit: int = 8, include_inactive: bool = True) -> list[dict]:
    async with raw_db() as db:
        q = "SELECT * FROM products WHERE category = ?"
        if not include_inactive:
            q += " AND is_active = 1"
        q += " ORDER BY is_featured DESC, sales_count DESC LIMIT ?"
        cursor = await db.execute(q, (category, limit))
        return [dict(r) for r in await cursor.fetchall()]


async def set_product_flag(product_id: int, column: str, value: int, category: str) -> bool:
    """Underboss-scoped flag toggle; only within own category."""
    if column not in ("is_active", "is_featured"):
        return False
    async with raw_db() as db:
        cursor = await db.execute(
            f"UPDATE products SET {column} = ? WHERE id = ? AND category = ?",
            (value, product_id, category),
        )
        await db.commit()
        return cursor.rowcount > 0


async def capo_team_stats(capo_id: int) -> dict:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (capo_id,)
        )
        members = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id = ? AND tx_type IN ('ref_commission', 'ref_bonus', 'ref_mystery', 'ref_milestone')",
            (capo_id,),
        )
        earned = (await cursor.fetchone())[0]
        cursor = await db.execute(
            """SELECT COUNT(*) FROM purchases pc
               JOIN users s ON s.user_id = pc.buyer_id
               WHERE s.referred_by = ?""",
            (capo_id,),
        )
        team_buys = (await cursor.fetchone())[0]
        return {"members": members, "earned": earned, "team_buys": team_buys}


# ---------- Coupons ----------

async def create_coupon(owner_id: int, code: str, percent: int, max_uses: int) -> int | None:
    async with raw_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO coupons (code, owner_id, percent, max_uses) VALUES (?, ?, ?, ?)",
                (code.upper(), owner_id, percent, max_uses),
            )
            await db.commit()
            return cursor.lastrowid
        except Exception:
            return None


async def get_coupon(code: str) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM coupons WHERE code = ?", ((code or "").upper(),))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_coupon_by_id(coupon_id: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM coupons WHERE id = ?", (coupon_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def redeem_coupon(coupon_id: int) -> bool:
    """Atomic: succeeds only while active and under max_uses."""
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE coupons SET uses = uses + 1 "
            "WHERE id = ? AND active = 1 AND (max_uses = 0 OR uses < max_uses)",
            (coupon_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- Settings (runtime-editable platform config) ----------

async def get_setting(key: str, default: str | None = None) -> str | None:
    async with raw_db() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else default


async def set_setting(key: str, value: str | None, updated_by: int | None = None):
    async with raw_db() as db:
        await db.execute(
            """INSERT INTO settings (key, value, updated_by, updated_at)
               VALUES (?, ?, ?, strftime('%s','now'))
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_by = excluded.updated_by,
                 updated_at = excluded.updated_at""",
            (key, value, updated_by),
        )
        await db.commit()


async def ban_user(user_id: int, banned: bool):
    async with raw_db() as db:
        await db.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id),
        )
        await db.commit()
        invalidate_user(user_id)


# ---------- Product field editing (whitelisted) ----------

PRODUCT_EDITABLE = ("title", "description", "price_credits", "photo_path",
                    "file_path", "file_type", "tags", "link")


async def update_product_field(product_id: int, column: str, value) -> bool:
    if column not in PRODUCT_EDITABLE:
        return False
    async with raw_db() as db:
        cursor = await db.execute(
            f"UPDATE products SET {column} = ? WHERE id = ?", (value, product_id)
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- Custom bot (user's own OpenAI-compatible endpoint) ----------

async def upsert_custom_bot(user_id: int, api_key: str, base_url: str, model: str, active: int = 1):
    async with raw_db() as db:
        await db.execute(
            """INSERT INTO custom_bots (user_id, api_key, base_url, model, active)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 api_key = excluded.api_key,
                 base_url = excluded.base_url,
                 model = excluded.model,
                 active = excluded.active""",
            (user_id, api_key, base_url, model, active),
        )
        await db.commit()


async def get_custom_bot(user_id: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM custom_bots WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_custom_bot_active(user_id: int, active: bool) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE custom_bots SET active = ? WHERE user_id = ?",
            (1 if active else 0, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- Conversation memory (Hermes-style persistent sessions) ----------

MEMORY_TURNS = 8       # recent turns injected into the prompt
MEMORY_MAX_ROWS = 60   # hard cap per user


async def mem_add(user_id: int, role: str, content: str):
    if role not in ("user", "assistant") or not content:
        return
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content[:6000]),
        )
        msg_id = cursor.lastrowid
        # FTS index (best-effort; search feature degrades gracefully)
        try:
            await db.execute(
                "INSERT INTO chat_fts (content, user_id, msg_id, session_id) "
                "VALUES (?, ?, ?, NULL)",
                (content[:6000], user_id, msg_id),
            )
        except Exception:
            pass
        await db.execute(
            """DELETE FROM chat_messages WHERE user_id = ? AND id NOT IN (
                 SELECT id FROM chat_messages WHERE user_id = ?
                 ORDER BY id DESC LIMIT ?)""",
            (user_id, user_id, MEMORY_MAX_ROWS),
        )
        # keep the FTS index in lockstep (no bloat, no stale hits)
        try:
            await db.execute(
                "DELETE FROM chat_fts WHERE user_id = ? AND msg_id NOT IN ("
                "SELECT id FROM chat_messages WHERE user_id = ?)",
                (user_id, user_id),
            )
        except Exception:
            pass
        await db.commit()


async def mem_recent(user_id: int, turns: int = MEMORY_TURNS) -> list[dict]:
    """Last N turns as [{'id','role','content'}] in chronological order."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, role, content FROM chat_messages WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, turns * 2),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
    rows.reverse()
    return rows


async def mem_count(user_id: int) -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE user_id = ?", (user_id,)
        )
        return (await cursor.fetchone())[0]


async def mem_clear(user_id: int) -> int:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        try:
            await db.execute("DELETE FROM chat_fts WHERE user_id = ?", (user_id,))
        except Exception:
            pass
        await db.commit()
        return cursor.rowcount


# ---------- FTS history search ----------

async def history_search(user_id: int, query: str, limit: int = 8) -> list[dict]:
    q = escape_like(query) if query else ""
    if not q:
        return []
    match_expr = " OR ".join(f'"{tok}"' for tok in q.split()[:6])
    async with get_db() as db:
        try:
            cursor = await db.execute(
                """SELECT m.id, m.role, m.content, m.created_at
                   FROM chat_fts f
                   JOIN chat_messages m ON m.id = f.msg_id AND m.user_id = f.user_id
                   WHERE chat_fts MATCH ? AND f.user_id = ?
                   ORDER BY m.id DESC LIMIT ?""",
                (match_expr, user_id, limit),
            )
            return [dict(r) for r in await cursor.fetchall()]
        except Exception:
            return []


# ---------- general cron (personal reminders) ----------

async def reminder_add(owner_id: int, hour: int, minute: int, text: str) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO cron_tasks (owner_id, hour, minute, text) VALUES (?, ?, ?, ?)",
            (owner_id, hour % 24, minute % 60, text[:500]),
        )
        return cur.lastrowid


async def reminder_list(owner_id: int) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM cron_tasks WHERE owner_id = ? AND active = 1 "
            "ORDER BY hour, minute", (owner_id,))
        return [dict(r) for r in await cursor.fetchall()]


async def reminder_delete(owner_id: int, task_id: int) -> bool:
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE cron_tasks SET active = 0 WHERE id = ? AND owner_id = ?",
            (task_id, owner_id),
        )
        return cursor.rowcount > 0


async def due_reminders(now_h: int, now_m: int, today: str, limit: int = 50) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM cron_tasks WHERE active = 1 AND last_date != ? "
            "AND hour = ? AND minute = ? LIMIT ?",
            (today, now_h, now_m, limit),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            await db.execute(
                "UPDATE cron_tasks SET last_date = ? WHERE id = ?",
                (today, r["id"]),
            )
        return rows


# ---------- Knowledge base ("second brain" / Obsidian analog) ----------

async def kb_save(user_id: int, topic: str, content: str, source: str = "librarian") -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "INSERT INTO kb_notes (user_id, topic, content, source) VALUES (?, ?, ?, ?)",
            (user_id, topic[:200], content[:6000], source),
        )
        await db.commit()
        return cursor.lastrowid


async def kb_search(user_id: int, query: str, limit: int = 2) -> list[dict]:
    """Lightweight keyword recall (any token match), newest first."""
    tokens = [t for t in (query or "").split() if len(t) >= 4][:5]
    if not tokens:
        return []
    like = " OR ".join(
        ["topic LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\'"] * len(tokens))
    params = []
    for t in tokens:
        e = escape_like(t)
        params += [f"%{e}%", f"%{e}%"]
    async with raw_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM kb_notes WHERE user_id = ? AND ({like}) "
            "ORDER BY id DESC LIMIT ?",
            [user_id] + params + [limit],
        )
        return [dict(r) for r in await cursor.fetchall()]


async def kb_count(user_id: int) -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM kb_notes WHERE user_id = ?", (user_id,)
        )
        return (await cursor.fetchone())[0]

DEFAULT_HELP = """🚀 DropAgentX — راهنمای کامل

۱) شروع: /start → منوی اصلی
۲) کردیت رایگان: بخش «✅ Earn Credits» تسک‌های فالو/ساب را انجام بده
۳) واریز پول: «💰 Wallet → 📥 واریز USDT» — شبکه انتخاب کن، به آدرس پلتفرم بفرست، TXID را ارسال کن؛ بعد از تأیید ادمین شارژ می‌شود
۴) ساخت محصول: «📦 My Products → ➕ Create» یا با کمک AI Agent
۵) فروش و برداشت: فروش = کردیت؛ برداشت USDT با تأیید ادمین

💰 نرخ تبدیل: ۱۰۰۰ کردیت = ۱ USDT
🎟 سربازها می‌توانند کد تخفیف بسازند؛ موقع خرید دکمه «کد تخفیف دارم»

👥 دعوت دوستان: لینک اختصاصی در «👥 Invite & Earn»
🎁 جعبه شانس فوری + بونوس دوطرفه پس از اولین فعالیت + ۲۰٪ کمیسیون مادام‌العمر

👑 مسیر رشد: کارآموز → اولین فروش = سرباز → ۱۰ دعوت فعال = کاپو → انتصاب = آندرباس"""

DEFAULT_RULES = """📜 قوانین پلتفرم

۱. احترام متقابل الزامی است؛ توهین و آزار = مسدودی دائمی.
۲. محصول باید متعلق به خودت باشد؛ کپی‌برداری و نقض کپی‌رایت = حذف محصول + برگشت وجه خریداران.
۳. ممنوعیت مطلق: محتوای بزرگسالان، خشونت، سلاح، مواد مخدر، هک/کرک، کلاهبرداری مالی.
۴. تبلیغ در تسک‌ها فقط کانال/پیج واقعی؛ فیک‌بازی در تسک = صفر شدن کردیت‌ها.
۵. توصیه سرمایه‌گذاری نیست! محصولات آموزشی صرفاً آموزشی هستند؛ مسئولیت معامله با خودت است.
۶. تخلف در واریز (TXID جعلی) = بن دائمی و گزارش.
۷. برداشت فقط به کیف پول خودت؛ مسئولیت آدرس اشتباه با کاربر است.
۸. کمیسیون پلتفرم روی هر فروش کسر می‌شود و قابل بازگشت نیست.
۹. اختلافات توسط ادمین (Godfather) رسیدگی و تصمیم نهایی قطعی است.
۱۰. قوانین ممکن است به‌روزرسانی شوند؛ ادامه استفاده = پذیرش."""


async def seed_content():
    async with raw_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO content_pages (key, title, body, updated_by) VALUES (?, ?, ?, ?)",
            ("help", "راهنمای پلتفرم", DEFAULT_HELP, None),
        )
        await db.execute(
            "INSERT OR IGNORE INTO content_pages (key, title, body, updated_by) VALUES (?, ?, ?, ?)",
            ("rules", "قوانین پلتفرم", DEFAULT_RULES, None),
        )
        await db.commit()


async def get_content(key: str) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM content_pages WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_content(key: str, body: str, updated_by: int) -> bool:
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE content_pages SET body = ?, updated_by = ?, updated_at = strftime('%s','now') "
            "WHERE key = ?",
            (body, updated_by, key),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------- Seed products ----------

SEED_PRODUCTS = [
    ("آموزش حرفه‌ای GitHub", "education", 1500,
     "گیت و گیت‌هاب از صفر تا پروفایل حرفه‌ای: کامیت، برنچ، PR، اکشنز و README جذاب. مناسب برنامه‌نویس‌ها و دانشجوها.",
     "github, git, ورژن-کنترل, برنامه‌نویسی"),
    ("آموزش Hermes Agent", "tools", 2500,
     "نصب و تسلط روی ایجنت هوش مصنوعی هرمس: CLI، گیت‌وی تلگرام، مهارت‌ها، پلاگین‌ها و اتوماسیون شخصی.",
     "hermes, ai, agent, اتوماسیون"),
    ("آموزش n8n", "tools", 2000,
     "اتوماسیون گردش‌کار با n8n: نودها، وب‌هوک، اتصال به API ها و ساخت سیستم‌های خودکار بدون کد.",
     "n8n, automation, no-code, workflow"),
    ("آموزش Memecoin Trading", "education", 3500,
     "ترید مم‌کوین: اسکنرها، لیکویدیتی، چارت‌خوانی، مدیریت ریسک و روانشناسی بازار پرنوسان. ⚠️ توصیه سرمایه‌گذاری نیست.",
     "crypto, memecoin, trading, دیفای"),
    ("آموزش ساخت اکسپرت MT5", "coding", 4500,
     "ساخت اکسپرت ادوایزر متاتریدر ۵ با MQL5: استراتژی، بک‌تست، مدیریت پوزیشن و بهینه‌سازی پارامترها.",
     "mt5, mql5, forex, expert-advisor"),
    ("آموزش ساخت ربات تلگرام", "coding", 2200,
     "از توکن بات فرادر تا انتشار: پایتون، اینلاین کیبورد، دیتابیس و دیپلوی روی سرور. پروژه‌محور و عملی.",
     "telegram, bot, python, ربات"),
    ("آموزش ساخت هرمس بات", "coding", 3000,
     "ساخت بات مارکت‌پلیس مبتنی بر هرمس: معماری، دیتابیس، پرداخت USDT، ریفرال و استقرار. همون چیزی که الان تو هستی!",
     "hermes, bot, marketplace, startup"),
    ("آموزش CMC", "education", 1200,
     "کوین‌مارکت‌کپ حرفه‌ای: تحلیل مارکت‌کپ، وچ لیستینگ، API و رصد ترندهای رمزارز قبل از بقیه.",
     "cmc, crypto, analysis, بازار"),
    ("آموزش MT5 MCN", "coding", 4000,
     "شبکه‌کپی MCN در متاتریدر ۵: اتصال حساب‌ها، مدیریت سیگنال و ریسک چندحسابی.",
     "mt5, copy-trading, forex, mcx"),
    ("آموزش Arena.ai", "tools", 1600,
     "کار با Arena.ai: مقایسه مدل‌های هوش مصنوعی، پرامپت‌نویسی برنده و استفاده حرفه‌ای از لیدربورد مدل‌ها.",
     "arena, ai, llm, prompt"),
]

SEED_INTROS = {
    "GitHub": "## سرفصل‌ها\n- نصب و کانفیگ Git\n- Commit/Branch/Merge/Rebase\n- Pull Request و Code Review\n- GitHub Actions (CI)\n- README و Profile README حرفه‌ای\n\n## تمرین\nیک ریپو بساز، ۳ برنچ، یک PR بزن و Merge کن.",
    "Hermes": "## سرفصل‌ها\n- نصب hermes-agent\n- حالت CLI و TUI\n- گیت‌وی تلگرام/دیسکورد\n- Skills و Plugins\n- Cron و Kanban\n\n## تمرین\nهرمس را نصب کن و یک Skill سفارشی بنویس.",
    "n8n": "## سرفصل‌ها\n- Docker نصب\n- Trigger ها و Webhook\n- اتصال OpenAI/Telegram/Sheets\n- Error Workflow\n\n## تمرین\nیک ورک‌فلو: تلگرام → GPT → گوگل‌شیت.",
    "Memecoin": "## سرفصل‌ها\n- اسکنرها (DEXScreener...)\n- Rug-check و لیکویدیتی\n- ورود/خروج سریع\n- مدیریت بانکرول ۱٪\n\n⚠️ آموزش صرفاً علمی است.",
    "MT5 Expert": "## سرفصل‌ها\n- MQL5 پایه\n- OrderSend و SL/TP\n- اندیکاتور سفارشی\n- Strategy Tester و Optimization\n\n## تمرین\nاکسرت MA-Cross با تریلینگ استاپ بساز.",
    "تلگرام": "## سرفصل‌ها\n- BotFather و توکن\n- aiogram 3\n- FSM و دکمه‌های اینلاین\n- SQLite\n- دیپلوی VPS\n\n## تمرین\nبات یادداشت‌برداری بساز.",
    "هرمس بات": "## سرفصل‌ها\n- معماری marketplace-bot\n- hermes_engine (cli/http/api)\n- ولت USDT و ادمین\n- ریفرال و رتبه‌ها\n\nاین خودِ همین پلتفرم است!",
    "CMC": "## سرفصل‌ها\n- MarketCap واقعی vs FDV\n- Watchlist و Alerts\n- CMC API\n- DYOR چک‌لیست\n\n## تمرین\n۵ پروژه نوظهور را آنالیز کن.",
    "MT5 MCN": "## سرفصل‌ها\n- مفهوم کپی‌تریدینگ\n- Master/Slave\n- Risk scaling\n- مانیتورینگ\n\n⚠️ ریسک بالا؛ ابتدا دمو.",
    "Arena.ai": "## سرفصل‌ها\n- Battle mode\n- انتخاب مدل برای هر وظیفه\n- Prompt patterns برنده\n\n## تمرین\n۳ مدل را روی یک تسک مقایسه کن.",
}


def _seed_file_for(title: str) -> str | None:
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    for key, intro in SEED_INTROS.items():
        if key.lower() in title.lower():
            safe = "".join(ch for ch in title if ch.isalnum() or ch in " -_")[:40].strip() or "product"
            path = os.path.join(config.UPLOAD_DIR, f"seed_{safe.replace(' ', '_')}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{intro}\n")
            return path
    return None


async def seed_products() -> int:
    from config import config as cfg
    owner = cfg.ADMIN_IDS[0] if cfg.ADMIN_IDS else None
    # Seed content must never violate products.creator_id NOT NULL. A clean
    # install without ADMIN_IDS should still initialize an empty database.
    if owner is None:
        logger.warning("Skipping demo product seed: ADMIN_IDS is empty")
        return 0
    async with raw_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, role, credits) "
            "VALUES (?, ?, ?, 'underboss', 0)",
            (owner, "platform_admin", "Platform Admin"),
        )
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        if (await cursor.fetchone())[0] > 0:
            await db.commit()
            return 0
        count = 0
        for title, category, price, description, tags in SEED_PRODUCTS:
            file_path = _seed_file_for(title)
            await db.execute(
                """INSERT INTO products
                   (creator_id, title, description, price_credits, file_path, file_type,
                    category, tags, is_featured, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    owner, title, description, price, file_path,
                    "text/markdown" if file_path else None,
                    category, tags, 1,
                ),
            )
            count += 1
        await db.commit()
        return count


# ---------- Deposits ----------

async def create_deposit(user_id: int, network: str, txid: str, amount_usdt: float) -> int | None:
    """Returns new deposit id, or None if (network, txid) already exists."""
    async with raw_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO deposits (user_id, network, txid, amount_usdt) VALUES (?, ?, ?, ?)",
                (user_id, network, txid, amount_usdt),
            )
            await db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None


async def get_deposit(deposit_id: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_deposit_status(deposit_id: int, status: str, reviewed_by: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE deposits SET status = ?, reviewed_by = ?, reviewed_at = strftime('%s','now') "
            "WHERE id = ? AND status = 'pending'",
            (status, reviewed_by, deposit_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
        cursor = await db.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_pending_deposits(limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT * FROM deposits WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def list_user_deposits(user_id: int, limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT * FROM deposits WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ---------- Withdrawals ----------

async def create_withdrawal(user_id: int, network: str, address: str,
                            amount_usdt: float, fee_usdt: float) -> int:
    async with raw_db() as db:
        cursor = await db.execute(
            "INSERT INTO withdrawals (user_id, network, address, amount_usdt, fee_usdt) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, network, address, amount_usdt, fee_usdt),
        )
        await db.commit()
        return cursor.lastrowid


async def get_withdrawal(wd_id: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute("SELECT * FROM withdrawals WHERE id = ?", (wd_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_withdrawal_status(wd_id: int, status: str, reviewed_by: int) -> Optional[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "UPDATE withdrawals SET status = ?, reviewed_by = ?, reviewed_at = strftime('%s','now') "
            "WHERE id = ? AND status = 'pending'",
            (status, reviewed_by, wd_id),
        )
        if cursor.rowcount == 0:
            return None
        if status == "paid":
            await db.execute(
                "UPDATE users SET has_withdrawn=1 WHERE user_id=(SELECT user_id FROM withdrawals WHERE id=?)",
                (wd_id,),
            )
        cursor = await db.execute("SELECT * FROM withdrawals WHERE id = ?", (wd_id,))
        row = await cursor.fetchone()
        if row:
            invalidate_user(row["user_id"])
        return dict(row) if row else None


async def list_pending_withdrawals(limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def list_user_withdrawals(user_id: int, limit: int = 10) -> list[dict]:
    async with raw_db() as db:
        cursor = await db.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ---------- Automatic treasury worker primitives ----------

async def record_deposit_verification_attempt(deposit_id: int, reason: str = "") -> None:
    """Keep provider failures observable while leaving the deposit pending."""
    async with raw_db() as db:
        await db.execute(
            "UPDATE deposits SET verification_attempts=COALESCE(verification_attempts,0)+1, "
            "verification_reason=? WHERE id=? AND status='pending'",
            (str(reason)[:300], deposit_id),
        )


async def approve_verified_deposit(deposit_id: int, reviewed_by: int = 0) -> Optional[dict]:
    """Atomically approve a verified deposit and mint its credits once."""
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT * FROM deposits WHERE id=? AND status='pending'",
            (deposit_id,),
        )
        dep = await cur.fetchone()
        if not dep:
            return None
        credits = usdt_to_credits(dep["amount_usdt"])
        cur = await db.execute(
            "UPDATE deposits SET status='approved', reviewed_by=?, "
            "reviewed_at=strftime('%s','now'), verified_at=strftime('%s','now'), "
            "verification_reason='verified by chain provider' "
            "WHERE id=? AND status='pending'",
            (reviewed_by, deposit_id),
        )
        if cur.rowcount == 0:
            return None
        await db.execute(
            "UPDATE users SET credits=credits+?, total_earned=total_earned+? WHERE user_id=?",
            (credits, credits, dep["user_id"]),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) "
            "VALUES (?, ?, 'deposit', ?, ?)",
            (dep["user_id"], credits, deposit_id,
             f"Deposit #{deposit_id} verified on-chain"),
        )
        cur = await db.execute("SELECT * FROM deposits WHERE id=?", (deposit_id,))
        row = await cur.fetchone()
        invalidate_user(dep["user_id"])
        return dict(row) if row else None


async def mark_withdrawal_paid(wd_id: int, txid: str, reviewed_by: int = 0) -> Optional[dict]:
    """Atomically mark a provider-confirmed payout as paid."""
    async with raw_db() as db:
        cur = await db.execute("SELECT user_id FROM withdrawals WHERE id=?", (wd_id,))
        owner = await cur.fetchone()
        if not owner:
            return None
        cur = await db.execute(
            "UPDATE withdrawals SET status='paid', payout_txid=?, reviewed_by=?, "
            "reviewed_at=strftime('%s','now'), payout_error='' "
            "WHERE id=? AND status='pending'",
            (str(txid)[:200], reviewed_by, wd_id),
        )
        if cur.rowcount == 0:
            return None
        await db.execute(
            "UPDATE users SET has_withdrawn=1 WHERE user_id=(SELECT user_id FROM withdrawals WHERE id=?)",
            (wd_id,),
        )
        cur = await db.execute("SELECT * FROM withdrawals WHERE id=?", (wd_id,))
        row = await cur.fetchone()
        invalidate_user(owner["user_id"])
        return dict(row) if row else None


async def record_payout_error(wd_id: int, reason: str) -> None:
    async with raw_db() as db:
        await db.execute(
            "UPDATE withdrawals SET payout_error=? WHERE id=? AND status='pending'",
            (str(reason)[:300], wd_id),
        )


async def approve_deposit_manual(deposit_id: int, reviewed_by: int = 0) -> Optional[dict]:
    """Manual admin approval with status change and credit mint in one txn."""
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT * FROM deposits WHERE id=? AND status='pending'", (deposit_id,))
        dep = await cur.fetchone()
        if not dep:
            return None
        credits = usdt_to_credits(dep["amount_usdt"])
        cur = await db.execute(
            "UPDATE deposits SET status='approved', reviewed_by=?, reviewed_at=strftime('%s','now'), "
            "verification_reason='manually approved by admin' WHERE id=? AND status='pending'",
            (reviewed_by, deposit_id),
        )
        if cur.rowcount == 0:
            return None
        await db.execute(
            "UPDATE users SET credits=credits+?, total_earned=total_earned+? WHERE user_id=?",
            (credits, credits, dep["user_id"]),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) "
            "VALUES (?, ?, 'deposit', ?, ?)",
            (dep["user_id"], credits, deposit_id,
             f"Deposit #{deposit_id} manually approved"),
        )
        cur = await db.execute("SELECT * FROM deposits WHERE id=?", (deposit_id,))
        row = await cur.fetchone()
        invalidate_user(dep["user_id"])
        return dict(row) if row else None


async def reject_withdrawal_and_refund(wd_id: int, reviewed_by: int = 0) -> Optional[dict]:
    """Reject a held withdrawal and release the hold atomically."""
    async with raw_db() as db:
        cur = await db.execute(
            "SELECT * FROM withdrawals WHERE id=? AND status='pending'", (wd_id,))
        wd = await cur.fetchone()
        if not wd:
            return None
        refund = usdt_to_credits(wd["amount_usdt"])
        cur = await db.execute(
            "UPDATE withdrawals SET status='rejected', reviewed_by=?, reviewed_at=strftime('%s','now'), "
            "payout_error='rejected by admin' WHERE id=? AND status='pending'",
            (reviewed_by, wd_id),
        )
        if cur.rowcount == 0:
            return None
        await db.execute(
            "UPDATE users SET credits=credits+? WHERE user_id=?",
            (refund, wd["user_id"]),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) "
            "VALUES (?, ?, 'withdraw_refund', ?, ?)",
            (wd["user_id"], refund, wd_id,
             f"Withdraw #{wd_id} rejected; hold released"),
        )
        cur = await db.execute("SELECT * FROM withdrawals WHERE id=?", (wd_id,))
        row = await cur.fetchone()
        invalidate_user(wd["user_id"])
        return dict(row) if row else None
