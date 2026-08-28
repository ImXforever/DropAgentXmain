"""DropAgentX Mini App API — Telegram initData auth + social commerce.

Mounted into web_admin.build_app() via app_api.register(app).
Auth: client sends Telegram.WebApp.initData → validated (HMAC-SHA256 per
Telegram spec, ≤24h fresh) → signed app cookie + Bearer token issued.
All money paths reuse the atomic primitives from database.py.
"""

import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)


def _get_bot_ref():
    """Return aiogram Bot if running in-process with bot.py."""
    try:
        import web_admin
        return getattr(web_admin, "_BOT", None)
    except Exception:
        return None

CATEGORIES = [
    ("ai", "هوش مصنوعی", "🤖"), ("prompts", "پرامپت", "💬"),
    ("design", "طراحی", "🎨"), ("templates", "قالب", "🧩"),
    ("dev", "برنامه‌نویسی", "💻"), ("education", "آموزش", "📚"),
    ("music", "موزیک", "🎵"), ("gaming", "گیمینگ", "🎮"),
    ("photo", "عکاسی", "📷"), ("video", "ویدیو", "🎬"),
    ("threed", "سه‌بعدی", "🧊"), ("business", "بیزنس", "💼"),
    ("marketing", "مارکتینگ", "📣"), ("content", "محتوا", "✍️"),
    ("tools", "ابزار", "🔧"), ("crypto", "کریپتو", "🪙"),
    ("lang", "زبان", "🗣️"), ("lifestyle", "لایف‌استایل", "🌿"),
    ("automation", "اتوماسیون", "⚙️"), ("other", "سایر", "📦"),
]
CAT_MAP = {"graphics": "design", "coding": "dev", "general": "other"}

FEED_LIMIT = 8


def register(app):
    from fastapi import HTTPException, Request, UploadFile, File
    from pydantic import BaseModel
    from config import config as cfg

    # ---------------------------------------------------------- auth ----

    def _validate_init_data(init_data: str) -> dict | None:
        """Validate Telegram Mini App initData per official spec.
        Uses urllib.parse.parse_qsl for proper URL-decoding."""
        try:
            from urllib.parse import parse_qsl
            pairs = parse_qsl(init_data, keep_blank_values=True)
            vals = dict(pairs)
        except Exception:
            vals = {}
            for kv in (init_data or "").split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    vals[k] = v
        h = vals.pop("hash", "")
        if not h:
            return None
        # data_check_string uses DECODED values per Telegram spec
        dcs = "\n".join(f"{k}={vals[k]}" for k in sorted(vals))
        secret = hmac.new(b"WebAppData", cfg.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, h):
            return None
        try:
            if time.time() - int(vals.get("auth_date", 0)) > 86400:
                return None
            user = json.loads(vals.get("user", "{}"))
        except Exception:
            return None
        if not user.get("id"):
            return None
        return user

    def _issue(uid: int) -> str:
        payload = f"app.{uid}.{int(time.time()) + 86400 * 30}"
        from web_admin import _sign
        return f"{payload}.{_sign(payload)}"

    def _verify(tok: str) -> int | None:
        try:
            payload, sig = tok.rsplit(".", 1)
            from web_admin import _sign
            if not hmac.compare_digest(_sign(payload), sig):
                return None
            role, uid, exp = payload.split(".")
            if role != "app" or int(exp) < time.time():
                return None
            return int(uid)
        except Exception:
            return None

    def _uid(request) -> int:
        tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip() \
            or request.cookies.get("happ", "")
        uid = _verify(tok)
        if not uid:
            raise HTTPException(401, "unauthorized")
        return uid

    class AuthIn(BaseModel):
        initData: str = ""

    @app.post("/api/app/auth")
    async def app_auth(body: AuthIn):
        user = _validate_init_data(body.initData)
        # Development-only fallback. Requires three explicit flags; a
        # copied .env in production cannot accidentally enable this.
        if (not user
                and os.getenv("APP_DEV_LOGIN") == "1"
                and os.getenv("APP_ENV", "production").lower() in {"dev", "test", "local"}
                and os.getenv("HERMES_MODE", "api").lower() != "api"):
            try:
                dev_id = int(body.initData or 0)
                if dev_id > 0:
                    user = {"id": dev_id, "first_name": "Dev"}
            except Exception:
                pass
        if not user:
            raise HTTPException(401, "از داخل تلگرام باز کن")
        uid = int(user["id"])
        import database as _dbm
        await _dbm.create_user(uid, user.get("username"), user.get("first_name"))
        u = await _dbm.get_user(uid)
        tok = _issue(uid)
        resp = __import__("fastapi").responses.JSONResponse({
            "token": tok,
            "user": {"id": uid, "name": u["first_name"], "username": u["username"],
                     "credits": u["credits"], "role": u["role"]},
        })
        resp.set_cookie("happ", tok, max_age=86400 * 30, httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "1" if os.getenv("APP_ENV", "production") == "production" else "0") == "1",
                        samesite="lax", path="/")
        return resp

    @app.get("/api/app/me")
    async def app_me(request: Request):
        uid = _uid(request)
        from database import get_user
        u = await get_user(uid)
        if not u:
            # ghost user — create on the fly
            import database as _dbm
            tg_user = None
            try:
                t = __import__("fastapi").__dict__.get("_tg", None)
            except Exception:
                pass
            from database import create_user
            u = await create_user(uid, str(uid), f"User {uid}")
        return {"id": uid, "name": u["first_name"], "username": u["username"],
                "credits": u["credits"], "role": u["role"]}

    # ---------------------------------------- browser login (code flow) --

    import random as _random
    _login_codes: dict[int, tuple[str, float]] = {}   # uid → (code, expires)
    _verify_fails: dict[int, tuple[int, float]] = {}  # uid → (fails, window_start)

    def _verify_locked(uid: int) -> bool:
        now = time.time()
        cnt, ts = _verify_fails.get(uid, (0, now))
        if now - ts > 300:
            cnt = 0
        return cnt >= 5

    def _register_verify_fail(uid: int):
        now = time.time()
        cnt, ts = _verify_fails.get(uid, (0, now))
        if now - ts > 300:
            cnt = 0
        _verify_fails[uid] = (cnt + 1, now)

    class LoginRequestIn(BaseModel):
        telegram_id: int

    @app.post("/api/app/login-request")
    async def app_login_request(body: LoginRequestIn):
        """Send a 6-digit code to the user's bot chat."""
        if _verify_locked(body.telegram_id):
            raise HTTPException(429, "تلاش‌های زیاد — ۵ دقیقه صبر کن")
        from database import get_user
        u = await get_user(body.telegram_id)
        if not u or u.get("is_banned"):
            raise HTTPException(404, "کاربر پیدا نشد — اول در بات /start بزن")
        # prune stale codes so the dict cannot grow unbounded
        now = time.time()
        for k in [k for k, v in _login_codes.items() if v[1] < now]:
            _login_codes.pop(k, None)
        code = f"{_random.randint(100000, 999999)}"
        _login_codes[body.telegram_id] = (code, time.time() + 300)
        try:
            import asyncio as _aio
            bot_ref = _get_bot_ref()
            if bot_ref:
                await bot_ref.send_message(
                    body.telegram_id,
                    f"🔐 کد ورود به DropAgentX:\n\n"
                    f"<b><code>{code}</code></b>\n\n"
                    f"⏱ ۵ دقیقه اعتبار دارد.\n"
                    f"🚫 اگر تو این درخواست را ندادی، نادیده بگیر.",
                    parse_mode="HTML")
            else:
                raise HTTPException(503, "بات در این پروسه اجرا نیست — از تلگرام باز کن")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "ارسال پیام ناموفق — بعداً تلاش کن")
        return {"ok": True, "message": "کد به چت تلگرامت ارسال شد 📨"}

    class LoginVerifyIn(BaseModel):
        telegram_id: int
        code: str

    @app.post("/api/app/login-verify")
    async def app_login_verify(body: LoginVerifyIn):
        if _verify_locked(body.telegram_id):
            raise HTTPException(429, "تلاش‌های زیاد — ۵ دقیقه صبر کن")
        stored = _login_codes.get(body.telegram_id)
        if not stored or time.time() > stored[1]:
            _login_codes.pop(body.telegram_id, None)
            raise HTTPException(400, "کد منقضی شده — دوباره درخواست بده")
        if not hmac.compare_digest(stored[0], body.code.strip()):
            _register_verify_fail(body.telegram_id)
            raise HTTPException(401, "کد اشتباه است")
        _login_codes.pop(body.telegram_id, None)
        _verify_fails.pop(body.telegram_id, None)
        uid = body.telegram_id
        from database import get_user, create_user
        u = await get_user(uid)
        if not u or u.get("is_banned"):
            raise HTTPException(404, "حساب یافت نشد")
        tok = _issue(uid)
        resp = __import__("fastapi").responses.JSONResponse({
            "token": tok,
            "user": {"id": uid, "name": u["first_name"], "username": u["username"],
                     "credits": u["credits"], "role": u["role"]},
        })
        resp.set_cookie("happ", tok, max_age=86400 * 30, httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "1" if os.getenv("APP_ENV", "production") == "production" else "0") == "1",
                        samesite="lax", path="/")
        return resp

    # ---------------------------------------- credit mint cap (3-A) ------

    async def _check_mint_budget(amount: int) -> tuple[bool, str]:
        """Check if free-credit distribution is within monthly budget.
        Returns (allowed, message)."""
        from database import get_db, get_setting, set_setting
        month_key = time.strftime("%Y-%m")
        budget = int(float(await get_setting("mint_cap_monthly", "50000")))
        cur_key = await get_setting("mint_month", "")
        if cur_key != month_key:
            await set_setting("mint_month", month_key)
            await set_setting("mint_used", "0")
        used = int(float(await get_setting("mint_used", "0")))
        if used + amount > budget:
            return False, f"سقف هدیهٔ این ماه پر شده ({used:,}/{budget:,} کردیت)"
        await set_setting("mint_used", str(used + amount))
        return True, ""

    def _get_commission_rate(uid: int) -> float:
        """2-C: commission based on seller plan."""
        import asyncio
        try:
            from database import get_db
            # can't await here — use sync fallback
            pass
        except Exception:
            pass
        return cfg.COMMISSION_RATE  # default; overridden per-sale

    # --------------------------------- product images (3-type system) ----

    IMG_SIZES = {
        "main": (1080, 1080),    # 1:1 — product detail page
        "feed": (1920, 1080),   # 16:9 — home feed thumbnail
        "story": (1080, 1920),  # 9:16 — explore / short preview
    }

    def _process_and_save_image(raw: bytes, pid: int, img_type: str) -> str:
        """Center-crop + resize to exact dims, save as optimized JPEG.
        VPS-ready: uses cfg.UPLOAD_DIR (relative or absolute)."""
        from PIL import Image, ImageOps
        import io as _io
        w, h = IMG_SIZES[img_type]
        img = Image.open(_io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        src_ratio = img.width / img.height
        dst_ratio = w / h
        if src_ratio > dst_ratio:
            new_h = img.height
            new_w = int(new_h * dst_ratio)
            left = (img.width - new_w) // 2
            img = img.crop((left, 0, left + new_w, img.height))
        else:
            new_w = img.width
            new_h = int(new_w / dst_ratio)
            top = (img.height - new_h) // 2
            img = img.crop((0, top, img.width, top + new_h))
        img = img.resize((w, h), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)

        dest_dir = os.path.join(cfg.UPLOAD_DIR, "products", str(pid))
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, f"{img_type}.jpg")
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        return path

    @app.post("/api/app/product/{pid}/images")
    async def app_upload_product_images(
        pid: int, request: Request,
        img_main: UploadFile = File(None),
        img_feed: UploadFile = File(None),
        img_story: UploadFile = File(None),
    ):
        uid = _uid(request)
        p = await get_product(pid)
        if not p:
            raise HTTPException(404, "محصول پیدا نشد")
        if p["creator_id"] != uid:
            raise HTTPException(403, "فقط سازنده می‌تواند عکس بگذارد")

        results, errors = {}, []
        for field, fobj in [("main", img_main), ("feed", img_feed), ("story", img_story)]:
            if not fobj or not fobj.filename:
                continue
            raw = await fobj.read()
            if len(raw) > 10 * 1024 * 1024:
                errors.append(f"{field}: فایل بزرگ‌تر از ۱۰MB")
                continue
            try:
                path = await asyncio.to_thread(
                    _process_and_save_image, raw, pid, field)
                col = f"img_{field}"
                async with get_db() as db:
                    await db.execute(
                        f"UPDATE products SET {col}=? WHERE id=?", (path, pid))
                    await db.commit()
                results[field] = f"/media/products/{pid}/{field}.jpg"
            except Exception as e:
                errors.append(f"{field}: {e}")

        if errors and not results:
            raise HTTPException(400, "; ".join(errors))
        return {"ok": True, "images": results,
                "errors": errors if errors else None}

    class ProductImagesIn(BaseModel):
        pass

    # ------------------------------------------------------ taxonomy ----

    @app.get("/api/app/categories")
    async def app_categories():
        from database import get_db
        async with get_db() as db:
            cur = await db.execute(
                "SELECT category, COUNT(*) FROM products "
                "WHERE is_active=1 AND status='approved' GROUP BY category")
            counts = {r[0]: r[1] for r in await cur.fetchall()}
        items = []
        for key, fa, icon in CATEGORIES:
            n = counts.get(key, 0) or (counts.get(CAT_MAP.get(key, ""), 0))
            items.append({"key": key, "fa": fa, "icon": icon, "count": int(n or 0)})
        return {"items": items}

    # ----------------------------------------------------------- feed ----

    async def _feed_rows(uid: int | None, mode: str, cat: str, off: int):
        from database import get_db
        cond = "p.is_active=1 AND p.status='approved'"
        params: list = []
        if cat and cat != "all":
            cond += " AND p.category=?"
            params.append(cat)
        follow_sel = ""
        order = ("(COALESCE(p.like_count,0)*3 + COALESCE(p.sales_count,0)*4 "
                 "+ COALESCE(p.impressions,0)*0.05) "
                 "/ (1 + (strftime('%s','now') - p.created_at)/172800.0) DESC")
        if mode == "following" and uid:
            follow_sel = (", (CASE WHEN EXISTS(SELECT 1 FROM follows f "
                          "WHERE f.follower_id=? AND f.target_id=p.creator_id) "
                          "THEN 1 ELSE 0 END) AS is_follow")
            order = "is_follow DESC, " + order
            params.append(int(uid))
        sql = f"""
            SELECT p.id, p.title, p.description, p.price_credits, p.photo_path,
                   p.preview_path, p.category, p.sales_count, p.is_featured,
                   COALESCE(p.like_count,0) like_count,
                   COALESCE(p.dislike_count,0) dislike_count,
                   COALESCE(p.comment_count,0) comment_count,
                   COALESCE(p.save_count,0) save_count,
                   COALESCE(p.impressions,0) impressions,
                   COALESCE(p.views,0) views,
                   u.first_name creator_name, u.username creator_username,
                   u.user_id creator_id {follow_sel}
            FROM products p LEFT JOIN users u ON u.user_id=p.creator_id
            WHERE {cond}
            ORDER BY {order} LIMIT ? OFFSET ?"""
        params += [FEED_LIMIT, off]
        async with get_db() as db:
            cur = await db.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in await cur.fetchall()]
        for r in rows:
            r["photo_url"] = _media(r.pop("photo_path") or r.pop("preview_path"))
        return rows

    def _media(path: str | None) -> str | None:
        if not path:
            return None
        up = os.path.abspath(cfg.UPLOAD_DIR)
        rel = os.path.relpath(os.path.abspath(path), up).replace("\\", "/")
        if not rel.startswith("..") and os.path.isfile(os.path.join(up, *rel.split("/"))):
            return f"/media/{rel}"  # e.g. covers/xxx.png or <uid>/prod_x.jpg
        # legacy: bare filename living in the uploads root
        base = os.path.basename(path.replace("\\", "/"))
        if base and os.path.isfile(os.path.join(up, base)):
            return f"/media/{base}"
        return None

    @app.get("/api/app/feed")
    async def app_feed(request: Request, mode: str = "foryou", cat: str = "all",
                       cursor: int = 0):
        uid = None
        try:
            uid = _uid(request)
        except HTTPException:
            pass
        rows = await _feed_rows(uid, mode, cat, max(0, cursor))
        # impression accounting (cheap single UPDATE per page)
        if rows:
            ids = ",".join(str(r["id"]) for r in rows)
            from database import raw_db
            async with raw_db() as db:
                await db.execute(
                    f"UPDATE products SET impressions=impressions+1 WHERE id IN ({ids})")
        me_likes = set()
        if uid and rows:
            ids = [str(r["id"]) for r in rows]
            from database import get_db
            async with get_db() as db:
                cur = await db.execute(
                    f"SELECT product_id, type FROM product_engagement WHERE user_id=? "
                    f"AND product_id IN ({','.join('?' * len(ids))})",
                    [uid] + ids)
                for pid, typ in await cur.fetchall():
                    if typ in ("like", "dislike", "save"):
                        me_likes.add((pid, typ))
        for r in rows:
            r["liked"] = (r["id"], "like") in me_likes
            r["disliked"] = (r["id"], "dislike") in me_likes
            r["saved"] = (r["id"], "save") in me_likes
            r["usd"] = round(r["price_credits"] / max(1, cfg.CREDITS_PER_USDT), 2)
        return {"items": rows, "next": cursor + FEED_LIMIT if len(rows) == FEED_LIMIT else None}

    @app.get("/api/app/trending")
    async def app_trending(request: Request, limit: int = 10):
        rows = await _feed_rows(None, "trend", "all", 0)
        out = []
        for i, r in enumerate(rows[:max(1, min(limit, 20))], 1):
            r["rank"] = i
            r["usd"] = round(r["price_credits"] / max(1, cfg.CREDITS_PER_USDT), 2)
            out.append(r)
        return {"items": out}

    @app.get("/api/app/search")
    async def app_search(request: Request, q: str = ""):
        from database import escape_like, get_db
        e = f"%{escape_like(q.strip())}%"
        products, users = [], []
        if len(q.strip()) >= 2:
            async with get_db() as db:
                cur = await db.execute(
                    """SELECT id,title,price_credits,photo_path,preview_path,sales_count
                       FROM products WHERE is_active=1 AND status='approved'
                       AND (title LIKE ? OR tags LIKE ? OR description LIKE ?)
                       LIMIT 12""", (e, e, e))
                cols = [d[0] for d in cur.description]
                products = [dict(zip(cols, r)) for r in await cur.fetchall()]
                cur = await db.execute(
                    """SELECT user_id, username, first_name FROM users
                       WHERE is_banned=0 AND (username LIKE ? OR first_name LIKE ?)
                       LIMIT 8""", (e, e))
                cols = [d[0] for d in cur.description]
                users = [dict(zip(cols, r)) for r in await cur.fetchall()]
        for p in products:
            p["photo_url"] = _media(p.pop("photo_path") or p.pop("preview_path"))
            p["usd"] = round(p["price_credits"] / max(1, cfg.CREDITS_PER_USDT), 2)
        return {"products": products, "users": users}

    # ---------------------------------------------- product detail ------

    @app.get("/api/app/product/{pid}")
    async def app_product(pid: int, request: Request):
        from database import get_db, product_rating
        uid = None
        try:
            uid = _uid(request)
        except HTTPException:
            pass
        async with get_db() as db:
            cur = await db.execute(
                """SELECT p.*, u.first_name creator_name, u.username creator_username
                   FROM products p LEFT JOIN users u ON u.user_id=p.creator_id
                   WHERE p.id=?""", (pid,))
            cols = [d[0] for d in cur.description]
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404)
            p = dict(zip(cols, row))
            stars, nrev = None, 0
            cr = await db.execute(
                "SELECT AVG(stars), COUNT(*) FROM reviews WHERE product_id=?", (pid,))
            stars, nrev = await cr.fetchone()
            cm = await db.execute(
                """SELECT c.id, c.text, c.created_at, u.first_name, u.username
                   FROM product_comments c LEFT JOIN users u ON u.user_id=c.user_id
                   WHERE c.product_id=? ORDER BY c.id DESC LIMIT 30""", (pid,))
            ccols = [d[0] for d in cm.description]
            comments = [dict(zip(ccols, r)) for r in await cm.fetchall()]
        my = {}
        if uid:
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT type FROM product_engagement WHERE product_id=? AND user_id=?",
                    (pid, uid))
                my = {r[0]: True for r in await cur.fetchall()}
        async with get_db() as db:
            await db.execute("UPDATE products SET views=views+1 WHERE id=?", (pid,))
        p["photo_url"] = _media(p.get("photo_path") or p.get("preview_path"))
        # Do not leak server paths or a downloadable file URL from a public
        # product detail response.
        for key in ("file_path", "preview_path", "photo_path", "img_main",
                    "img_feed", "img_story"):
            p.pop(key, None)
        p["usd"] = round(p["price_credits"] / max(1, cfg.CREDITS_PER_USDT), 2)
        return {"item": p, "stars": round(stars or 0, 1), "reviews": nrev or 0,
                "comments": comments, "my": my}

    class EngageIn(BaseModel):
        product_id: int
        type: str  # like | dislike | save | click

    @app.post("/api/app/engage")
    async def app_engage(body: EngageIn, request: Request):
        uid = _uid(request)
        typ = body.type
        col = {"like": "like_count", "dislike": "dislike_count",
               "save": "save_count", "click": "clicks", "view": "views"}.get(typ)
        if not col:
            raise HTTPException(400)

        # 5-A/B: engagement micro-rewards
        reward = 0
        if typ == "like":
            reward = int(float(os.getenv("REWARD_LIKE", "0.1")) * 100) / 100
        elif typ == "save":
            reward = float(os.getenv("REWARD_SAVE", "0.5"))

        from database import get_db, raw_db, update_credits
        toggled = False
        if typ in ("like", "dislike", "save"):
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT 1 FROM product_engagement WHERE product_id=? AND user_id=? AND type=?",
                    (body.product_id, uid, typ))
                exists = await cur.fetchone()
                other = "dislike" if typ == "like" else "like"
                if exists:
                    await db.execute(
                        "DELETE FROM product_engagement WHERE product_id=? AND user_id=? AND type=?",
                        (body.product_id, uid, typ))
                    delta = -1
                else:
                    if typ in ("like", "dislike"):
                        ocol = "dislike_count" if typ == "like" else "like_count"
                        otyp = other
                        cur2 = await db.execute(
                            "SELECT 1 FROM product_engagement WHERE product_id=? AND user_id=? AND type=?",
                            (body.product_id, uid, otyp))
                        if await cur2.fetchone():
                            await db.execute(
                                "DELETE FROM product_engagement WHERE product_id=? AND user_id=? AND type=?",
                                (body.product_id, uid, otyp))
                            await db.execute(
                                f"UPDATE products SET {ocol}=MAX(0,{ocol}-1) WHERE id=?",
                                (body.product_id,))
                    await db.execute(
                        "INSERT OR IGNORE INTO product_engagement (product_id,user_id,type) VALUES (?,?,?)",
                        (body.product_id, uid, typ))
                    delta = 1
                    toggled = True
                await db.execute(
                    f"UPDATE products SET {col}=MAX(0,{col}+?) WHERE id=?",
                    (delta, body.product_id))
        else:  # click/view counters — anonymous ok
            toggled = True
            async with raw_db() as db:
                await db.execute(f"UPDATE products SET {col}={col}+1 WHERE id=?",
                                 (body.product_id,))

        # 5-A/B: engagement micro-reward (only on toggle-on)
        if reward > 0 and toggled:
            # daily cap: likes 10/day (1 credit), saves 4/day (2 credits)
            today = time.strftime("%Y-%m-%d")
            cap_key = f"eng_reward_{uid}_{today}"
            eng_count = getattr(app_engage, cap_key, 0)
            max_daily = {"like": 10, "save": 4}.get(typ, 0)
            if eng_count < max_daily:
                await update_credits(uid, int(reward * 100) / 100,
                                     "admin_grant", f"engagement_{typ}")
                setattr(app_engage, cap_key, eng_count + 1)

        return {"ok": True, "on": toggled}

    class CommentIn(BaseModel):
        product_id: int
        text: str

    @app.post("/api/app/comment")
    async def app_comment(body: CommentIn, request: Request):
        uid = _uid(request)
        text = body.text.strip()[:500]
        if len(text) < 2:
            raise HTTPException(400, "متن کوتاه است")
        from database import get_db, update_credits
        async with get_db() as db:
            # reward only the FIRST comment per user per product (anti-farm)
            cur = await db.execute(
                "SELECT 1 FROM product_comments WHERE product_id=? AND user_id=? LIMIT 1",
                (body.product_id, uid))
            already = await cur.fetchone()
            await db.execute(
                "INSERT INTO product_comments (product_id,user_id,text) VALUES (?,?,?)",
                (body.product_id, uid, text))
            await db.execute(
                "UPDATE products SET comment_count=comment_count+1 WHERE id=?",
                (body.product_id,))
            rewarded = already is None
            if rewarded:  # daily cap on rewarded comments
                cur = await db.execute(
                    "SELECT COUNT(*) FROM transactions WHERE user_id=? AND tx_type='admin_grant' "
                    "AND description='comment reward' AND created_at > ?",
                    (uid, time.time() - 86400))
                rewarded = (await cur.fetchone())[0] < 5
        if rewarded:
            await update_credits(uid, 1, "admin_grant", "comment reward")
        return {"ok": True}

    # ------------------------------------------------------------ follows -

    class FollowIn(BaseModel):
        target: int
        on: bool

    @app.post("/api/app/follow")
    async def app_follow(body: FollowIn, request: Request):
        uid = _uid(request)
        if body.target == uid:
            raise HTTPException(400, "خودت!")
        from database import get_db
        async with get_db() as db:
            if body.on:
                await db.execute(
                    "INSERT OR IGNORE INTO follows (follower_id,target_id) VALUES (?,?)",
                    (uid, body.target))
            else:
                await db.execute(
                    "DELETE FROM follows WHERE follower_id=? AND target_id=?",
                    (uid, body.target))
        return {"ok": True}

    @app.get("/api/app/following-ids")
    async def app_following_ids(request: Request):
        uid = _uid(request)
        from database import get_db
        async with get_db() as db:
            cur = await db.execute(
                "SELECT target_id FROM follows WHERE follower_id=?", (uid,))
            return {"ids": [r[0] for r in await cur.fetchall()]}

    # ------------------------------------------------------------- buy ----

    @app.post("/api/app/buy/{pid}")
    async def app_buy(pid: int, request: Request):
        uid = _uid(request)
        from commerce import CommerceError, apply_sale_network_effects, purchase_with_credits

        try:
            result = await purchase_with_credits(uid, pid, payment_method="credits")
        except CommerceError as e:
            msg = str(e)
            code = 409 if "قبلاً" in msg else 400
            raise HTTPException(code, msg)

        try:
            from memory import record_purchase_event
            await record_purchase_event(uid, result.product)
        except Exception:
            logger.warning("purchase memory update failed (uid=%s, pid=%s)", uid, pid)

        # Referral/upline rewards are shared with the Telegram purchase path.
        await apply_sale_network_effects(result, _get_bot_ref())
        from database import get_user
        bal = await get_user(uid)
        return {
            "ok": True,
            "file_url": _media(result.product.get("file_path")),
            "balance": bal["credits"],
        }

    # ----------------------------------------------------------- wallet ---

    @app.get("/api/app/wallet")
    async def app_wallet(request: Request):
        uid = _uid(request)
        from database import get_user, get_db
        u = await get_user(uid)
        async with get_db() as db:
            cur = await db.execute(
                """SELECT tx_type, amount, description, created_at FROM transactions
                   WHERE user_id=? ORDER BY id DESC LIMIT 25""", (uid,))
            cols = [d[0] for d in cur.description]
            txs = [dict(zip(cols, r)) for r in await cur.fetchall()]
        return {"credits": u["credits"], "earned": u["total_earned"],
                "spent": u["total_spent"], "txs": txs,
                "per_usdt": cfg.CREDITS_PER_USDT}

    # ------------------------------------------- store / create / misc --

    async def _save_upload(request, max_mb: int, exts: set) -> str | None:
        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" not in ctype:
            return None
        import re as _re
        m = _re.search(r'boundary=([^;]+)', ctype)
        if not m:
            return None
        boundary = m.group(1).encode()
        raw = await request.body()
        if len(raw) > max_mb * 1024 * 1024:
            raise HTTPException(413, "فایل بزرگ است")
        parts = raw.split(b"--" + boundary)
        out = None
        for part in parts[1:-1]:
            head, _, body = part.partition(b"\r\n\r\n")
            disp = head.decode("utf-8", "ignore")
            fnm = _re.search(r'filename="([^"]*)"', disp)
            if not fnm:
                continue
            name = os.path.basename(fnm.group(1))
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            body = body.rstrip(b"\r\n")
            if exts != {""} and ext not in exts:
                continue
            dest_dir = os.path.join(os.path.abspath(cfg.UPLOAD_DIR), str(int(time.time()))[-6:])
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, f"{int(time.time()*1000)}.{ext or 'bin'}")
            with open(dest, "wb") as f:
                f.write(body)
            out = dest
            break
        return out

    class CreateIn(BaseModel):
        title: str
        description: str = ""
        category: str = "other"
        price_credits: int

    @app.post("/api/app/create-product")
    async def app_create(request: Request):
        uid = _uid(request)
        ctype = request.headers.get("content-type", "")
        photo_path = None
        title = desc = cat = None
        price = None
        if "multipart/form-data" in ctype:
            form = await request.form()
            title = str(form.get("title", "")).strip()
            desc = str(form.get("description", "")).strip()
            cat = str(form.get("category", "other")).strip().lower()
            price = int(form.get("price_credits", 0))
            up = form.get("photo")
            if up is not None and hasattr(up, "read"):
                data = await up.read()
                if len(data) > 8 * 1024 * 1024:
                    raise HTTPException(413, "عکس بزرگ است (حداکثر ۸MB)")
                ext = {"image/jpeg": "jpg", "image/png": "png"}.get(up.content_type, "")
                if ext:
                    d = os.path.join(os.path.abspath(cfg.UPLOAD_DIR), str(uid))
                    os.makedirs(d, exist_ok=True)
                    path = os.path.join(d, f"prod_{int(time.time()*1000)}.{ext}")
                    with open(path, "wb") as f:
                        f.write(data)
                    photo_path = path
        else:
            body = await request.json()
            title = str(body.get("title", "")).strip()
            desc = str(body.get("description", "")).strip()
            cat = str(body.get("category", "other")).strip().lower()
            price = int(body.get("price_credits", 0))
        if len(title) < 3:
            raise HTTPException(400, "عنوان کوتاه است")
        if price < 5 or price > 200000:
            raise HTTPException(400, "قیمت باید بین ۵ تا ۲۰۰٬۰۰۰ کردیت باشد")
        cat = CAT_MAP.get(cat, cat if any(c[0] == cat for c in CATEGORIES) else "other")
        from database import get_db
        pid = None
        async with get_db() as db:
            cur = await db.execute(
                """INSERT INTO products (creator_id, title, description, price_credits,
                       category, status, created_at)
                   VALUES (?,?,?,?,?, 'pending', strftime('%s','now'))""",
                (uid, title[:120], desc[:1000], price, cat))
            pid = cur.lastrowid
            if photo_path:
                await db.execute("UPDATE products SET photo_path=? WHERE id=?",
                                 (photo_path, pid))
            await db.commit()
        return {"ok": True, "id": pid,
                "note": "پس از تأیید ادمین در مارکت منتشر می‌شود ⏳"}

    @app.post("/api/app/me/photo/{kind}")  # kind: avatar | cover
    async def app_me_photo(kind: str, request: Request):
        uid = _uid(request)
        if kind not in ("avatar", "cover"):
            raise HTTPException(400)
        saved = await _save_upload(request, 8, {"jpg", "jpeg", "png"})
        if not saved:
            raise HTTPException(400, "عکس JPG/PNG بفرست")
        col = "avatar_path" if kind == "avatar" else "cover_path"
        from database import get_db
        async with get_db() as db:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                await db.commit()
            except Exception:
                pass
        async with get_db() as db:
            await db.execute(f"UPDATE users SET {col}=? WHERE user_id=?", (saved, uid))
        return {"ok": True, "url": _media(saved)}

    @app.get("/api/app/store/{target}")
    async def app_store(target: int, request: Request):
        me = _uid(request)
        from database import get_db, get_user
        u = await get_user(target)
        async with get_db() as db:
            cur = await db.execute(
                """SELECT id,title,price_credits,sales_count,photo_path,preview_path,
                          like_count,comment_count
                   FROM products WHERE creator_id=? AND is_active=1 AND status='approved'
                   ORDER BY id DESC LIMIT 30""", (target,))
            cols = [d[0] for d in cur.description]
            items = [dict(zip(cols, r)) for r in await cur.fetchall()]
            cf = await db.execute(
                "SELECT COUNT(*) FROM follows WHERE target_id=?", (target,))
            followers = (await cf.fetchone())[0]
            fol = await db.execute(
                "SELECT 1 FROM follows WHERE follower_id=? AND target_id=?",
                (me, target))
            following = bool(await fol.fetchone())
        for p in items:
            p["photo_url"] = _media(p.pop("photo_path") or p.pop("preview_path"))
            p["usd"] = round(p["price_credits"] / max(1, cfg.CREDITS_PER_USDT), 2)
        total_sales = sum(i.get("sales_count") or 0 for i in items)

        def pic(col):
            p = u.get(col) if isinstance(u, dict) else (u[col] if col in u.keys() else None)
            return _media(p)

        try:
            avatar_url = _media(u["avatar_path"]) if "avatar_path" in u.keys() else None
            cover_url = _media(u["cover_path"]) if "cover_path" in u.keys() else None
        except Exception:
            avatar_url = cover_url = None
        return {
            "id": target, "name": u["first_name"], "username": u["username"],
            "bio": "", "followers": followers, "following_me": following,
            "avatar_url": avatar_url, "cover_url": cover_url,
            "products": items, "total_sales": total_sales, "is_me": target == me,
        }

    @app.get("/api/app/activity")
    async def app_activity(request: Request):
        uid = _uid(request)
        from database import get_db
        async with get_db() as db:
            cur = await db.execute(
                """SELECT pc.id, pc.price_credits, pc.purchased_at, pr.title, pr.file_path
                   FROM purchases pc JOIN products pr ON pr.id=pc.product_id
                   WHERE pc.buyer_id=? ORDER BY pc.purchased_at DESC LIMIT 20""", (uid,))
            cols = [d[0] for d in cur.description]
            bought = []
            for r in await cur.fetchall():
                d = dict(zip(cols, r))
                d["download_url"] = _media(d.get("file_path"))
                d.pop("file_path", None)
                bought.append(d)
            cur = await db.execute(
                """SELECT pc.id, pc.price_credits, pc.purchased_at, pr.title, u.first_name buyer
                   FROM purchases pc JOIN products pr ON pr.id=pc.product_id
                   JOIN users u ON u.user_id=pc.buyer_id
                   WHERE pr.creator_id=? ORDER BY pc.purchased_at DESC LIMIT 20""", (uid,))
            cols = [d[0] for d in cur.description]
            sold = [dict(zip(cols, r)) for r in await cur.fetchall()]
        return {"bought": bought, "sold": sold}

    @app.post("/api/app/agent")
    async def app_agent(request: Request):
        uid = _uid(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "bad json")
        text = str(body.get("text", "")).strip()[:800]
        if not text:
            raise HTTPException(400)
        from ai_agent import smart_messages, AI_SYSTEM_PROMPT
        from hermes_engine import hermes_chat_stream, HermesEngineError, redact_secrets
        async def _noop(_acc):  # engine awaits on_delta; a sync lambda breaks it
            return None
        msgs = await smart_messages(uid, AI_SYSTEM_PROMPT, text)
        try:
            answer = await hermes_chat_stream(msgs, _noop)
        except HermesEngineError as e:
            logger.warning("mini-app agent engine error (uid=%s): %s", uid, e)
            raise HTTPException(502, str(e))
        except Exception as e:  # noqa: BLE001 — 500s are invisible on Railway
            logger.exception("mini-app agent failed (uid=%s)", uid)
            raise HTTPException(502, redact_secrets(
                f"engine failure: {type(e).__name__}: {e}")[:300])
        return {"answer": (answer or "").strip()[:3800]}
