# -*- coding: utf-8 -*-
"""تست‌های 0.5.2 — رگرسیون فیکس‌های QA عمیق:
   ۱) تلهٔ لاگین HTTP (کوکی Secure پیش‌فرض)  ۲) route گمشدهٔ /live  ۳) وب-تنها با DB خالی
   + اطمینان از idempotent بودن سرویس خرید (کامرس)"""
import os, sys, asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('WEB_PASSWORD', 'pw-052')
os.environ.setdefault('WEB_SECRET', 'x' * 32)
os.environ.setdefault('ADMIN_IDS', '8198598635')
os.environ.pop('COOKIE_SECURE', None)
os.environ.pop('APP_ENV', None)

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    import database
    from config import config as cfg
    old_db = database.DB_PATH
    database.DB_PATH = str(tmp_path / 't052.db')
    cfg.DB_PATH = database.DB_PATH
    await database.init_db()
    yield database.DB_PATH

    async def _close():
        if database._DB is not None:
            await database._DB.close()
            database._DB = None
            database._DB_SRC = None
    await _close()
    database.DB_PATH = old_db
    cfg.DB_PATH = old_db


@pytest_asyncio.fixture
async def client():
    from fastapi.testclient import TestClient
    import web_admin
    with TestClient(web_admin.build_app()) as c:
        yield c


def _login(c):
    from fastapi.testclient import TestClient as _T
    r = c.post('/api/login', json={'password': os.environ['WEB_PASSWORD']})
    assert r.status_code == 200
    kv = r.headers['set-cookie'].split(';')[0]
    c.cookies.set(*kv.split('=', 1))
    return r


@pytest.mark.asyncio
async def test_http_login_full_flow(client):
    """فیکس ۱: روی HTTP عادی لاگین → کوکی → API ادمین باید کار کند (قبلاً 401 بی‌پایان)."""
    r = client.post('/api/login', json={'password': 'wrong'})
    assert r.status_code == 401
    r = _login(client)
    assert 'Secure' not in r.headers.get('set-cookie', ''), 'روی HTTP نباید Secure بخورد'
    assert client.get('/api/admin/stats').status_code == 200
    assert client.get('/api/admin/settings').status_code == 200


@pytest.mark.asyncio
async def test_live_route(client):
    """فیکس ۲: /live قبلاً 404 بود (فایل بود، route نداشت)."""
    r = client.get('/live', follow_redirects=False)
    assert r.status_code == 302, 'بدون لاگین → ریدایرکت لاگین'
    _login(client)
    assert client.get('/live').status_code == 200


@pytest.mark.asyncio
async def test_web_standalone_fresh_db(tmp_path):
    """فیکس ۳: وب با فایل DB ناموجود نباید ۵۰۰ بدهد — استارتاپ خودش init می‌کند."""
    import database
    from config import config as cfg
    from fastapi.testclient import TestClient
    import web_admin
    old_db = database.DB_PATH
    database.DB_PATH = str(tmp_path / 'fresh' / 'brand-new.db')   # عمداً ناموجود
    cfg.DB_PATH = database.DB_PATH
    try:
        with TestClient(web_admin.build_app()) as c:
            for p in ('/api/pub/info', '/api/pub/catalog', '/api/pub/leaderboard'):
                assert c.get(p).status_code == 200, p
    finally:
        async def _close():
            if database._DB is not None:
                await database._DB.close()
                database._DB = None
                database._DB_SRC = None
        await _close()
        database.DB_PATH = old_db
        cfg.DB_PATH = old_db


@pytest.mark.asyncio
async def test_purchase_service_idempotent(isolated_db):
    """کامرس: خرید تکراری باید خطای کنترل‌شده بدهد و دقیقاً یک‌بار پول کم شود."""
    import database as db
    from commerce import purchase_with_credits, CommerceError
    from database import raw_db

    await db.create_user(111, 'seller', 'S')
    await db.create_user(222, 'buyer', 'B')
    async with raw_db() as d:
        await d.execute(
            "INSERT INTO products(creator_id,title,description,price_credits,category,status,is_active) "
            "VALUES(111,'پک تست','د',100,'ai','approved',1)")
        await d.commit()
        async with db.get_db() as _:
            pass
    prod = await db.search_products('پک تست')
    assert prod, 'محصول ساخته نشد'
    pid = prod[0]['id']

    await db.update_credits(222, 1000, 'deposit', 'شارژ')
    before = (await db.get_user(222))['credits']
    assert before >= 1000
    r1 = await purchase_with_credits(222, pid)
    assert r1 is not None
    with pytest.raises(CommerceError):
        await purchase_with_credits(222, pid)
    assert await db.is_product_purchased_by_user(pid, 222) is True
    u = await db.get_user(222)
    assert u['credits'] == before - 100, 'دقیقاً یک‌بار باید ۱۰۰ کم می‌شد'
