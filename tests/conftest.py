"""Shared test fixtures for V3 test suite."""
import asyncio
import os
import sys
import tempfile

import pytest
import pytest_asyncio

# Ensure DropAgentXmain modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
from config import config


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """Set test environment variables for the entire session."""
    os.environ["APP_ENV"] = "test"
    os.environ["sandbox_local_allow"] = "1"
    yield


def _reset_db_layer():
    """Clear all module-global database state so tests are order-independent.

    The connection, its source-path marker, the file lock and the per-user cache
    are all reset. This removes the cross-test leakage that made the suite
    order-dependent (stale users surviving between isolated databases).
    """
    database._DB = None
    database._DB_SRC = None
    database._DBLock = asyncio.Lock()
    database._USER_CACHE.clear()
    database._USER_CACHE_PATH = None
    # reset create_user in-process mint counters
    if hasattr(database.create_user, "_month"):
        database.create_user._month = None
    if hasattr(database.create_user, "_used"):
        database.create_user._used = 0


@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    """Isolated DB fixture — each test gets a fresh database."""
    await database.close_pool()
    _reset_db_layer()
    old = {
        "db": database.DB_PATH,
        "cfg_db": config.DB_PATH,
        "uploads": config.UPLOAD_DIR,
        "admins": list(config.ADMIN_IDS),
    }
    database.DB_PATH = str(tmp_path / "test.db")
    config.DB_PATH = database.DB_PATH
    config.UPLOAD_DIR = str(tmp_path / "uploads")
    config.ADMIN_IDS = [1]

    try:
        await database.init_db()
        yield tmp_path
    finally:
        await database.close_pool()
        _reset_db_layer()
        database.DB_PATH = old["db"]
        config.DB_PATH = old["cfg_db"]
        config.UPLOAD_DIR = old["uploads"]
        config.ADMIN_IDS = old["admins"]
