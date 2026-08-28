import html
import os
import time

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, FSInputFile

from config import config as cfg
from database import get_content, save_content
from utils import send_safe, edit_safe

router = Router()


class EditContent(StatesGroup):
    waiting_body = State()


def is_admin(user_id: int) -> bool:
    return user_id in cfg.ADMIN_IDS


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 راهنما", callback_data="help_show"),
            InlineKeyboardButton(text="📜 قوانین", callback_data="help_rules"),
        ],
        [InlineKeyboardButton(text="📄 دریافت فایل کامل (HTML)", callback_data="help_html")],
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="main_menu")],
    ])


HELP_WELCOME = (
    "❓ **مرکز راهنمایی DropAgentX**\n\n"
    "هر چیزی که برای شروع لازم داری اینجاست:\n\n"
    "📖 **راهنما** — قدم‌به‌قدم استفاده از پلتفرم\n"
    "📜 **قوانین** — چارچوب طلایی بازی\n"
    "📄 **فایل کامل** — راهنما + قوانین در یک HTML زیبا، ارسال خودکار به تو"
)


@router.message(F.text.startswith("/help"))
async def cmd_help(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(HELP_WELCOME, reply_markup=_menu_kb(), parse_mode="Markdown")


@router.callback_query(F.data == "help_menu")
async def help_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await edit_safe(callback.message, HELP_WELCOME, _menu_kb())
    await callback.answer()


@router.callback_query(F.data == "help_show")
async def help_show(callback: CallbackQuery):
    page = await get_content("help")
    body = page["body"] if page else "راهنما هنوز تنظیم نشده."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 فایل کامل", callback_data="help_html"),
         InlineKeyboardButton(text="📜 قوانین", callback_data="help_rules")],
        [InlineKeyboardButton(text="🔙 Help", callback_data="help_menu")],
    ])
    await edit_safe(callback.message, body, kb)
    await callback.answer()


@router.callback_query(F.data == "help_rules")
async def rules_show(callback: CallbackQuery):
    page = await get_content("rules")
    body = page["body"] if page else "قوانین هنوز تنظیم نشده."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 فایل کامل", callback_data="help_html"),
         InlineKeyboardButton(text="📖 راهنما", callback_data="help_show")],
        [InlineKeyboardButton(text="🔙 Help", callback_data="help_menu")],
    ])
    await edit_safe(callback.message, body, kb)
    await callback.answer()


# ---------------- Beautiful HTML export ----------------

_ROLE_GUIDE = {
    "associate": ("🎓 کارآموز", "با تسک کردیت بگیر، با AI محصول بساز و اولین فروشت را ثبت کن تا سرباز شوی."),
    "soldier": ("🪖 سرباز", "فروشگاهت مال خودت است! از «👑 قلمرو» کد تخفیف بساز و بازار خودت را گرم کن."),
    "capo": ("🕴️ کاپو", "تیمت مال توست: ۵٪ اوورراید از فروش فروشنده‌های زیرمجموعه + داشبورد تیم در «👑 قلمرو»."),
    "underboss": ("👔 آندرباس", "حوزه تو یک دسته‌ی کامل است: داشبورد درآمد، فیچر و مدیریت محصولات حوزه در «👑 قلمرو»."),
    "godfather": ("👑 Godfather", "مالک کل پلتفرم: انتصاب رتبه‌ها (/setrole)، مدیریت محتوا (/editcontent)، تأیید مالی، پنل /admin."),
}

_COMMANDS = [
    ("/start", "منوی اصلی و ثبت‌نام"),
    ("/help", "همین مرکز راهنما"),
    ("/cancel", "لغو عملیات جاری"),
    ("/admin", "پنل مدیریت (فقط Godfather)"),
    ("/addcredits id amount", "شارژ کردیت کاربر (ادمین)"),
    ("/setrole id role [cat]", "انتصاب رتبه (ادمین)"),
    ("/editcontent help|rules", "ویرایش متن راهنما/قوانین (ادمین)"),
]

_ECONOMY = [
    ("۱۰۰۰ کردیت = ۱ USDT", "نرخ ثابت تبدیل داخلی"),
    ("کمیسیون فروش", f"{int(cfg.COMMISSION_RATE*100)}٪ سهم پلتفرم از هر معامله"),
    ("واریز", "USDT روی TON / BSC-BASE / SOL / TRX با تأیید ادمین"),
    ("برداشت", "حداقل ۵ USDT؛ کارمزد شبکه از مبلغ کسر می‌شود"),
    ("ریفرال", "۵–۲۰ کردیت جعبه شانس فوری + ۷۵ کردیت پس از فعالیت نفر + ۲۰٪ کمیسیون مادام‌العمر"),
]


def render_full_html(help_body: str, rules_body: str, role: str, bot_username: str) -> str:
    e = html.escape
    role_fa, role_tip = _ROLE_GUIDE.get(role, _ROLE_GUIDE["associate"])
    nl2br = lambda s: "<br>".join(e(line) for line in (s or "").splitlines())

    cmds = "".join(
        f'<tr><td class="cmd">{e(c)}</td><td>{e(d)}</td></tr>' for c, d in _COMMANDS
    )
    econ = "".join(f"<tr><td class='k'>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in _ECONOMY)
    ranks = "".join(
        f"<div class='rank'><b>{e(rf)}</b> — {e(tip)}</div>"
        for rf, tip in _ROLE_GUIDE.values()
    )

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DropAgentX — راهنمای کامل</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Segoe UI", Tahoma, sans-serif;
    background: #0d1117; color: #e6edf3; line-height: 1.9;
  }}
  .hero {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #b8860b33 100%);
    padding: 48px 24px; text-align: center;
    border-bottom: 2px solid #d4af37;
  }}
  .hero h1 {{ font-size: 2rem; color: #ffd700; text-shadow: 0 0 24px #d4af3766; }}
  .hero p {{ color: #9aa4b2; margin-top: 8px; }}
  .wrap {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 64px; }}
  .card {{
    background: #161b22; border: 1px solid #21262d; border-radius: 14px;
    padding: 26px 28px; margin-bottom: 22px;
    box-shadow: 0 4px 18px #00000055;
  }}
  .card h2 {{
    color: #ffd700; font-size: 1.25rem; margin-bottom: 14px;
    border-right: 4px solid #d4af37; padding-right: 12px;
  }}
  pre.body {{
    white-space: pre-wrap; font-family: inherit;
    background: #0d1117; border-radius: 10px; padding: 16px 18px;
    border: 1px solid #21262d; color: #c9d1d9;
  }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #21262d; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  td.k {{ color: #ffd700; white-space: nowrap; font-weight: 600; }}
  td.cmd {{ direction: ltr; text-align: left; color: #7ee787; font-family: Consolas, monospace; }}
  .rank {{
    background: #0d1117; border: 1px solid #30363d; border-radius: 10px;
    padding: 10px 14px; margin: 8px 0;
  }}
  .badge {{
    display: inline-block; background: #d4af3722; color: #ffd700;
    border: 1px solid #d4af37; border-radius: 999px;
    padding: 4px 16px; margin-bottom: 12px; font-weight: bold;
  }}
  footer {{
    text-align: center; color: #6e7681; font-size: .85rem; padding: 24px;
    border-top: 1px solid #21262d;
  }}
  a {{ color: #58a6ff; text-decoration: none; }}
</style>
</head>
<body>
  <div class="hero">
    <h1>🤖🛒 DropAgentX</h1>
    <p>مارکت‌پلیس محصولات دیجیتال مجهز به ایجنت هوش مصنوعی — راهنمای رسمی و قوانین</p>
  </div>
  <div class="wrap">

    <div class="card">
      <span class="badge">رتبه فعلی شما: {e(role_fa)}</span>
      <p>{e(role_tip)}</p>
    </div>

    <div class="card"><h2>📖 راهنمای پلتفرم</h2><pre class="body">{nl2br(help_body)}</pre></div>

    <div class="card"><h2>📜 قوانین پلتفرم</h2><pre class="body">{nl2br(rules_body)}</pre></div>

    <div class="card"><h2>⌨️ دستورات ربات</h2>
      <table>{cmds}</table>
    </div>

    <div class="card"><h2>💱 اقتصاد و کردیت</h2>
      <table>{econ}</table>
    </div>

    <div class="card"><h2>👑 سطوح و قلمروها (ساختار فرکتالی)</h2>{ranks}</div>

  </div>
  <footer>
    تولید خودکار توسط ربات @{e(bot_username)} · {time.strftime("%Y-%m-%d %H:%M")}
  </footer>
</body>
</html>"""


@router.callback_query(F.data == "help_html")
async def send_full_html(callback: CallbackQuery):
    from handlers.org import effective_role
    help_page = await get_content("help")
    rules_page = await get_content("rules")
    role = await effective_role(callback.from_user.id)
    me = await callback.bot.me()

    doc = render_full_html(
        help_page["body"] if help_page else "",
        rules_page["body"] if rules_page else "",
        role,
        me.username or "BaseMarketEmpireBot",
    )

    os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(cfg.UPLOAD_DIR, f"HermesGuide_{int(time.time())}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)

    await callback.message.answer_document(
        FSInputFile(path),
        caption="📄 **راهنمای کامل + قوانین**\nاین فایل را ذخیره کن — همه‌چیز داخلش هست!",
        parse_mode="Markdown",
    )
    try:
        os.remove(path)
    except OSError:
        pass
    await callback.answer("فایل آماده شد! 📄")


# ---------------- Admin editing ----------------

@router.message(F.text.startswith("/editcontent"))
async def edit_content_cmd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    key = parts[1].strip().lower() if len(parts) > 1 else ""
    if key not in ("help", "rules"):
        await message.answer(
            "📝 **ویرایش محتوا**\n\n"
            "`/editcontent help` — ویرایش راهنما\n"
            "`/editcontent rules` — ویرایش قوانین\n\n"
            "بعدش متن جدید رو بفرست (متن خام، بدون Markdown اجباری).",
            parse_mode="Markdown",
        )
        return

    page = await get_content(key)
    current = (page or {}).get("body", "")
    await state.set_state(EditContent.waiting_body)
    await state.update_data(edit_key=key)
    preview = current[:800] + ("\n…" if len(current) > 800 else "")
    await message.answer(
        f"📝 ویرایش «{'راهنما' if key=='help' else 'قوانین'}»\n\n"
        f"**متن فعلی:**\n{preview}\n\n"
        f"✍️ حالا متن کامل جدید رو بفرست.\nلغو: /cancel",
        parse_mode=None,
    )


@router.message(EditContent.waiting_body)
async def edit_content_save(message: Message, state: FSMContext):
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("↩️ لغو شد.")
        return
    if not message.text:
        await message.answer("❌ فقط متن.")
        return

    data = await state.get_data()
    key = data.get("edit_key")
    if key not in ("help", "rules"):
        await state.clear()
        return

    ok = await save_content(key, message.text.strip(), message.from_user.id)
    await state.clear()
    if ok:
        await message.answer(
            f"✅ «{'راهنما' if key=='help' else 'قوانین'}» آپدیت شد!\n"
            f"از همین لحظه در /help و فایل HTML نسخه جدید ارائه می‌شه.",
        )
