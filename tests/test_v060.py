# -*- coding: utf-8 -*-
"""تست‌های 0.6.0 — رگرسیون ۹ فیکس ممیزی + فیلتر ضدکلاهبرداری"""
import os, sys, asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('WEB_PASSWORD', 'pw-060')
os.environ.setdefault('WEB_SECRET', 'z' * 32)
os.environ.setdefault('ADMIN_IDS', '8198598635')

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    import database
    from config import config as cfg
    old_db = database.DB_PATH
    database.DB_PATH = str(tmp_path / 't060.db')
    cfg.DB_PATH = database.DB_PATH
    await database.init_db()
    yield
    async def _close():
        if database._DB is not None:
            await database._DB.close()
            database._DB = None
            database._DB_SRC = None
    await _close()
    database.DB_PATH = old_db
    cfg.DB_PATH = old_db


# ─── آپشن جدید: فیلتر ضدکلاهبرداری ───

@pytest.mark.asyncio
async def test_moderation_blocks_scam(isolated_db):
    from moderation import check_text
    ok, bad = await check_text("پکیج آموزشی طراحی سایت")
    assert ok, bad
    ok, bad = await check_text("دوربین عکاسی حرفه‌ای")
    assert ok, bad
    ok, bad = await check_text("سود تضمینی ۱۰۰٪ در ماه — پول رایگان!")
    assert not ok and bad, 'ادعای مالی غیرواقعی باید رد شود'


@pytest.mark.asyncio
async def test_moderation_no_bypass_with_zwnj(isolated_db):
    from moderation import check_text
    # دورزدن با نیم‌فاصله/حرف عربی/کاراکتر مخفی
    ok, bad = await check_text("س\u200cو\u200cد ت\u200cضمینی می‌گیرید")
    assert not ok, 'نیم‌فاصله نباید فیلتر را دور بزند'
    ok, bad = await check_text("كيجن ویندوز")  # ك و ي عربی
    assert not ok, 'ك عربی نباید فیلتر را دور بزند'


@pytest.mark.asyncio
async def test_moderation_off_and_custom_words(isolated_db):
    from database import get_setting, set_setting, raw_db
    from moderation import check_text
    await set_setting('moderation_enabled', '0', 0)
    ok, _ = await check_text('سود تضمینی')
    assert ok, 'با خاموشی فیلتر باید مجاز باشد'
    await set_setting('moderation_enabled', '1', 0)
    await set_setting('moderation_extra_words', 'فیل_تبلیغاتی', 0)
    ok, bad = await check_text('این یک فیل تبلیغاتی است')
    assert not ok and bad == 'فیل_تبلیغاتی'


# ─── F1: sanitize اسم فایل آپلودی ───

def _load_helper():
    """handlers.products به aiogram نیاز دارد (در سندباکس نصب نیست) — فقط خودِ تابع را اجرا می‌کنیم."""
    import ast, os as _os, time as _time
    src = open(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                             'handlers', 'products.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == '_safe_upload_name':
            ns = {'os': _os, 'time': _time}
            exec(ast.get_source_segment(src, node), ns)
            return ns['_safe_upload_name']
    raise AssertionError('_safe_upload_name پیدا نشد')


def test_safe_upload_name_traversal():
    _safe_upload_name = _load_helper()
    n = _safe_upload_name(42, '../../.env')
    assert '..' not in n and '/' not in n and '\\' not in n
    assert n.startswith('42_')
    n2 = _safe_upload_name(42, 'ویدیو آموزش.r【x】.mp4')
    assert '【' not in n2 and n2.endswith('.mp4')
    n3 = _safe_upload_name(7, 'a.rat.py')
    assert n3.startswith('7_') and len(n3.split('_')[1]) >= 10, 'یکتایی با timestamp'
    n4 = _safe_upload_name(9, '../' * 20 + 'passwd.txt')
    assert n4 == n4.split('/')[-1] and '..' not in n4


# ─── F2: اسکرو اتمیک تسک (hold شرطی) ───

@pytest.mark.asyncio
async def test_task_escrow_atomic_hold(isolated_db):
    import database as db
    await db.create_user(777, 'creator', 'C')
    await db.update_credits(777, 100, 'deposit', 'شارژ')
    ok1 = await db.try_hold_credits(777, 80, 'task_creation', 'تسک ۱')
    assert ok1 is True
    # دومین hold همزمان (دبل‌کلیک) باید رد شود — اینجا دیگر ۸۰ موجود نیست
    ok2 = await db.try_hold_credits(777, 80, 'task_creation', 'تسک ۲')
    assert ok2 is False, 'بودجهٔ کافی برای دو تسک نیست'
    u = await db.get_user(777)
    assert u['credits'] == 150 - 80, 'فقط hold اول باید انجام شده باشد (۵۰ خوش‌آمد + ۱۰۰ شارژ - ۸۰)' 


# ─── F3: کف موجودی صفر ───

@pytest.mark.asyncio
async def test_update_credits_floors_at_zero(isolated_db):
    import database as db
    await db.create_user(555, 'u', 'U')
    await db.update_credits(555, 10, 'deposit', 'شارژ کم')
    await db.update_credits(555, -100, 'admin_grant', 'کسر بزرگ')
    u = await db.get_user(555)
    assert u['credits'] == 0, 'موجودی نباید منفی شود'


# ─── F4: هش پایدار بین ری‌استارت‌ها ───

def test_identity_rl_hash_stable():
    import identity_rl as m
    fn = None
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, '_hash_state'):
            fn = obj._hash_state
            break
    assert fn is not None, 'کلاس RL پیدا نشد'
    v1 = fn('user:1|ip:2|dev:3')
    assert v1 == fn('user:1|ip:2|dev:3')
    # مقدار ثابت blake2b — بین پروسه‌ها یکسان (برخلاف hash())
    import hashlib
    expected = int.from_bytes(hashlib.blake2b('user:1|ip:2|dev:3'.encode(), digest_size=4).digest(), 'big') % 100000
    assert v1 == expected
    assert 0 <= fn('other') < 100000


# ─── F5/F6: rate limiter — XFF و معافیت استاتیک ───

def test_private_ip_detection():
    from web_admin import _is_private_ip
    assert _is_private_ip('192.168.1.5') is True
    assert _is_private_ip('10.0.0.7') is True
    assert _is_private_ip('127.0.0.1') is True
    assert _is_private_ip('8.8.8.8') is False
    assert _is_private_ip('testclient') is False   # جعل XFF از بیرون بی‌اثر


def test_static_paths_excluded_from_limiter():
    import web_admin
    # باید داخل web_admin به‌صورت ثابت موجود باشد — ارجاع از طریق بستن روی build_app
    src = open(web_admin.__file__, encoding='utf-8').read()
    for p in ('"/media/"', '"/sw.js"', '"/fonts/"', '"/vendor/"'):
        assert p in src, f'{p} باید از limiter معاف باشد'


# ─── F7: sandbox محلی قفل ───

def test_sandbox_local_requires_explicit_flag(monkeypatch):
    import sandbox
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.delenv('SANDBOX_ALLOW_LOCAL', raising=False)
    assert sandbox._local_allowed() is False, 'بدون پرچم صریح نباید محلی اجرا شود'
    monkeypatch.setenv('SANDBOX_ALLOW_LOCAL', '1')
    assert sandbox._local_allowed() is True
    monkeypatch.setenv('APP_ENV', 'production')
    assert sandbox._local_allowed() is False, 'در production هرگز'


def test_sandbox_env_scrubs_secrets(monkeypatch):
    import sandbox
    monkeypatch.setenv('BOT_TOKEN', 'SECRET-TOKEN')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-xxx')
    monkeypatch.setenv('WEB_SECRET', 'topsecret')
    env = sandbox._sandbox_env()
    assert 'BOT_TOKEN' not in env and 'OPENAI_API_KEY' not in env and 'WEB_SECRET' not in env
    assert env.get('PATH'), 'PATH باید بماند'


# ─── F8/F9: لاگین بدون سکرت ممنوع + توکن ادمین مقید به رمز ───

def test_admin_token_dies_with_password_change(monkeypatch):
    import web_admin
    monkeypatch.setenv('WEB_SECRET', 'k' * 32)
    monkeypatch.setenv('WEB_PASSWORD', 'old-pass')
    tok = web_admin._make_token()
    assert web_admin._verify_token(tok)
    monkeypatch.setenv('WEB_PASSWORD', 'new-pass')
    assert not web_admin._verify_token(tok), 'توکن مسروقه با تغییر رمز باید بمیرد'


def test_default_secret_login_refused(monkeypatch, tmp_path):
    import database
    from config import config as cfg
    from fastapi.testclient import TestClient
    import web_admin
    old_db = database.DB_PATH
    database.DB_PATH = str(tmp_path / 'ns.db')
    cfg.DB_PATH = database.DB_PATH
    saved = {k: os.environ.get(k) for k in ('WEB_SECRET', 'BOT_TOKEN', 'WEB_PASSWORD')}
    try:
        for k in ('WEB_SECRET', 'BOT_TOKEN'):
            os.environ.pop(k, None)
        os.environ['WEB_PASSWORD'] = 'x'
        with TestClient(web_admin.build_app()) as c:
            r = c.post('/api/login', json={'password': 'x'})
            assert r.status_code == 503, 'با سکرت پیش‌فرض لاگین باید رد شود'
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        database.DB_PATH = old_db
        cfg.DB_PATH = old_db
