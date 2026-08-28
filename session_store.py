"""Session persistence: named sessions, FTS5 search, export, recovery.

Inspired by Hermes Agent's session system (hermes_state.py + session_export.py):
  - Sessions are conversation containers (one per topic/context)
  - FTS5 for fast full-text search across all sessions
  - Export to JSON/Markdown for sharing or archival
  - Session recovery: resume any previous session by title or ID

Design:
  - Sessions table links to chat_messages via session_id
  - Each session has a title (auto-generated from first user message)
  - Search operates across ALL user sessions via FTS5
  - Export generates complete conversation as downloadable file
"""

import aiosqlite
import json
import os
import time
from datetime import datetime

from database import get_db, raw_db, MEMORY_MAX_ROWS


# =========================================================
# Session CRUD
# =========================================================

async def session_create(user_id: int, title: str = "") -> int:
    """Create a new conversation session. Returns session_id."""
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO sessions (user_id, title) VALUES (?, ?)",
            (user_id, title[:200] if title else f"Session {datetime.now():%Y-%m-%d %H:%M}"),
        )
        return cursor.lastrowid


async def session_update_title(session_id: int, title: str):
    """Update session title (e.g., after first meaningful exchange)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET title = ?, last_active = strftime('%s','now') WHERE id = ?",
            (title[:200], session_id),
        )
        await db.commit()


async def session_touch(session_id: int):
    """Update last_active timestamp."""
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET last_active = strftime('%s','now') WHERE id = ?",
            (session_id,),
        )
        await db.commit()


async def session_list(user_id: int, limit: int = 20) -> list[dict]:
    """List user's sessions, newest first."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT s.*, 
                      (SELECT COUNT(*) FROM chat_messages cm WHERE cm.session_id = s.id) AS msg_count
               FROM sessions s WHERE s.user_id = ?
               ORDER BY s.last_active DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def session_delete(session_id: int, user_id: int) -> bool:
    """Delete a session and its messages."""
    async with get_db() as db:
        # Delete messages first (FK)
        await db.execute(
            "DELETE FROM chat_messages WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        cursor = await db.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def session_active(user_id: int) -> dict | None:
    """Get the most recently active session for a user."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY last_active DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def session_get(session_id: int, user_id: int) -> dict | None:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


# =========================================================
# Message association with sessions
# =========================================================

async def session_add_msg(session_id: int, role: str, content: str) -> int:
    """Add a message to a specific session."""
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO chat_messages (session_id, user_id, role, content) "
            "VALUES (?, (SELECT user_id FROM sessions WHERE id=?), ?, ?)",
            (session_id, session_id, role, content[:6000]),
        )
        msg_id = cursor.lastrowid
        # update FTS
        try:
            uid_cursor = await db.execute(
                "SELECT user_id FROM sessions WHERE id=?", (session_id,)
            )
            uid_row = await uid_cursor.fetchone()
            uid = uid_row[0] if uid_row else 0
            await db.execute(
                "INSERT INTO chat_fts (content, user_id, msg_id, session_id) "
                "VALUES (?, ?, ?, ?)",
                (content[:6000], uid, msg_id, session_id),
            )
        except Exception:
            pass
        # update session timestamp
        await db.execute(
            "UPDATE sessions SET last_active = strftime('%s','now') WHERE id = ?",
            (session_id,),
        )
        await db.commit()
        return msg_id


async def session_messages(session_id: int, limit: int = 50) -> list[dict]:
    """Get messages for a session, chronological."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, role, content, created_at FROM chat_messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# =========================================================
# Enhanced FTS5 search
# =========================================================

async def session_search(user_id: int, query: str, limit: int = 10) -> list[dict]:
    """Full-text search across all user sessions with context snippets."""
    if not query or len(query.strip()) < 2:
        return []
    
    terms = [t for t in query.split() if len(t) >= 2][:8]
    if not terms:
        return []

    # FTS5 MATCH expression
    match_expr = " OR ".join(f'"{t}"' for t in terms)

    async with get_db() as db:
        try:
            cursor = await db.execute(
                """SELECT m.id, m.session_id, m.role, m.content, m.created_at,
                          s.title AS session_title,
                          snippet(chat_fts, 0, '>>>', '<<<', '…', 32) AS snippet
                   FROM chat_fts f
                   JOIN chat_messages m ON m.id = f.msg_id AND m.user_id = f.user_id
                   LEFT JOIN sessions s ON s.id = m.session_id
                   WHERE chat_fts MATCH ? AND f.user_id = ?
                   ORDER BY m.id DESC
                   LIMIT ?""",
                (match_expr, user_id, limit),
            )
            results = []
            for r in await cursor.fetchall():
                d = dict(r)
                d["snippet"] = d.get("snippet", d["content"][:200])
                results.append(d)
            return results
        except Exception:
            # Fallback to LIKE search if FTS5 is broken
            like_q = f"%{terms[0]}%"
            cursor = await db.execute(
                """SELECT m.id, m.session_id, m.role, m.content, m.created_at,
                          s.title AS session_title
                   FROM chat_messages m
                   LEFT JOIN sessions s ON s.id = m.session_id
                   WHERE m.user_id = ? AND m.content LIKE ?
                   ORDER BY m.id DESC LIMIT ?""",
                (user_id, like_q, limit),
            )
            return [dict(r) for r in await cursor.fetchall()]


# =========================================================
# Export: JSON
# =========================================================

async def session_export_json(session_id: int, user_id: int) -> dict | None:
    """Export a session as structured JSON."""
    session = await session_get(session_id, user_id)
    if not session:
        return None
    messages = await session_messages(session_id, limit=500)
    return {
        "export_format": "dropagentx_session_v1",
        "session": {
            "id": session["id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "last_active": session["last_active"],
        },
        "messages": [{"role": m["role"], "content": m["content"],
                       "timestamp": m["created_at"]} for m in messages],
        "stats": {
            "total_messages": len(messages),
            "user_messages": sum(1 for m in messages if m["role"] == "user"),
            "assistant_messages": sum(1 for m in messages if m["role"] == "assistant"),
        },
    }


# =========================================================
# Export: Markdown
# =========================================================

async def session_export_md(session_id: int, user_id: int) -> str | None:
    """Export a session as formatted Markdown."""
    data = await session_export_json(session_id, user_id)
    if not data:
        return None

    s = data["session"]
    lines = [
        f"# {s['title']}",
        f"",
        f"**Session ID:** {s['id']}",
        f"**Created:** {datetime.fromtimestamp(s['created_at']):%Y-%m-%d %H:%M}" if s['created_at'] else "",
        f"**Messages:** {data['stats']['total_messages']}",
        f"",
        "---",
        "",
    ]

    for msg in data["messages"]:
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        role_name = "کاربر" if msg["role"] == "user" else "AI"
        lines.append(f"### {role_icon} {role_name}")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")

    return "\n".join(lines)


# =========================================================
# Export: file path for Telegram delivery
# =========================================================

async def session_export_file(session_id: int, user_id: int,
                               fmt: str = "md") -> str | None:
    """Export session to a temporary file; returns the file path."""
    if fmt == "json":
        data = await session_export_json(session_id, user_id)
        if not data:
            return None
        content = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        content = await session_export_md(session_id, user_id)
        if not content:
            return None

    os.makedirs("data/exports", exist_ok=True)
    path = f"data/exports/session_{user_id}_{session_id}_{int(time.time())}.{fmt}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# =========================================================
# Session recovery
# =========================================================

async def session_resume_suggestion(user_id: int) -> str:
    """Suggest which session to resume based on recent activity."""
    sessions = await session_list(user_id, limit=5)
    if not sessions:
        return "💡 هیچ جلسه قبلی نداری. با یک پیام جدید شروع کن."

    lines = ["📋 **آخرین جلسات شما:**\n"]
    for s in sessions[:5]:
        ts = datetime.fromtimestamp(s["last_active"] or 0).strftime("%m/%d %H:%M")
        lines.append(f"• **{s['title'][:50]}** ({s.get('msg_count', 0)} پیام — {ts})")
        lines.append(f"  🔄 `/resume {s['id']}` برای ادامه")
    return "\n".join(lines)
