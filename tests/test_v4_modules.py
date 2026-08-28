"""v4.0.0 module tests — tickets, quests/XP, reports, analytics."""
import pytest
import pytest_asyncio

import database
from config import config as cfg


@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    await database.close_pool()
    old_db, old_uploads, old_admins = database.DB_PATH, cfg.UPLOAD_DIR, cfg.ADMIN_IDS
    database.DB_PATH = str(tmp_path / "v4.db")
    cfg.DB_PATH = database.DB_PATH
    cfg.UPLOAD_DIR = str(tmp_path / "uploads")
    cfg.ADMIN_IDS = [1]
    try:
        await database.init_db()
        yield tmp_path
    finally:
        await database.close_pool()
        database.DB_PATH = old_db
        cfg.DB_PATH = old_db
        cfg.UPLOAD_DIR = old_uploads
        cfg.ADMIN_IDS = old_admins


@pytest.mark.asyncio
async def test_ticket_lifecycle(isolated_db):
    tid = await database.create_ticket(1, "payment", "واریز ثبت نشد", "۵ USDT واریز کردم")
    t = await database.get_ticket(tid)
    assert t and t[3] == "واریز ثبت نشد" and t[4] == "open"
    assert await database.add_ticket_msg(tid, 999, "admin", "در حال بررسی است")
    await database.set_ticket_status(tid, "answered")
    t = await database.get_ticket(tid)
    assert t[4] == "answered"
    thread = await database.ticket_thread(tid)
    assert len(thread) == 2 and thread[1][0] == "admin"
    rows = await database.list_user_tickets(1)
    assert rows and rows[0][2] == "واریز ثبت نشد"
    open_t = await database.list_open_tickets()
    assert open_t and open_t[0][0] == tid
    await database.set_ticket_status(tid, "closed")
    assert not await database.add_ticket_msg(tid, 1, "user", "سلام")


@pytest.mark.asyncio
async def test_quests_progress_and_claim(isolated_db):
    await database.create_user(user_id=7, username="q", first_name="Q")
    from database import raw_db
    async with raw_db() as db:
        for i in (1, 2, 3):
            await db.execute(f"INSERT INTO tasks (id, title, task_type, target_url, credits_reward, creator_id) VALUES ({i},'t{i}','follow','https://x',10,7)")
            await db.execute("INSERT INTO task_completions (task_id, user_id, status) VALUES (?, 7, 'completed')", (i,))
        await db.commit()
    v = await database.quests_view(7)
    q1 = next(q for q in v if q["id"] == 1)
    assert q1["progress"] == 3 and q1["done"] and not q1["claimed"]
    before = (await database.get_user(7))["credits"]
    ok, reward = await database.claim_quest(1, 7)
    assert ok and reward == 30
    after = (await database.get_user(7))["credits"]
    assert after == before + 30
    ok2, why = await database.claim_quest(1, 7)
    assert not ok2 and "قبلاً" in why
    xp = await database.xp_snapshot(7)
    assert xp["xp"] >= 30 and xp["level"] >= 1


@pytest.mark.asyncio
async def test_quest_not_done_guard(isolated_db):
    await database.create_user(user_id=8, username="q2", first_name="Q2")
    ok, why = await database.claim_quest(2, 8)
    assert not ok and "کامل نشده" in why


@pytest.mark.asyncio
async def test_reports(isolated_db):
    rid = await database.create_report(5, "@scammer", "کالا نفروخت")
    rows = await database.list_open_reports()
    assert rows and rows[0][0] == rid and rows[0][2] == "@scammer"
    from database import raw_db
    async with raw_db() as db:
        await db.execute("UPDATE reports SET status='closed' WHERE id=?", (rid,))
        await db.commit()
    assert not await database.list_open_reports()


@pytest.mark.asyncio
async def test_analytics(isolated_db):
    await database.create_user(user_id=10, username="s", first_name="Seller")
    await database.create_user(user_id=11, username="b", first_name="Buyer")
    from database import raw_db
    async with raw_db() as db:
        await db.execute("INSERT INTO products (id, creator_id, title, price_credits, views) VALUES (901, 10, 'پک آموزشی', 100, 50)")
        await db.execute("INSERT INTO products (id, creator_id, title, price_credits, views) VALUES (902, 10, 'پک طراحی', 100, 30)")
        await db.execute("INSERT INTO purchases (buyer_id, product_id, price_credits) VALUES (11, 901, 100)")
        await db.execute("INSERT INTO purchases (buyer_id, product_id, price_credits) VALUES (11, 902, 100)")
        await db.execute("INSERT INTO reviews (product_id, buyer_id, stars) VALUES (901, 11, 5)")
        await db.commit()
    a = await database.user_analytics(11)
    assert a["purchases"] == 2 and a["spent"] == 200 and a["percentile"] > 0
    s = await database.seller_analytics(10)
    assert s["units"] == 2 and s["revenue"] == 200 and s["buyers"] == 1
    assert s["avg_stars"] == 5.0 and s["views"] == 80 and s["top"] is not None
