"""Tests for V3-4: Session persistence, FTS search, export."""
import asyncio
import json
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")


async def main():
    from database import init_db, create_user
    from session_store import (
        session_create, session_update_title, session_touch, session_list,
        session_delete, session_active, session_get,
        session_add_msg, session_messages, session_search,
        session_export_json, session_export_md, session_export_file,
        session_resume_suggestion,
    )
    await init_db()
    await create_user(1, "alice", "Alice")

    # --- session CRUD ---
    sid1 = await session_create(1, "First Session")
    assert sid1 >= 1
    sid2 = await session_create(1, "Second Session")
    assert sid2 > sid1
    print("[ok] session_create")

    # --- update title ---
    await session_update_title(sid1, "AI Chat about Python")
    s = await session_get(sid1, 1)
    assert s["title"] == "AI Chat about Python"
    print("[ok] session_update_title")

    # --- touch ---
    old = s["last_active"]
    await session_touch(sid1)
    s2 = await session_get(sid1, 1)
    assert s2["last_active"] >= old
    print("[ok] session_touch")

    # --- list ---
    sessions = await session_list(1)
    assert len(sessions) == 2
    assert sessions[0]["id"] == sid2  # newest first
    print("[ok] session_list (newest first)")

    # --- active session ---
    act = await session_active(1)
    assert act["id"] == sid2
    print("[ok] session_active")

    # --- add messages ---
    await session_add_msg(sid1, "user", "hello world")
    await session_add_msg(sid1, "assistant", "hi there! I can help with Python.")
    await session_add_msg(sid1, "user", "tell me about dataclasses")
    await session_add_msg(sid1, "assistant", "dataclasses are a Python module for creating classes that store data.")

    msgs = await session_messages(sid1)
    assert len(msgs) == 4
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    print("[ok] session_messages")

    # --- FTS search ---
    results = await session_search(1, "dataclasses")
    assert len(results) >= 1
    assert "dataclasses" in results[0]["content"].lower()
    print("[ok] session_search (FTS)")

    # --- search by session title ---
    results = await session_search(1, "Python")
    assert len(results) >= 1
    print("[ok] session_search finds via title context")

    # --- export JSON ---
    jdata = await session_export_json(sid1, 1)
    assert jdata["session"]["id"] == sid1
    assert jdata["stats"]["total_messages"] == 4
    assert jdata["stats"]["user_messages"] == 2
    print("[ok] session_export_json")

    # --- export Markdown ---
    md = await session_export_md(sid1, 1)
    assert "AI Chat about Python" in md
    assert "dataclasses" in md
    assert md.count("### 👤") == 2
    assert md.count("### 🤖") == 2
    print("[ok] session_export_md")

    # --- export to file ---
    path = await session_export_file(sid1, 1, "json")
    assert path and os.path.exists(path)
    with open(path) as f:
        data = json.load(f)
    assert data["export_format"] == "dropagentx_session_v1"
    os.remove(path)
    print("[ok] session_export_file (json)")

    path = await session_export_file(sid1, 1, "md")
    assert path and os.path.exists(path)
    assert "# AI Chat about Python" in open(path).read()
    os.remove(path)
    print("[ok] session_export_file (md)")

    # --- resume suggestion ---
    suggestion = await session_resume_suggestion(1)
    assert "/resume" in suggestion
    assert "Second Session" in suggestion
    print("[ok] session_resume_suggestion")

    # --- delete ---
    assert await session_delete(sid1, 1)
    assert not await session_delete(9999, 1)  # doesn't exist
    s = await session_get(sid1, 1)
    assert s is None
    msgs = await session_messages(sid1)
    assert len(msgs) == 0
    print("[ok] session_delete (cascade)")

    print("\nALL V3-4 TESTS PASSED")


asyncio.run(main())
