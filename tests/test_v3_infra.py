"""V3 Test Suite — Infrastructure (sessions, cron, db)."""
import asyncio
import json
import os
import time

import pytest
import pytest_asyncio


# =========================================================
# Session Persistence (V3-4)
# =========================================================

@pytest.mark.asyncio
async def test_session_crud(isolated_db):
    from session_store import (session_create, session_list, session_get,
                               session_update_title, session_delete)
    sid = await session_create(1, "Test Session")
    assert sid >= 1
    s = await session_get(sid, 1)
    assert s and s["title"] == "Test Session"

    await session_update_title(sid, "Renamed Session")
    s2 = await session_get(sid, 1)
    assert s2["title"] == "Renamed Session"

    sessions = await session_list(1)
    assert len(sessions) == 1

    assert await session_delete(sid, 1)
    assert await session_get(sid, 1) is None


@pytest.mark.asyncio
async def test_session_messages_and_search(isolated_db):
    from session_store import (session_create, session_add_msg,
                               session_messages, session_search)
    sid = await session_create(1, "Python Chat")
    await session_add_msg(sid, "user", "tell me about dataclasses")
    await session_add_msg(sid, "assistant", "dataclasses are great for Python")
    await session_add_msg(sid, "user", "how about decorators?")

    msgs = await session_messages(sid)
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"

    results = await session_search(1, "dataclasses")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_session_export(isolated_db):
    from session_store import (session_create, session_add_msg,
                               session_export_json, session_export_md)
    sid = await session_create(1, "Export Test")
    await session_add_msg(sid, "user", "hello")
    await session_add_msg(sid, "assistant", "hi!")

    j = await session_export_json(sid, 1)
    assert j["export_format"] == "dropagentx_session_v1"
    assert j["stats"]["total_messages"] == 2

    md = await session_export_md(sid, 1)
    assert "Export Test" in md
    assert "hello" in md
    assert "hi!" in md


@pytest.mark.asyncio
async def test_session_delete_cascade(isolated_db):
    from session_store import (session_create, session_add_msg,
                               session_delete, session_messages)
    sid = await session_create(1, "To Delete")
    await session_add_msg(sid, "user", "msg1")
    await session_add_msg(sid, "user", "msg2")
    assert len(await session_messages(sid)) == 2
    await session_delete(sid, 1)
    assert len(await session_messages(sid)) == 0


# =========================================================
# Cron Scheduler (V3-7)
# =========================================================

def test_cron_expression():
    from cron_scheduler import cron_matches
    from datetime import datetime
    dt = datetime(2026, 8, 27, 14, 30)  # Thursday
    assert cron_matches("30 14 * * *", dt)
    assert cron_matches("*/15 * * * *", dt)  # 30 is multiple of 15
    assert not cron_matches("30 15 * * *", dt)


def test_duration_parser():
    from cron_scheduler import parse_duration
    assert parse_duration("5m") == 300
    assert parse_duration("2h") == 7200
    assert parse_duration("1d") == 86400
    assert parse_duration("abc") is None


def test_at_time_parser():
    from cron_scheduler import parse_at_time
    assert parse_at_time("09:00") == (9, 0)
    assert parse_at_time("8:5") == (8, 5)
    assert parse_at_time("abc") is None
    assert parse_at_time("25:00") is None


@pytest.mark.asyncio
async def test_cron_job_lifecycle(isolated_db):
    from cron_scheduler import (job_create, job_list, job_get,
                                job_set_enabled, job_delete, job_run_now)
    jid = await job_create(1, "Test Job", "every", "1h",
                           "notify", "hello world")
    assert jid >= 1

    jobs = await job_list(owner_id=1)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Test Job"

    result = await job_run_now(jid)
    assert result and result["status"] == "ok"

    assert await job_set_enabled(jid, False)
    j = await job_get(jid)
    assert j["enabled"] == 0

    assert await job_delete(jid)
    assert await job_get(jid) is None


# =========================================================
# Database core (V3 foundation)
# =========================================================

@pytest.mark.asyncio
async def test_db_singleton_reentrant(isolated_db):
    """Nested get_db calls must not deadlock."""
    from database import get_db, raw_db

    async def nested():
        async with get_db() as outer:
            cur = await outer.execute("SELECT 1")
            val = await cur.fetchone()
            assert val[0] == 1
            async with raw_db() as inner:
                cur2 = await inner.execute("SELECT 2")
                val2 = await cur2.fetchone()
                assert val2[0] == 2

    await asyncio.wait_for(nested(), timeout=5)


@pytest.mark.asyncio
async def test_db_user_cache(isolated_db):
    from database import get_user, update_credits, invalidate_user, create_user
    u = await create_user(42, "cached", "Cache")
    assert u["credits"] == 50

    # cache should return same object
    u2 = await get_user(42)
    assert u2["credits"] == 50

    # invalidate then refetch
    invalidate_user(42)
    await update_credits(42, 25, "task", "test")
    u3 = await get_user(42)
    assert u3["credits"] == 75


@pytest.mark.asyncio
async def test_db_fts_search(isolated_db):
    from database import mem_add, mem_recent, history_search
    for i in range(5):
        await mem_add(99, "user", f"message about python decorator {i}")
        await mem_add(99, "assistant", f"answer about python decorator {i}")
    results = await history_search(99, "decorator python")
    assert len(results) >= 1
    assert "decorator" in results[0]["content"].lower()


@pytest.mark.asyncio
async def test_db_moderation_flow(isolated_db):
    from database import create_user, set_product_status, search_products
    from database import get_db
    await create_user(50, "seller", "Seller")
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO products (creator_id,title,description,price_credits,category,status)"
            " VALUES (50,'Test Product','desc',100,'coding','pending')")
        pid = cur.lastrowid

    # pending: not visible
    assert all(p["id"] != pid for p in await search_products(limit=50))

    row = await set_product_status(pid, "approved", 1)
    assert row and row["status"] == "approved"
    assert any(p["id"] == pid for p in await search_products(limit=50))


@pytest.mark.asyncio
async def test_db_commerce_atomic(isolated_db):
    from database import create_user, get_db, update_credits, get_user
    from commerce import purchase_with_credits
    await create_user(10, "seller", "Seller")
    await create_user(20, "buyer", "Buyer")
    await update_credits(20, 500, "test")

    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO products (creator_id,title,description,price_credits,status,is_active)"
            " VALUES (10,'Prod','desc',200,'approved',1)")
        pid = cur.lastrowid

    result = await purchase_with_credits(20, pid)
    assert result.price == 200
    assert (await get_user(20))["credits"] == 350  # 50 welcome + 500 - 200

    with pytest.raises(Exception):
        await purchase_with_credits(20, pid)  # idempotent


@pytest.mark.asyncio
async def test_db_referral_flow(isolated_db):
    from database import (create_user, set_referred_by, get_referrer,
                          mark_ref_bonus_paid, count_qualified_refs, count_total_refs)
    await create_user(10, "ref1", "Ref")
    await create_user(20, "ref2", "Ref")
    r = await set_referred_by(20, 10)
    print(f"set_referred_by result: {r}, type: {type(r)}")
    ref = await get_referrer(20)
    print(f"referrer: {ref}")
    assert ref == 10
    assert await count_total_refs(10) == 1
    assert await count_qualified_refs(10) == 0

    assert await mark_ref_bonus_paid(20)
    assert not await mark_ref_bonus_paid(20)  # idempotent
    assert await count_qualified_refs(10) == 1
