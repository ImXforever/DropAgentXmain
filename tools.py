"""Safe AI tools (function calling) — the agent's hands.

Every tool maps to a vetted local function with permission checks.
The model never touches raw SQL or the filesystem directly.
"""

import json

from config import config as cfg


# ---------- OpenAI-format tool specs ----------

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "search_products",
        "description": "جستجوی محصولات مارکت‌پلیس",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "category": {"type": "string", "enum": ["education", "graphics", "coding", "content", "template", "tools", "general"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "my_balance",
        "description": "موجودی کردیت کاربر و معادل دلاری",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "my_products",
        "description": "لیست محصولات خود کاربر با قیمت و فروش",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "my_referrals",
        "description": "آمار دعوت‌های کاربر و درآمد شبکه",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "platform_stats",
        "description": "آمار کلی پلتفرم (کاربر/محصول/فروش)",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "create_coupon",
        "description": "ساخت کد تخفیف برای محصولات فروشنده (نیاز به رتبه سرباز+)",
        "parameters": {"type": "object", "properties": {
            "percent": {"type": "integer"}, "max_uses": {"type": "integer"},
        }, "required": ["percent", "max_uses"]},
    }},
    {"type": "function", "function": {
        "name": "set_product_price",
        "description": "تغییر قیمت یکی از محصولات خود کاربر",
        "parameters": {"type": "object", "properties": {
            "product_id": {"type": "integer"}, "price_credits": {"type": "integer"},
        }, "required": ["product_id", "price_credits"]},
    }},
    {"type": "function", "function": {
        "name": "save_knowledge",
        "description": "ذخیره یک یادداشت ارزشمند در مغز دوم کاربر",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"}, "content": {"type": "string"},
        }, "required": ["topic", "content"]},
    }},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "جستجو در مغز دوم کاربر",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "جستجوی وب (DuckDuckGo) برای شواهد تازه",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "read_webpage",
        "description": "خواندن متن یک صفحه وب",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                        "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "run_python",
        "description": "اجرای امن کد پایتون در سندباکس (برای محاسبه/تست Forge)",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string"}}, "required": ["code"]},
    }},
    {"type": "function", "function": {
        "name": "history_search",
        "description": "جستجوی تمام-متن در تاریخچه گفتگوی کاربر",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "generate_cover_image",
        "description": "تولید تصویر کاور محصول با هوش مصنوعی",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string"}}, "required": ["prompt"]},
    }},
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "لیست مهارت‌های نصب‌شده پلتفرم با توضیح هر کدام",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "load_skill",
        "description": "خواندن دستورالعمل کامل یک مهارت خاص (برای اجرای درست وظیفه)",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]},
    }},
]

# --- V3: File tools ---
from file_tools import TOOL_SPECS as _FILE_SPECS
TOOL_SPECS.extend(_FILE_SPECS)

# --- V3: Terminal sandbox ---
TOOL_SPECS.append({"type": "function", "function": {
    "name": "run_shell",
    "description": "اجرای دستور shell در سندباکس ایمن (با دروازه تأیید برای دستورات خطرناک)",
    "parameters": {"type": "object", "properties": {
        "command": {"type": "string", "description": "دستور shell"},
    }, "required": ["command"]},
}})

# --- V3: Browser automation ---
from browser_tools import TOOL_SPECS as _BROWSER_SPECS
TOOL_SPECS.extend(_BROWSER_SPECS)


async def execute_tool(name: str, args: dict, user_id: int) -> str:
    from database import (
        search_products, get_my_products, get_user, update_product_field,
        get_role, create_coupon, kb_save, kb_search,
        count_total_refs, count_qualified_refs, get_db, usdt_to_credits,
        get_all_users_count, get_total_products, get_total_sales,
    )
    args = args or {}
    try:
        if name == "search_products":
            rows = await search_products(
                query=args.get("query", ""), category=args.get("category", ""), limit=8)
            return json.dumps([
                {"id": r["id"], "title": r["title"], "price_credits": r["price_credits"],
                 "sales": r["sales_count"], "category": r["category"]} for r in rows],
                ensure_ascii=False)

        if name == "my_balance":
            u = await get_user(user_id)
            c = (u or {}).get("credits", 0)
            return json.dumps({"credits": c, "usdt": round(c / cfg.CREDITS_PER_USDT, 2)})

        if name == "my_products":
            rows = await get_my_products(user_id)
            return json.dumps([
                {"id": p["id"], "title": p["title"], "price_credits": p["price_credits"],
                 "sales": p["sales_count"], "active": bool(p["is_active"])} for p in rows[:15]],
                ensure_ascii=False)

        if name == "my_referrals":
            total = await count_total_refs(user_id)
            qual = await count_qualified_refs(user_id)
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? "
                    "AND tx_type IN ('ref_bonus','ref_mystery','ref_commission','ref_milestone')",
                    (user_id,))
                earned = (await cur.fetchone())[0]
            return json.dumps({"invited": total, "qualified": qual, "earned_credits": earned})

        if name == "platform_stats":
            return json.dumps({
                "users": await get_all_users_count(),
                "products": await get_total_products(),
                "sales": await get_total_sales(),
            })

        if name == "create_coupon":
            role = await get_role(user_id)
            if role not in ("soldier", "capo", "underboss") and user_id not in cfg.ADMIN_IDS:
                return json.dumps({"error": "فقط سرباز به بالا می‌تواند کوپن بسازد."})
            pct = int(args.get("percent", 0)); uses = int(args.get("max_uses", 1))
            if not (1 <= pct <= 90 and 1 <= uses <= 10000):
                return json.dumps({"error": "درصد ۱-۹۰ و ظرفیت ۱-۱۰۰۰۰"})
            import secrets
            code = f"AI{secrets.token_hex(3).upper()}"
            cid = await create_coupon(user_id, code, pct, uses)
            if cid is None:
                return json.dumps({"error": "کد تکراری شد؛ دوباره تلاش کن."})
            return json.dumps({"created": code, "percent": pct, "max_uses": uses})

        if name == "set_product_price":
            pid = int(args.get("product_id", 0))
            price = int(args.get("price_credits", 0))
            if price < 1:
                return json.dumps({"error": "قیمت باید مثبت باشد."})
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT creator_id FROM products WHERE id = ?", (pid,))
                row = await cur.fetchone()
            if not row or row[0] != user_id:
                return json.dumps({"error": "این محصول متعلق به تو نیست."})
            await update_product_field(pid, "price_credits", price)
            return json.dumps({"updated": pid, "new_price": price})

        if name == "save_knowledge":
            await kb_save(user_id, args.get("topic", "یادداشت"),
                          args.get("content", ""), source="ai-tool")
            return json.dumps({"saved": True})

        if name == "search_knowledge":
            notes = await kb_search(user_id, args.get("query", ""), limit=3)
            return json.dumps([{"topic": n["topic"], "excerpt": n["content"][:200]}
                               for n in notes], ensure_ascii=False)

        if name == "web_search":
            from webtools import web_search as _ws
            rows = await _ws(args.get("query", ""), int(args.get("max_results", 5)))
            return json.dumps(rows, ensure_ascii=False)[:2500]

        if name == "read_webpage":
            from webtools import read_webpage as _rw
            return (await _rw(args.get("url", "")))[:2500]

        if name == "run_python":
            # code execution is sensitive: admins by default; open to all
            # users only when the admin explicitly sets sandbox_for_users=1
            from hermes_engine import get_dynamic_setting
            if user_id not in cfg.ADMIN_IDS and \
                    (await get_dynamic_setting("sandbox_for_users", "0")) != "1":
                return json.dumps({"error": "اجرای کد فقط برای ادمین فعال است."})
            from sandbox import run_python as _rp
            return await _rp(args.get("code", ""))

        if name == "history_search":
            from database import history_search as _hs
            return json.dumps(await _hs(user_id, args.get("query", "")),
                              ensure_ascii=False)[:2500]

        if name == "generate_cover_image":
            role = await get_role(user_id)
            if role not in ("soldier", "capo", "underboss") and user_id not in cfg.ADMIN_IDS:
                return json.dumps({"error": "تصویرسازی فقط برای سرباز به بالاست."})
            from media_v2 import generate_image
            path = await generate_image(args.get("prompt", ""))
            return json.dumps({"saved": path})

        if name == "list_skills":
            from skills import list_skills
            items = await list_skills()
            enabled = [it for it in items if it["enabled"]]
            return json.dumps(
                [{"name": it["name"], "description": it["desc"],
                  "tags": it["tags"]} for it in enabled],
                ensure_ascii=False)

        if name == "load_skill":
            from skills import skill_read
            body = await skill_read(str(args.get("name", "")))
            if body is None:
                return json.dumps({"error": "مهارت پیدا نشد"})
            return body[:3000]

        # --- V3 File tools ---
        if name == "read_file":
            from file_tools import read_file
            result = await read_file(
                args.get("path", ""),
                line_start=int(args.get("line_start", 1)),
                line_end=int(args.get("line_end", 0)),
                user_id=user_id)
            return result.data["content"][:3000] if result.success else json.dumps({"error": result.message})

        if name == "write_file":
            from file_tools import write_file
            result = await write_file(
                args.get("path", ""),
                args.get("content", ""),
                mode=args.get("mode", "overwrite"),
                user_id=user_id)
            return json.dumps({"success": result.success, "message": result.message,
                               **(result.data or {})})

        if name == "patch_file":
            from file_tools import patch_file
            result = await patch_file(
                args.get("path", ""),
                args.get("old", ""),
                args.get("new", ""),
                user_id=user_id)
            return json.dumps({"success": result.success, "message": result.message,
                               **(result.data or {})})

        if name == "search_files":
            from file_tools import search_files
            result = await search_files(
                pattern=args.get("pattern", "*"),
                content_pattern=args.get("content_pattern", ""),
                directory=args.get("directory", "."),
                user_id=user_id)
            return json.dumps({"success": result.success, "count": len(result.data.get("results", [])),
                               "results": result.data.get("results", [])[:10]})

        # --- V3: Terminal sandbox tools ---
        if name == "run_shell":
            from sandbox import run_shell
            return await run_shell(args.get("command", ""))

        # --- V3: Browser tools ---
        browser_tools_map = {
            "browser_navigate": lambda a: browser_navigate(a["url"]),
            "browser_snapshot": lambda a: browser_snapshot(int(a.get("max_chars", 3000))),
            "browser_click": lambda a: browser_click(a["selector"]),
            "browser_type": lambda a: browser_type(a["selector"], a["text"], a.get("press_enter", False)),
            "browser_scroll": lambda a: browser_scroll(a.get("direction", "down")),
            "browser_back": lambda a: browser_back(),
            "browser_get_links": lambda a: browser_get_links(),
            "browser_get_images": lambda a: browser_get_images(),
        }
        if name in browser_tools_map:
            from browser_tools import (browser_navigate, browser_snapshot, browser_click,
                                        browser_type, browser_scroll, browser_back,
                                        browser_get_links, browser_get_images)
            return await browser_tools_map[name](args)

        return json.dumps({"error": f"ابزار ناشناخته: {name}"})
    except Exception as e:
        from hermes_engine import redact_secrets
        return json.dumps({"error": redact_secrets(str(e))[:200]})



async def execute_tool_routed(name: str, args: dict, user_id: int) -> str:
    if name.startswith("mcp__"):
        import mcp_lite
        return await mcp_lite.call_mcp_tool(name, args)
    return await execute_tool(name, args, user_id)
