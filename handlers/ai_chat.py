import logging
import os
import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from ai_agent import (
    chat_with_ai, generate_product_title,
    generate_product_description, generate_html_tutorial,
    AI_SYSTEM_PROMPT,
)
from database import get_user, get_db, update_credits
from config import config
from utils import get_or_create_user,  send_safe, edit_safe, ChatStream
from skills import build_skills_prompt

router = Router()
logger = logging.getLogger(__name__)


# ---- AI chat pricing: 1 credit per reply (admins free, cost adjustable) ----

def _is_admin_uid(uid: int) -> bool:
    return str(uid) in {s.strip() for s in
                        os.getenv("ADMIN_IDS", "").split(",") if s.strip()}


async def _ai_chat_cost() -> int:
    """Chat billing cost per reply. Default = FREE (0).
    Admin can enable billing: /set ai_chat_cost 1 or web panel toggle."""
    from hermes_engine import get_dynamic_setting
    return int(float(await get_dynamic_setting("ai_chat_cost", "0")) or 0)


async def _charge_ai_reply(uid: int) -> tuple[bool, int]:
    """Reserve credits BEFORE generating. Returns (ok, remaining)."""
    cost = await _ai_chat_cost()
    if cost <= 0 or _is_admin_uid(uid):
        return True, -1
    u = await get_user(uid)
    if not u or u["credits"] < cost:
        return False, 0
    await update_credits(uid, -cost, "ai_usage", "Hermesa chat reply")
    u2 = await get_user(uid)
    return True, u2["credits"] if u2 else 0


async def _refund_ai_reply(uid: int, reason: str) -> None:
    """Give a reserved chat credit back after ANY generation failure.

    Every exit path after _charge_ai_reply() must call this, otherwise the
    user silently loses credits (httpx/Telegram/OSError used to slip past the
    HermesEngineError-only handler).
    """
    try:
        cost = await _ai_chat_cost()
        if cost > 0 and not _is_admin_uid(uid):
            await update_credits(uid, cost, "admin_grant", f"refund — {reason}")
            logger.info("AI credit refunded (uid=%s, cost=%s, reason=%s)",
                        uid, cost, reason)
    except Exception:  # a broken refund must never mask the original error
        logger.exception("AI credit refund failed (uid=%s)", uid)


# ---- generated-file delivery -------------------------------------------------

def _extract_file_block(text: str):
    import re
    fences = re.findall(r"```([\w+#.-]*)\n(.*?)```", text or "", re.DOTALL)
    if not fences:
        return None
    lang, code = max(fences, key=lambda f: len(f[1]))
    code = code.rstrip()
    if len(code) < 150:
        return None
    ext = {"html": "html", "htm": "html", "xml": "xml", "css": "css",
           "python": "py", "py": "py", "javascript": "js", "js": "js",
           "typescript": "ts", "ts": "ts", "tsx": "tsx", "json": "json",
           "sql": "sql", "bash": "sh", "sh": "sh", "markdown": "md",
           "md": "md", "yaml": "yml", "yml": "yml"}.get(lang.lower(), "txt")
    return ext, code + "\n"


async def _deliver_generated_file(bot, chat_id: int, uid: int, response: str):
    """When Hermesa produced a substantial code/HTML block → send it as a file."""
    try:
        got = _extract_file_block(response)
        if not got:
            return
        ext, code = got
        d = os.path.join(config.UPLOAD_DIR, "generated", str(uid))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"hermesa_{int(time.time())}.{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        from aiogram.types import FSInputFile
        await bot.send_document(
            chat_id, FSInputFile(path),
            caption=f"💌 فایل آماده‌ست! ({ext.upper()} · {len(code):,} کاراکتر)\nاگه تغییری خواستی بگو 💗")
    except Exception:
        pass


class AIChat(StatesGroup):
    chatting = State()
    generating_title = State()
    generating_description = State()
    generating_tutorial = State()


class TutorialSave(StatesGroup):
    waiting_meta = State()


class DocBuild(StatesGroup):
    waiting_topic = State()


class CustomBot(StatesGroup):
    waiting_cfg = State()


EXIT_COMMANDS = {"/back", "/start", "/cancel"}

# simple per-user AI cooldown (economic fuse)
import time as _time
_LAST_AI_CALL: dict[int, float] = {}
AI_COOLDOWN_SECONDS = 3.0


async def _ai_cooled_down(user_id: int) -> bool:
    from hermes_engine import get_dynamic_setting
    gap = float(await get_dynamic_setting("ai_cooldown_seconds",
                                          str(AI_COOLDOWN_SECONDS)))
    now = _time.monotonic()
    last = _LAST_AI_CALL.get(user_id, 0.0)
    if now - last < gap:
        return False
    _LAST_AI_CALL[user_id] = now
    return True


@router.callback_query(F.data == "ai_chat")
async def ai_chat_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    from database import mem_count
    mem_n = await mem_count(callback.from_user.id)

    from fleet import fleet_status_line
    fl = await fleet_status_line(callback.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 گپ با هرمسا", callback_data="ai_chat_start")],
        [InlineKeyboardButton(text="📄 سندساز حرفه‌ای", callback_data="doc_build"),
         InlineKeyboardButton(text="🎨 کاور AI", callback_data="img_cover")],
        [InlineKeyboardButton(text="📚 آموزش HTML", callback_data="ai_gen_tutorial")],
        [
            InlineKeyboardButton(text="📝 عنوان", callback_data="ai_gen_title"),
            InlineKeyboardButton(text="📋 توضیحات", callback_data="ai_gen_desc"),
        ],
        [
            InlineKeyboardButton(text="💡 ایده‌ها", callback_data="ai_ideas"),
            InlineKeyboardButton(text="🧹 گفتگوی تازه", callback_data="mem_clear"),
        ],
        [
            InlineKeyboardButton(text="🛰️ Fleet چیست؟", callback_data="fleet_info"),
            InlineKeyboardButton(text="🤖 بات شخصی", callback_data="custombot"),
        ],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await edit_safe(
        callback.message,
        f"💗 **هرمسا آنلاینه!** — حافظه: {mem_n} پیام\n{fl}\n\n"
        f"🎯 **چی بلده؟**\n"
        f"• گپ صمیمی زنده — مثل یه رفیق واقعی، تندتند جواب میده\n"
        f"• فایل برات می‌سازه (HTML، کد، آموزش...) و همینجا تحویلت میده 💌\n"
        f"• 🛰️ سؤال سنگین بدی، تیم ایجنت‌ها پاش میشه\n"
        f"• 📄 سندساز · 🎨 کاور AI · 📚 آموزش HTML\n\n"
        f"💳 هر پیام چت: ۱ کردیت",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "fleet_info")
async def fleet_info(callback: CallbackQuery):
    await edit_safe(callback.message, 
        "🛰️ **Hermes Fleet** — پشت این چت یک تیم است:\n\n"
        "🧭 **Atlas** رئیس ستاد — تشخیص می‌دهد سؤالت ساده یا چندلایه است\n"
        "🔎 **Cipher** شواهد از حافظه و مغز دوم جمع می‌کند\n"
        "♟️ **Vega** گزینه‌ها و سناریوها را می‌سنجد\n"
        "🔢 **Quant** با اعداد واقعی پلتفرم حساب می‌کند\n"
        "⚒️ **Forge** گام‌های عملی ساخت می‌دهد\n"
        "🛡️ **Rook** فرضیه‌ها را می‌کوبد (Red Team)\n"
        "🎭 **Muse** همه را به یک پاسخ خوانا تبدیل می‌کند\n"
        "📚 **Librarian** نتیجه ارزشمند را در مغز دوم ذخیره می‌کند\n\n"
        "💡 سؤال ساده بپرسی، خود هرمس مستقیم جواب می‌دهد.\n"
        "سؤال تحلیلی/استراتژیک بدهی، تیم زنجیره‌ای کار می‌کند و وضعیتش زنده می‌بینی!\n\n"
        "🧠 نتایج مهم به مغز دوم می‌رود و دفعه بعد در تحلیل‌ها استفاده می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 منوی هرمسا", callback_data="ai_chat")],
        ]),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "mem_clear")
async def mem_clear_session(callback: CallbackQuery, state: FSMContext):
    from database import mem_clear
    n = await mem_clear(callback.from_user.id)

    from database import raw_db
    try:
        async with raw_db() as db:
            await db.execute("DELETE FROM hermes_sessions WHERE user_id = ?",
                             (callback.from_user.id,))
    except Exception:
        pass

    await state.clear()
    await callback.answer(f"🧹 {n} پیام پاک شد — ذهن تازه!", show_alert=True)
    await ai_chat_menu(callback, state)


@router.callback_query(F.data == "ai_chat_start")
async def ai_chat_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.chatting)
    await edit_safe(
        callback.message,
        "💗 **هرمسا: سلام عزیزم! من هرمسام** 😊\n\n"
        "هر چی دلو می‌خواد ازم بپرس — گپ، ایده، کد، آموزش...\n"
        "اگه فایلی هم بخوای (HTML و...) برات می‌سازم و همینجا میدمش 💌\n\n"
        "_هر پیامت ۱ کردیت برده میشه_\n"
        "برای خروج /cancel بفرست.",
    )
    await callback.answer()


@router.message(AIChat.chatting)
async def process_chat(message: Message, state: FSMContext):
    if message.text and message.text.strip() in EXIT_COMMANDS:
        await state.clear()
        await message.answer("↩️ از چت خارج شدی. /start بزن.")
        return

    from database import mem_add
    from utils import ChatStream
    from hermes_engine import hermes_chat_stream, chat_custom, HermesEngineError
    from ai_agent import smart_messages

    if not await _ai_cooled_down(message.from_user.id):
        await message.answer("⏳ کمی آرام‌تر — چند ثانیه دیگر دوباره بفرست.")
        return

    ok, _rem = await _charge_ai_reply(message.from_user.id)
    if not ok:
        from hermes_engine import get_dynamic_setting
        cost = await _ai_chat_cost()
        await send_safe(
            message,
            f"💸 کردیتت برای چت کمه عزیزم! هر پیام {cost} کردیت هزینه داره 😔\n"
            f"یه تسک انجام بده یا واریز کن که برگیم سرِ گپ 💗",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ کسب کردیت رایگان", callback_data="tasks_menu"),
                 InlineKeyboardButton(text="💰 واریز", callback_data="dep_start")],
                [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
            ]),
        )
        return

    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("📝 در این حالت فقط متن بفرست (عکس/فایل اینجا پشتیبانی نمی‌شود).")
        await _refund_ai_reply(message.from_user.id, "empty message")
        return
    history = []  # context now built by smart_messages (compression+skills)

    msgs = await smart_messages(message.from_user.id,
                                AI_SYSTEM_PROMPT,
                                user_text)

    live = ChatStream(message.bot, message.chat.id)
    await live.start()

    async def _on_delta(acc):
        await live.on_delta(acc)

    # Custom Bot route keeps its own endpoint but same memory + streaming UX
    cb_record = None
    from database import get_custom_bot
    cb_record = await get_custom_bot(message.from_user.id)

    try:
        if cb_record and cb_record.get("active"):
            response = await chat_custom(
                user_text,
                AI_SYSTEM_PROMPT,
                cb_record["api_key"], cb_record["base_url"], cb_record["model"],
            )
            tag = "\n\n_از طریق بات شخصی تو_"
        else:
            # Fleet: Atlas decides direct vs team (only on platform engine)
            from database import get_setting
            fleet_on = (await get_setting("fleet_enabled", "1")) == "1"
            fleet_meta = None
            if fleet_on:
                from fleet import run_fleet, fleet_status_line

                async def _status(s):
                    await live.set_status(s)

                team_answer, fleet_meta = await run_fleet(user_text, message.from_user.id, _status)
                if fleet_meta.get("mode") == "team":
                    response = team_answer
                    saved = "\n📚 ذخیره شد در مغز دوم." if fleet_meta.get("saved") else ""
                    tag = f"\n\n🛰️ تیم: {' → '.join(fleet_meta.get('roles', []))}{saved}"

            if not fleet_meta or fleet_meta.get("mode") != "team":
                # Tool loop: agent's hands on real data (Atlas flagged it)
                if fleet_meta and fleet_meta.get("needs_tools"):
                    from tools import TOOL_SPECS, execute_tool
                    from hermes_engine import chat_with_tools

                    await live.set_status("⚒️ در حال استفاده از ابزارهای پلتفرم…")
                    try:
                        from memory import build_memory_context
                        _mem = await build_memory_context(message.from_user.id, user_text)
                    except Exception:
                        _mem = ""
                    try:
                        from skills import build_skills_prompt as _bsp
                        _skl = await _bsp(user_text)
                    except Exception:
                        _skl = ""
                    msgs_tools = [{"role": "system", "content":
                                   AI_SYSTEM_PROMPT + _mem + _skl +
                                   "\nاز ابزارها برای داده واقعی استفاده کن و پاسخ نهایی فارسی و خوانا بده."}]
                    msgs_tools.extend({"role": h["role"], "content": h["content"]} for h in history)
                    msgs_tools.append({"role": "user", "content": user_text})
                    response, used = await chat_with_tools(
                        msgs_tools, TOOL_SPECS,
                        lambda name, args: execute_tool(name, args, message.from_user.id),
                    )
                    tag = f"\n\n⚒️ ابزارها: {', '.join(used)}" if used else ""
                else:
                    response = await hermes_chat_stream(msgs, _on_delta)
                    tag = ""
        await mem_add(message.from_user.id, "user", user_text)
        await mem_add(message.from_user.id, "assistant", response)

        # long-term memory: periodic durable-fact extraction (fire-and-forget)
        from memory import schedule_extraction
        schedule_extraction(message.from_user.id, user_text, response)

        # v2.0.0: multi-faceted memory + identity RL signal (fire-and-forget, guarded)
        try:
            import memory2
            memory2.schedule_extraction(message.from_user.id, user_text, response)
        except Exception:
            pass
        try:
            from identity_rl import signal as rl_signal
            rl_signal(message.from_user.id, "chat_message")
        except Exception:
            pass
    except HermesEngineError as e:
        await _refund_ai_reply(message.from_user.id, "AI engine error")
        await live.fail(f"⚠️ {e}")
        return
    except Exception as e:  # noqa: BLE001 — never let a credit burn silently
        logger.exception("AI chat failed unexpectedly (uid=%s, model path)",
                         message.from_user.id)
        await _refund_ai_reply(message.from_user.id,
                               f"unexpected {type(e).__name__}")
        await live.fail("⚠️ یه خطای غیرمنتظره پیش اومد — کردیتت برگشت 💗 "
                        "چند لحظه دیگه دوباره امتحان کن.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ادامهٔ گپ", callback_data="ai_chat_continue")],
        [InlineKeyboardButton(text="🧹 گفتگوی تازه", callback_data="mem_clear"),
         InlineKeyboardButton(text="🔙 منو", callback_data="ai_chat")],
    ])
    cost = await _ai_chat_cost()
    tag_full = tag or ""
    if cost > 0 and not _is_admin_uid(message.from_user.id):
        pass  # charge already settled upstream; kept for future post-checks

    await live.finish(response, tag=tag_full, reply_markup=kb)

    # file delivery: Hermesa's code/HTML blocks arrive as real downloadable files
    await _deliver_generated_file(message.bot, message.chat.id,
                                  message.from_user.id, response)


@router.callback_query(F.data == "ai_chat_continue")
async def ai_chat_continue(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.chatting)
    await edit_safe(callback.message, "💬 **ادامه چت**\n\nسوالت رو بفرست:")
    await callback.answer()


@router.callback_query(F.data == "ai_gen_title")
async def ai_gen_title(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.generating_title)
    await edit_safe(
        callback.message,
        "📝 **ساخت عنوان جذاب**\n\n"
        "محصولت رو توصیف کن تا عنوان جذاب بسازم:\n\n"
        "مثال: 'آموزش HTML از صفر تا حرفه‌ای'\n\nبرای لغو /cancel بزن.",
    )
    await callback.answer()


@router.message(AIChat.generating_title)
async def process_gen_title(message: Message, state: FSMContext):
    if message.text and message.text.strip() in EXIT_COMMANDS:
        await state.clear()
        await message.answer("↩️ لغو شد. /start بزن.")
        return

    await message.answer("⏳ در حال ساخت عنوان...")

    title = await generate_product_title(message.text, user_key=message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بساز دوباره", callback_data="ai_gen_title")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
    ])
    await send_safe(message, f"📝 **عنوان پیشنهادی:**\n\n{title}", kb)


@router.callback_query(F.data == "ai_gen_desc")
async def ai_gen_desc(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.generating_description)
    await edit_safe(
        callback.message,
        "📋 **ساخت توضیحات حرفه‌ای**\n\n"
        "عنوان و دسته‌بندی محصول رو بده:\n\n"
        "مثال: `آموزش HTML, education`\n\nبرای لغو /cancel بزن.",
    )
    await callback.answer()


@router.message(AIChat.generating_description)
async def process_gen_desc(message: Message, state: FSMContext):
    if message.text and message.text.strip() in EXIT_COMMANDS:
        await state.clear()
        await message.answer("↩️ لغو شد. /start بزن.")
        return

    parts = message.text.split(",")
    title = parts[0].strip()
    category = parts[1].strip() if len(parts) > 1 else "general"

    await message.answer("⏳ در حال نوشتن توضیحات...")

    description = await generate_product_description(title, category, user_key=message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بساز دوباره", callback_data="ai_gen_desc")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
    ])
    await send_safe(message, f"📋 **توضیحات پیشنهادی:**\n\n{description}", kb)


@router.callback_query(F.data == "ai_gen_tutorial")
async def ai_gen_tutorial(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.generating_tutorial)
    await edit_safe(
        callback.message,
        "📚 **ساخت آموزش با هرمس**\n\n"
        "موضوع آموزش رو بنویس:\n\n"
        "مثال:\n"
        "• 'ساخت فرم تماس'\n"
        "• 'Responsive Layout'\n"
        "• 'CSS Grid'\n\n"
        "بعد از تولید، می‌تونی آموزش رو مستقیم به‌عنوان محصول ذخیره کنی!\n\n"
        "برای لغو /cancel بزن.",
    )
    await callback.answer()


@router.message(AIChat.generating_tutorial)
async def process_gen_tutorial(message: Message, state: FSMContext):
    if message.text and message.text.strip() in EXIT_COMMANDS:
        await state.clear()
        await message.answer("↩️ لغو شد. /start بزن.")
        return

    status = await message.answer("⏳ هرمس در حال نوشتن آموزش... (ممکنه تا چند دقیقه طول بکشه)")

    topic = message.text.strip()
    tutorial = await generate_html_tutorial(topic, user_key=message.from_user.id)

    await state.update_data(last_tutorial=tutorial, last_topic=topic)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 ذخیره به‌عنوان محصول", callback_data="ai_save_tutorial")],
        [InlineKeyboardButton(text="🔄 بساز دوباره", callback_data="ai_gen_tutorial")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
    ])

    try:
        await status.delete()
    except TelegramBadRequest:
        pass

    header = f"📚 **آموزش «{topic}» تولید شد:**\n\n"
    body_limit = 4096 - len(header) - 200
    if len(tutorial) > body_limit:
        chunks = [tutorial[i:i + 3800] for i in range(0, len(tutorial), 3800)]
        await send_safe(message, header + chunks[0])
        for chunk in chunks[1:]:
            await send_safe(message, chunk)
        await send_safe(
            message,
            "✅ آموزش کامل تولید شد! برای فروش به‌عنوان محصول، دکمه زیر:",
            kb,
        )
    else:
        await send_safe(message, header + tutorial, kb)


@router.callback_query(F.data == "ai_save_tutorial")
async def ai_save_tutorial(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("last_tutorial"):
        await callback.answer("اول یک آموزش تولید کن!", show_alert=True)
        return

    await state.set_state(TutorialSave.waiting_meta)
    await edit_safe(
        callback.message,
        "📦 **ذخیره آموزش به عنوان محصول**\n\n"
        "عنوان و قیمت رو به این فرمت بفرست:\n\n"
        "`عنوان | قیمت کردیت`\n\n"
        "مثال: `آموزش حرفه‌ای HTML | 150`\n\n"
        "💡 پیشنهاد قیمت: آموزش مبتدی ۵۰-۱۰۰ | حرفه‌ای ۱۰۰-۳۰۰\n\n"
        "برای لغو /cancel بزن.",
    )
    await callback.answer()


@router.message(TutorialSave.waiting_meta, F.text)
async def process_tutorial_save(message: Message, state: FSMContext):
    if message.text.strip() in EXIT_COMMANDS:
        await state.clear()
        await message.answer("↩️ لغو شد. /start بزن.")
        return

    parts = message.text.split("|")
    if len(parts) != 2:
        await message.answer("❌ فرمت اشتباهه! `عنوان | قیمت` بفرست.", parse_mode="Markdown")
        return

    title = parts[0].strip()
    try:
        price = int(parts[1].strip())
        if price < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ قیمت باید عدد صحیح مثبت باشه!")
        return

    data = await state.get_data()
    tutorial = data["last_tutorial"]
    topic = data.get("last_topic", title)

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    safe_name = "".join(c for c in topic[:30] if c.isalnum() or c in " -_").strip() or "tutorial"
    file_path = os.path.join(config.UPLOAD_DIR, f"{message.from_user.id}_tutorial_{int(time.time())}_{safe_name}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n{tutorial}")

    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO products (creator_id, title, description, price_credits,
                                     file_path, file_type, category, tags, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                message.from_user.id,
                title,
                f"آموزش تولیدشده توسط Hermes AI — موضوع: {topic}",
                price,
                file_path,
                "text/markdown",
                "education",
                f"{topic}, آموزش, AI, Hermes",
            ),
        )
        product_id = cursor.lastrowid
        await db.commit()

    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Marketplace", callback_data="mp_latest")],
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products")],
    ])

    await send_safe(
        message,
        f"🎉 **محصول ساخته شد** 🛡️\n\n"
        f"📖 {title}\n"
        f"💰 قیمت: {price} کردیت\n"
        f"📄 فایل: {os.path.basename(file_path)}\n\n"
        f"⏳ در انتظار تأیید ادمین برای انتشار در مارکت.",
        kb,
    )

    from handlers.admin import notify_admins
    akb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید", callback_data=f"adm_appr_{product_id}"),
            InlineKeyboardButton(text="❌ رد", callback_data=f"adm_rej_{product_id}"),
        ],
    ])
    await notify_admins(
        message.bot,
        f"🆕 **محصول AI جدید در انتظار تأیید**\n\n"
        f"📌 {title}\n💰 {price} کردیت\n👤 @{message.from_user.username or message.from_user.id}",
        akb,
    )


@router.callback_query(F.data == "ai_ideas")
async def ai_ideas(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.chatting)
    await edit_safe(
        callback.message,
        "💡 **ایده‌پردازی برای محصول**\n\n"
        "زمینه یا علاقه‌مندی‌ات رو بگو تا ایده بدم:\n\n"
        "مثال:\n"
        "• 'می‌خوام چیزی در زمینه برنامه‌نویسی بسازم'\n"
        "• 'به طراحی علاقه دارم'\n"
        "• 'دنبال ایده آموزشی هستم'",
    )
    await callback.answer()


# ================= Custom BOT (user's own API — FREE) =================

@router.callback_query(F.data == "custombot")
async def custombot_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from database import get_custom_bot
    rec = await get_custom_bot(callback.from_user.id)

    if not rec or not rec.get("api_key"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ تنظیم API شخصی", callback_data="cb_setup")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
        ])
        await edit_safe(
            callback.message,
            "🤖 **بات شخصی** — هوش مصنوعی مخصوص خودت! **رایگان** 💚\n\n"
            "با API سازگار با OpenAI خودت، داخل همین چت از مدل دلخواهت استفاده کن:\n"
            "• کلید API خودت (OpenAI / Groq / OpenRouter / سرور شخصی...)\n"
            "• Endpoint + مدل دلخواه\n\n"
            f"💚 کاملاً رایگان — بدون هزینهٔ lifetime!\n"
            f"🔓 هر وقت بخوای فعال/غیرفعال کن.",
            kb,
        )
        await callback.answer()
        return

    status = "🟢 فعال" if rec["active"] else "🔴 غیرفعال"
    masked = rec["api_key"][:6] + "…" + rec["api_key"][-4:] if len(rec["api_key"]) > 14 else "***"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 خاموش/روشن", callback_data="cb_toggle"),
         InlineKeyboardButton(text="✏️ تغییر تنظیمات", callback_data="cb_cfg")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
    ])
    await edit_safe(
        callback.message,
        f"🤖 **بات شخصی** {status} 💚\n\n"
        f"🌐 `{rec['base_url']}`\n🧠 `{rec['model']}`\n🔑 `{masked}`\n\n"
        f"وقتی فعاله، «💬 گپ با هرمسا» از API خودِ تو استفاده می‌کنه!",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "cb_setup")
async def cb_setup(callback: CallbackQuery):
    CustomBotStateBridge.pending[callback.from_user.id] = True
    await edit_safe(
        callback.message,
        "🎉 عالی! تنظیمات API خودتو بفرست:\n\n"
        "`KEY | ENDPOINT | MODEL`\n\n"
        "مثال:\n`sk-xxx | https://openrouter.ai/api/v1 | meta-llama/llama-3-8b-instruct:free`\n\n"
        "💡 OpenRouter مدل‌های free داره (`:free` پسوند)\nلغو: /cancel",
        parse_mode="Markdown",
    )
    await callback.answer("حالا کلید و آدرس را بفرست")

class CustomBotStateBridge:
    pending = {}


@router.callback_query(F.data == "cb_cfg")
async def cb_cfg_start(callback: CallbackQuery):
    CustomBotStateBridge.pending[callback.from_user.id] = True
    await edit_safe(callback.message, 
        "`KEY | ENDPOINT | MODEL` رو بفرست:\n\n"
        "مثال: `sk-xxx | https://api.groq.com/openai/v1 | llama-3.3-70b`",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "cb_toggle")
async def cb_toggle(callback: CallbackQuery):
    from database import get_custom_bot, set_custom_bot_active
    rec = await get_custom_bot(callback.from_user.id)
    if not rec:
        await callback.answer("اول تنظیم کن!", show_alert=True)
        return
    new_state = not bool(rec["active"])
    await set_custom_bot_active(callback.from_user.id, new_state)
    await callback.answer("فعال شد 🟢" if new_state else "خاموش شد 🔴", show_alert=True)
    await custombot_menu(callback, _NullState())


class _NullState:
    async def clear(self):
        pass


@router.message(lambda m: CustomBotStateBridge.pending.get(m.from_user.id))
async def cb_config_input(message: Message):
    CustomBotStateBridge.pending.pop(message.from_user.id, None)
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) != 3:
        await send_safe(message, "❌ فرمت: `KEY | ENDPOINT | MODEL`")
        return
    key, url, model = parts
    if not key or not url.startswith("http"):
        await send_safe(message, "❌ KEY و ENDPOINT معتبر نیستن.")
        return

    from database import upsert_custom_bot
    await upsert_custom_bot(message.from_user.id, key, url.rstrip("/"), model, active=1)

    # quick sanity test
    test_msg = await message.answer("⏳ تست اتصال...")
    from hermes_engine import chat_custom
    resp = await chat_custom("ping — فقط بگو ok", None, key, url.rstrip("/"), model)
    ok = not resp.startswith("⚠️")
    try:
        await test_msg.edit_text(("✅ اتصال برقراره!\n\n" + resp[:300]) if ok else resp[:400], parse_mode=None)
    except Exception:
        pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 گپ با بات شخصی‌ام", callback_data="ai_chat_start")],
        [InlineKeyboardButton(text="⚙️ پنل بات شخصی", callback_data="custombot")],
    ])
    await send_safe(message, "🤖 بات شخصی ذخیره و فعال شد!" if ok else "ذخیره شد ولی تست ناموفق بود.", kb)


# ================= Document Builder (Hermes file-tools style) =================

DOC_FORMATS = {"md": ("📝 Markdown", ".md"), "html": ("🌐 HTML", ".html"), "txt": ("📄 Plain", ".txt")}


@router.callback_query(F.data == "doc_build")
async def doc_build_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DocBuild.waiting_topic)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 MD", callback_data="docfmt_md"),
            InlineKeyboardButton(text="🌐 HTML", callback_data="docfmt_html"),
            InlineKeyboardButton(text="📄 TXT", callback_data="docfmt_txt"),
        ],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")],
    ])
    await edit_safe(
        callback.message,
        "📄 **Document Builder** — سازندهٔ اسناد حرفه‌ای هرمس\n\n"
        "۱) موضوع سند رو بنویس\n"
        "۲) فرمت رو انتخاب کن (پیش‌فرض: Markdown)\n\n"
        f"خروجی همیشه ساختارمند: عنوان، TL;DR، بخش‌ها، کد واقعی، چک‌لیست.\n\nلغو: /cancel",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("docfmt_"))
async def doc_fmt_pick(callback: CallbackQuery, state: FSMContext):
    fmt = callback.data.split("_")[1]
    if fmt not in DOC_FORMATS:
        await callback.answer("فرمت نامعتبر", show_alert=True)
        return
    await state.update_data(doc_fmt=fmt)
    await callback.answer(f"فرمت: {DOC_FORMATS[fmt][0]} ✅")


@router.message(DocBuild.waiting_topic, F.text & ~F.text.startswith("/"))
async def doc_topic(message: Message, state: FSMContext):
    await state.update_data(doc_topic=message.text.strip())
    await state.set_state(None)

    from ai_agent import generate_document
    from utils import LiveEditor
    from database import mem_add
    import os
    import time

    data = await state.get_data()
    fmt = data.get("doc_fmt", "md")
    topic = data["doc_topic"]
    ext = DOC_FORMATS[fmt][1]

    live = LiveEditor(message.bot, message.chat.id, "⏳ هرمس در حال نوشتن سند…")
    await live.start()

    async def _cb(acc):
        await live.on_delta(acc)

    doc = await generate_document(topic, fmt=fmt, user_key=message.from_user.id)
    await mem_add(message.from_user.id, "assistant", doc[:3000])

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    safe_name = "".join(c for c in topic[:32] if c.isalnum() or c in " -_").strip() or "document"
    path = os.path.join(config.UPLOAD_DIR, f"{message.from_user.id}_doc_{int(time.time())}{ext}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)

    await state.update_data(last_tutorial=doc, last_topic=topic, doc_path=path, doc_fmt=fmt)

    await live.finish(
        f"✅ **سند آماده شد:** {topic}\n"
        f"📊 {len(doc):,} کاراکتر | فرمت {DOC_FORMATS[fmt][0]}\n\n"
        f"{doc[:1200]}…",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 ذخیره به‌عنوان محصول", callback_data="ai_save_tutorial")],
            [InlineKeyboardButton(text="🔄 دوباره", callback_data="doc_build")],
            [InlineKeyboardButton(text="🔙 منو", callback_data="ai_chat")],
        ]),
    )


# ================= Voice (STT→chat) / TTS / Cover AI / Search =================

@router.message(F.voice)
async def voice_in(message: Message, state: FSMContext):
    """Voice message → transcribe → same Hermes pipeline."""
    from hermes_engine import get_dynamic_setting
    if (await get_dynamic_setting("stt_enabled", "0")) != "1":
        await send_safe(message, "🎙 پیام صوتی گرفتم ولی STT فعال نیست.\nادمین می‌تواند با `/set stt_enabled 1` فعال کند.")
        return

    status = await message.answer("🎙 در حال شنیدن…")
    import tempfile, os as _os
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    await message.bot.download(message.voice, destination=tmp.name)

    try:
        from media_ai import speech_to_text
        text = await speech_to_text(tmp.name)
    except Exception as e:
        await status.edit_text(f"⚠️ تبدیل صوت ناموفق: {str(e)[:150]}")
        return
    finally:
        try:
            _os.remove(tmp.name)
        except OSError:
            pass
    try:
        await status.delete()
    except Exception:
        pass

    if not text:
        await message.answer("🎙 صدای واضحی نشنیدم؛ دوباره بگو.")
        return
    await send_safe(message, f"👂 شنیدم: «{text}»")
    # route through the same chat brain by injecting a text-message clone
    message.text = text
    await process_chat(message, state)


@router.message(F.text.startswith("/tts"))
async def tts_cmd(message: Message):
    from hermes_engine import get_dynamic_setting
    if (await get_dynamic_setting("tts_enabled", "0")) != "1":
        await message.answer("🔇 TTS غیرفعال است — ادمین: `/set tts_enabled 1`")
        return
    text = (message.text or "").split(maxsplit=1)
    body = text[1].strip() if len(text) > 1 else ""
    if not body:
        await message.answer("متن را هم بده: `/tts سلام دنیا`", parse_mode="Markdown")
        return
    m = await message.answer("🔊 در حال ساختن صدا…")
    try:
        from media_ai import text_to_speech
        path = await text_to_speech(body[:1000])
    except Exception as e:
        await m.edit_text(f"⚠️ {str(e)[:200]}")
        return
    from aiogram.types import FSInputFile
    await m.delete()
    await message.answer_voice(FSInputFile(path), caption="🔊")


class CoverFlow(StatesGroup):
    waiting_prompt = State()


@router.callback_query(F.data == "img_cover")
async def cover_start(callback: CallbackQuery, state: FSMContext):
    from hermes_engine import get_dynamic_setting
    if (await get_dynamic_setting("img_enabled", "1")) != "1":
        await callback.answer("تولید تصویر غیرفعال است.", show_alert=True)
        return
    await state.set_state(CoverFlow.waiting_prompt)
    await edit_safe(callback.message,
                    "🎨 **کاور محصول با AI**\n\nتوصیف کاور موردنظرت رو بنویس:\n\n"
                    "مثال: `کاور مینیمال برای آموزش HTML، پس‌زمینه سرمه‌ای، لپ‌تاپ طلایی`\n\nلغو: /cancel",
                    InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 برگشت", callback_data="ai_chat")]]))
    await callback.answer()


@router.message(CoverFlow.waiting_prompt, F.text & ~F.text.startswith("/"))
async def cover_gen(message: Message, state: FSMContext):
    await state.set_state(None)
    status = await message.answer("🎨 هرمس نقاشی می‌کند… (تا ۶۰ ثانیه)")
    try:
        from media_v2 import generate_image
        path = await generate_image(message.text.strip())
    except Exception as e:
        await status.edit_text(f"⚠️ {str(e)[:200]}")
        return
    from aiogram.types import FSInputFile
    await status.delete()
    from database import get_my_products
    prods = await get_my_products(message.from_user.id)[:8]
    rows = [[InlineKeyboardButton(text=f"🖼 {p['title'][:28]}",
                                  callback_data=f"cpick_{p['id']}")]
            for p in prods]
    rows.append([InlineKeyboardButton(text="🔙 منوی هرمسا", callback_data="ai_chat")])
    await state.update_data(last_cover=path)
    caption_extra = ("\n\n👇 انتخاب کن کدام محصول این کاور را بگیرد:"
                     if prods else "\n\n(محصولی نداری؛ بعداً از ویرایش محصول وصل کن)")
    await message.answer_photo(FSInputFile(path),
                               caption=f"🎨 کاور آماده شد.{caption_extra}",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


_PENDING_COVER: dict[int, str] = {}


@router.callback_query(F.data.startswith("cpick_"))
async def cover_pick(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    data = await state.get_data()
    path = data.get("last_cover")
    if not path or not os.path.exists(path):
        await callback.answer("کاور منقضی شده.", show_alert=True)
        return
    from database import update_product_field, get_product
    prod = await get_product(pid)
    if not prod or prod["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری!", show_alert=True)
        return
    await update_product_field(pid, "photo_path", path)
    await callback.answer(f"✅ کاور به «{prod['title'][:24]}» وصل شد!", show_alert=True)


@router.message(F.text.startswith("/search "))
async def history_search_cmd(message: Message):
    q = (message.text or "").split(maxsplit=1)
    query = q[1].strip() if len(q) > 1 else ""
    if not query:
        await message.answer("`/search <کلمه کلیدی>`", parse_mode="Markdown")
        return
    from database import history_search
    rows = await history_search(message.from_user.id, query, 8)
    if not rows:
        await message.answer(f"چیزی دربارهٔ «{query}» در تاریخچه‌ات نیست.")
        return
    lines = [f"• [{r['role']}] {r['content'][:110]}" for r in rows]
    await send_safe(message, f"🗂 **نتایج تاریخچه:**\n\n" + "\n".join(lines))


# ---- skills admin commands ----
from aiogram.fsm.state import State as _St, StatesGroup as _SG


class SkillAdd(_SG):
    waiting_content = _St()


_SKILL_PENDING_NAME = {}


@router.message(F.text.startswith("/skill_add"))
async def skill_add_cmd(message: Message, state: FSMContext):
    from handlers.admin import is_admin
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("`/skill_add <name>` بعدش محتوا را بفرست.", parse_mode="Markdown")
        return
    name = parts[1].strip()
    from skills import skill_path
    if not skill_path(name):
        await message.answer("❌ نام نامعتبر (a-z0-9_- ، ۲ تا ۲۴ کاراکتر).")
        return
    _SKILL_PENDING_NAME[message.from_user.id] = name
    await message.answer(f"📝 محتوای Skill «{name}» را بفرست (Markdown آزاد):")


@router.message(lambda m: _SKILL_PENDING_NAME.get(m.from_user.id))
async def skill_content_in(message: Message):
    name = _SKILL_PENDING_NAME.pop(message.from_user.id)
    from skills import skill_add
    ok = skill_add(name, message.text or "")
    await message.answer(f"{'✅ نصب شد' if ok else '❌ خطا'}: {name}")


@router.message(F.text.startswith("/skill_del"))
async def skill_del_cmd(message: Message):
    from handlers.admin import is_admin
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("`/skill_del <name>`", parse_mode="Markdown")
        return
    from skills import skill_del
    await message.answer("🗑 حذف شد." if skill_del(parts[1].strip()) else "پیدا نشد.")


@router.message(F.text == "/skills")
async def skills_list_cmd(message: Message):
    from skills import skill_list
    rows = skill_list()
    if not rows:
        await message.answer("هیچ مهارتی نصب نیست. ادمین: `/skill_add <name>`")
        return
    await send_safe(message, "🧩 **مهارت‌های نصب‌شده:**\n" +
                    "\n".join(f"• {n} ({s//1024}KB)" for n, s in rows))
