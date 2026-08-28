import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

import database
from blockchain import TRANSFER_TOPIC, Verification, verify_deposit
from config import config
from commerce import CommerceError, purchase_with_credits
from hermes_engine import redact_secrets
from webtools import _ip_is_dangerous


@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    await database.close_pool()
    old_db, old_uploads, old_admins = database.DB_PATH, config.UPLOAD_DIR, config.ADMIN_IDS
    database.DB_PATH = str(tmp_path / "marketplace.db")
    config.DB_PATH = database.DB_PATH
    config.UPLOAD_DIR = str(tmp_path / "uploads")
    config.ADMIN_IDS = [1]
    try:
        await database.init_db()
        yield tmp_path
    finally:
        await database.close_pool()
        database.DB_PATH, config.DB_PATH = old_db, old_db
        config.UPLOAD_DIR, config.ADMIN_IDS = old_uploads, old_admins


@pytest.mark.asyncio
async def test_clean_install_without_admin_does_not_crash(tmp_path):
    await database.close_pool()
    old_db, old_uploads, old_admins = database.DB_PATH, config.UPLOAD_DIR, config.ADMIN_IDS
    database.DB_PATH = str(tmp_path / "empty.db")
    config.DB_PATH = database.DB_PATH
    config.UPLOAD_DIR = str(tmp_path / "uploads")
    config.ADMIN_IDS = []
    try:
        await database.init_db()
        assert await database.get_all_users_count() == 0
        assert await database.get_total_products() == 0
    finally:
        await database.close_pool()
        database.DB_PATH, config.DB_PATH = old_db, old_db
        config.UPLOAD_DIR, config.ADMIN_IDS = old_uploads, old_admins


@pytest.mark.asyncio
async def test_purchase_is_atomic_and_idempotent(isolated_db):
    seller = await database.create_user(10, "seller", "Seller")
    buyer = await database.create_user(20, "buyer", "Buyer")
    await database.update_credits(buyer["user_id"], 200, "test_credit")
    async with database.get_db() as db:
        cur = await db.execute(
            "INSERT INTO products (creator_id,title,description,price_credits,status,is_active) "
            "VALUES (?,?,?,?, 'approved', 1)",
            (seller["user_id"], "Test product", "Test", 100),
        )
        pid = cur.lastrowid
    result = await purchase_with_credits(buyer["user_id"], pid)
    assert result.price == 100
    assert (await database.get_user(buyer["user_id"]))["credits"] == 150
    assert (await database.get_user(seller["user_id"]))["credits"] == 135
    assert (await database.get_product(pid))["sales_count"] == 1
    with pytest.raises(CommerceError):
        await purchase_with_credits(buyer["user_id"], pid)


def test_redaction_and_ssrf_basics():
    masked = redact_secrets("key=sk-12345678901234567890")
    assert "12345678901234567890" not in masked
    assert _ip_is_dangerous("127.0.0.1")
    assert _ip_is_dangerous("169.254.169.254")


def test_transfer_topic_constant():
    assert TRANSFER_TOPIC == "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@pytest.mark.asyncio
async def test_chain_verifier_fails_closed_without_config(monkeypatch):
    monkeypatch.delenv("BSC_RPC_URL", raising=False)
    monkeypatch.delenv("USDT_BSC_TOKEN", raising=False)
    result = await verify_deposit("bsc", "0xabc", 1, "0x0000000000000000000000000000000000000001")
    assert isinstance(result, Verification)
    assert result.verified is False
