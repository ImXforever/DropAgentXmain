import re

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

from config import config
from database import (
    get_user, get_db, usdt_to_credits,
    create_deposit, create_withdrawal,
    list_user_deposits, list_user_withdrawals, update_credits,
)
from utils import get_or_create_user,  send_safe, edit_safe

router = Router()

NETWORKS = {
    "ton": ("TON", "💠 TON (USDT TRC20-like jetton)"),
    "bsc": ("BSC/BASE", "🟡 BSC or BASE (USDT ERC20/EVM)"),
    "sol": ("SOL", "🌞 Solana (USDT SPL)"),
    "trx": ("TRX", "🔴 Tron (USDT TRC20)"),
}


class DepositFlow(StatesGroup):
    waiting_amount = State()
    waiting_txid = State()


class WithdrawFlow(StatesGroup):
    waiting_address = State()
    waiting_amount = State()


async def dynf(key: str, fallback: float) -> float:
    from hermes_engine import get_dynamic_setting
    try:
        return float(await get_dynamic_setting(key, str(fallback)))
    except Exception:
        return fallback


def _fmt_usdt(x: float) -> str:
    return f"{x:g}"


def wallet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 واریز USDT", callback_data="dep_start"),
            InlineKeyboardButton(text="📤 برداشت USDT", callback_data="wd_start"),
        ],
        [InlineKeyboardButton(text="📜 تاریخچه واریز/برداشت", callback_data="wh_history")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])


@router.callback_query(F.data == "wallet")
async def wallet_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    credits = user["credits"]
    usdt_eq = credits / config.CREDITS_PER_USDT

    wd_min = await dynf("withdraw_min_usdt", config.WITHDRAW_MIN_USDT)
    # 4-A: first withdrawal = 60% of standard threshold (trust builder)
    from database import get_db
    async with get_db() as db:
        cur = await db.execute(
            "SELECT has_withdrawn FROM users WHERE user_id=?", (callback.from_user.id,))
        row = await cur.fetchone()
        has_withdrawn = bool(row and row[0])
    if not has_withdrawn:
        wd_min = round(wd_min * 0.6, 1)   # $3 instead of $5
    wd_goal_credits = int(wd_min * config.CREDITS_PER_USDT)

    if credits >= wd_goal_credits:
        progress_line = "💸 آمادهٔ برداختی! 🎉"
    else:
        remain = wd_goal_credits - credits
        pct = min(100, int(credits * 100 / max(1, wd_goal_credits)))
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        celebrate = " 🔥" if pct >= 70 else ""
        first_hint = " (اولین برداشت تخفیف داره!)" if not has_withdrawn else ""
        progress_line = (
            f"🎯 تا برداشت ({_fmt_usdt(wd_min)}$): {bar} {pct}%{celebrate}\n"
            f"   فقط {remain:,} کردیت مونده 💪{first_hint}"
        )

    await edit_safe(
        callback.message,
        f"💰 **کیف پول تو**\n\n"
        f"💳 موجودی: **{credits:,} کردیت** ≈ **{_fmt_usdt(usdt_eq)} USDT**\n"
        f"📈 کل درآمدت تا حالا: {user['total_earned']:,} کردیت\n\n"
        f"{progress_line}\n\n"
        f"💱 نرخ ثابت و شفاف: `۱٬۰۰۰ کردیت = ۱ USDT` — بدون تغییر ناگهانی\n\n"
        f"⏱ واریزها معمولاً ظرف **چند ساعت** تأیید و شارژ می‌شن.\n"
        f"🔒 پولت امنه — ما فقط واسطه‌ایم، پلتفرم بانک نیست.",
        wallet_kb(),
    )
    await callback.answer()


# ---------------- Deposit (3-step wizard) ----------------
# Step 1: network + amount → Step 2: address + Done button → Step 3: TXID

@router.callback_query(F.data == "dep_start")
async def dep_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = [[InlineKeyboardButton(text=f"{NETWORKS[k][0]}", callback_data=f"dep_net_{k}")]
            for k in NETWORKS]
    rows.append([InlineKeyboardButton(text="🔙 Wallet", callback_data="wallet")])
    await edit_safe(
        callback.message,
        "📥 **واریز USDT — مرحله ۱ از ۳**\n\nشبکه واریز رو انتخاب کن:",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dep_net_"))
async def dep_network(callback: CallbackQuery, state: FSMContext):
    net = callback.data.split("_")[2]
    if net not in config.DEPOSIT_WALLETS or not config.DEPOSIT_WALLETS[net]:
        await callback.answer("این شبکه فعال نیست!", show_alert=True)
        return

    await state.set_state(DepositFlow.waiting_amount)
    await state.update_data(dep_network=net)
    fee_note = ""
    await edit_safe(
        callback.message,
        f"📥 **واریز — شبکه {NETWORKS[net][0]}**\n"
        f"**مرحله ۱:** چند USDT می‌خوای واریز کنی؟ (فقط عدد)\n\n"
        f"حداقل: **{_fmt_usdt(config.DEPOSIT_MIN_USDT)} USDT**\n"
        f"{fee_note}لغو: /cancel",
    )
    await callback.answer()


@router.message(DepositFlow.waiting_amount)
async def dep_amount(message: Message, state: FSMContext):
    raw = (message.text or "").strip().replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", raw):
        await send_safe(message, "❌ فقط عدد بفرست. مثال: `10` یا `25.5`")
        return

    amount = float(raw)
    dep_min = await dynf("deposit_min_usdt", config.DEPOSIT_MIN_USDT)
    if amount < dep_min:
        await send_safe(message, f"❌ حداقل واریز {_fmt_usdt(dep_min)} USDT هست.")
        return

    data = await state.get_data()
    net = data.get("dep_network")
    if not net or not config.DEPOSIT_WALLETS.get(net):
        await state.clear()
        await send_safe(message, "↩️ نشست منقضی شد. دوباره از کیف پول شروع کن.")
        return

    address = config.DEPOSIT_WALLETS[net]
    credits = usdt_to_credits(amount)

    # Step 2: show address + Done button (amount kept in FSM)
    await state.set_state(None)
    await state.update_data(dep_amount=amount)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پرداخت کردم — ادامه", callback_data=f"dep_done_{net}")],
        [InlineKeyboardButton(text="🔙 تغییر شبکه", callback_data="dep_start")],
    ])
    await send_safe(
        message,
        f"📥 **واریز — مرحله ۲ از ۳**\n\n"
        f"💠 شبکه: {NETWORKS[net][0]}\n"
        f"💵 مبلغ تو: **{_fmt_usdt(amount)} USDT**  → معادل `{credits:,} کردیت (≈{_fmt_usdt(amount)}$)`\n\n"
        f"📍 آدرس مقصد (کپی کن):\n`{address}`\n\n"
        f"⚠️ **دقیقاً روی شبکه {NETWORKS[net][0]} بفرست؛** شبکهٔ اشتباه = از دست رفتن پول!\n"
        f"💡 بعد از ارسال، دکمهٔ «✅ پرداخت کردم» رو بزن تا مرحلهٔ آخر.",
        kb,
    )


@router.callback_query(F.data.startswith("dep_done_"))
async def dep_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("dep_amount")
    if not amount:
        await callback.answer("اول مبلغ رو ثبت کن!", show_alert=True)
        return

    await state.set_state(DepositFlow.waiting_txid)
    await edit_safe(
        callback.message,
        f"📥 **واریز — مرحله ۳ از ۳** ✅\n\n"
        f"💵 مبلغ ثبت‌شده: **{_fmt_usdt(amount)} USDT**\n\n"
        f"🔖 حالا **TXID / هش تراکنش** رو بفرست:\n\nلغو: /cancel",
    )
    await callback.answer()


@router.message(DepositFlow.waiting_txid)
async def dep_txid(message: Message, state: FSMContext):
    txid = (message.text or "").strip()
    if len(txid) < 10 or " " in txid:
        await send_safe(message, "❌ هش کامل تراکنش رو بدون فاصله بفرست.")
        return

    data = await state.get_data()
    net, amount = data.get("dep_network"), data.get("dep_amount")
    if not net or not amount:
        await state.clear()
        await send_safe(message, "↩️ نشست منقضی شد. دوباره شروع کن.")
        return

    deposit_id = await create_deposit(message.from_user.id, net, txid, float(amount))
    if deposit_id is None:
        await send_safe(message, "⚠️ این txid قبلاً ثبت شده! تراکنش تکراریه.")
        return

    await state.clear()
    credits = usdt_to_credits(float(amount))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet")],
    ])
    await send_safe(
        message,
        f"💌 **ثبت شد! (شماره #{deposit_id})**\n\n"
        f"💠 شبکه: {NETWORKS[net][0]}\n"
        f"💵 مبلغ: {_fmt_usdt(float(amount))} USDT → `{credits:,} کردیت` بعد از تأیید\n"
        f"🔖 TXID: `{txid[:20]}…`\n\n"
        f"⏱ معمولاً در **کمتر از چند ساعت** بررسی و شارژ می‌شود.\n"
        f"🔔 به‌محض تأیید، پیام شارژ می‌گیری — نگران نباش، پولت امنه 🔒",
        kb,
    )

    from handlers.admin import notify_admins
    akb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید و شارژ", callback_data=f"adm_dep_ok_{deposit_id}"),
            InlineKeyboardButton(text="❌ رد", callback_data=f"adm_dep_no_{deposit_id}"),
        ],
    ])
    uname = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
    await notify_admins(
        message.bot,
        f"🟡 **واریز جدید #{deposit_id}**\n\n"
        f"👤 {uname} (`{message.from_user.id}`)\n"
        f"💠 شبکه: {NETWORKS[net][0]}\n"
        f"💵 مبلغ: {_fmt_usdt(float(amount))} USDT → {credits:,} کردیت\n"
        f"🔖 TXID:\n`{txid}`",
        akb,
    )


# ---------------- Withdraw ----------------

@router.callback_query(F.data == "wd_start")
async def wd_start(callback: CallbackQuery, state: FSMContext):
    user = await get_or_create_user(callback.from_user)
    credits = user["credits"] if user else 0
    wd_min = await dynf("withdraw_min_usdt", config.WITHDRAW_MIN_USDT)
    goal = int(wd_min * config.CREDITS_PER_USDT)

    if credits < goal:
        await callback.answer(
            f"🎯 تا حداقل برداشت ({_fmt_usdt(wd_min)}$) "
            f"{goal - credits:,} کردیت مونده — از فروش و تسک پرش کن!",
            show_alert=True)
        return

    rows = [[InlineKeyboardButton(text=f"{NETWORKS[k][0]}", callback_data=f"wd_net_{k}")]
            for k in NETWORKS]
    rows.append([InlineKeyboardButton(text="🔙 کیف پول", callback_data="wallet")])
    await edit_safe(
        callback.message,
        f"📤 **برداشت USDT**\n\n"
        f"💳 موجودی قابل برداشت: **{credits:,} کردیت** ≈ {_fmt_usdt(credits / config.CREDITS_PER_USDT)}$\n\n"
        f"شبکهٔ دریافت رو انتخاب کن:",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wd_net_"))
async def wd_network(callback: CallbackQuery, state: FSMContext):
    net = callback.data.split("_")[2]
    if net not in NETWORKS:
        await callback.answer("شبکه نامعتبر!", show_alert=True)
        return

    fee = await dynf(f"fee_{net}", config.WITHDRAW_FEES.get(net, 1))
    wd_min = await dynf("withdraw_min_usdt", config.WITHDRAW_MIN_USDT)
    await state.set_state(WithdrawFlow.waiting_address)
    await state.update_data(wd_network=net)
    await edit_safe(
        callback.message,
        f"📤 **برداشت به شبکه {NETWORKS[net][0]}**\n\n"
        f"آدرس کیف پول مقصد رو بفرست:\n\n"
        f"💸 کارمزد شبکه: **{_fmt_usdt(fee)} USDT** (از مبلغ برداشت کسر می‌شه)\n"
        f"حداقل برداشت: **{_fmt_usdt(wd_min)} USDT**\n\n"
        f"لغو: /cancel",
    )
    await callback.answer()


@router.message(WithdrawFlow.waiting_address)
async def wd_address(message: Message, state: FSMContext):
    addr = (message.text or "").strip()
    if len(addr) < 20 or len(addr) > 120 or " " in addr:
        await send_safe(message, "❌ آدرس نامعتبره. آدرس کیف پول خالص بفرست (بدون فاصله).")
        return

    data = await state.get_data()
    net = data.get("wd_network")
    if not net:
        await state.clear()
        await send_safe(message, "↩️ نشست برداشت منقضی شد. دوباره شروع کن.")
        return

    await state.update_data(wd_address=addr)
    await state.set_state(WithdrawFlow.waiting_amount)

    user = await get_or_create_user(message.from_user)
    max_wd = user["credits"] / config.CREDITS_PER_USDT
    fee = config.WITHDRAW_FEES.get(net, 1)

    await send_safe(
        message,
        f"✅ آدرس ذخیره شد:\n`{addr}`\n\n"
        f"💵 حالا **مبلغ برداشت** به USDT بفرست (فقط عدد):\n\n"
        f"حداکثر قابل برداشت: **{_fmt_usdt(max_wd)} USDT**\n"
        f"(دریافت نهایی پس از کسر {_fmt_usdt(fee)} کارمزد)",
    )


@router.message(WithdrawFlow.waiting_amount)
async def wd_amount(message: Message, state: FSMContext):
    user = await get_or_create_user(message.from_user)
    raw = (message.text or "").strip().replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", raw):
        await send_safe(message, "❌ فقط عدد بفرست. مثال: `12.5`")
        return

    amount = float(raw)

    wd_min = await dynf("withdraw_min_usdt", config.WITHDRAW_MIN_USDT)
    if amount < wd_min:
        await send_safe(
            message,
            f"❌ حداقل برداشت {_fmt_usdt(wd_min)} USDT هست.",
        )
        return

    data = await state.get_data()
    net, addr = data.get("wd_network"), data.get("wd_address")
    if not net or not addr:
        await state.clear()
        await send_safe(message, "↩️ نشست برداشت منقضی شد. دوباره شروع کن.")
        return

    fee = await dynf(f"fee_{net}", config.WITHDRAW_FEES.get(net, 1))
    if amount <= fee:
        await send_safe(message, f"❌ مبلغ باید بیشتر از کارمزد ({_fmt_usdt(fee)}) باشه.")
        return

    needed_credits = usdt_to_credits(amount)

    # ATOMIC hold: single-statement guard prevents concurrent overdraft
    from database import try_hold_credits
    ok = await try_hold_credits(
        message.from_user.id, needed_credits, "withdraw",
        f"Withdraw hold (requesting {amount:g} USDT)")
    if not ok:
        have_usdt = user["credits"] / config.CREDITS_PER_USDT
        await send_safe(
            message,
            f"❌ موجودی کافی نیست!\nموجودی: {_fmt_usdt(have_usdt)} USDT | درخواستی: {_fmt_usdt(amount)}",
        )
        return

    try:
        wd_id = await create_withdrawal(message.from_user.id, net, addr, amount, fee)
    except Exception:
        # The balance hold must never disappear if persistence fails.
        await update_credits(
            message.from_user.id, needed_credits, "withdraw_refund",
            "Withdrawal creation failed; hold released",
        )
        await state.clear()
        await send_safe(message, "⚠️ ثبت برداشت ناموفق بود؛ موجودی‌ات آزاد شد. دوباره تلاش کن.")
        return

    await state.clear()

    payout = amount - fee
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Wallet", callback_data="wallet")],
    ])
    await send_safe(
        message,
        f"✅ **درخواست برداشت #{wd_id} ثبت شد**\n\n"
        f"💠 شبکه: {NETWORKS[net][0]}\n"
        f"🏦 آدرس: `{addr}`\n"
        f"💵 مبلغ: {_fmt_usdt(amount)} USDT (کارمزد {_fmt_usdt(fee)})\n"
        f"📩 دریافتی شما: **{_fmt_usdt(payout)} USDT**\n\n"
        f"⏳ موجودی فریز شد؛ بعد از پرداخت ادمین تأیید نهایی می‌شه.\n"
        f"در صورت رد، مبلغ کامل برگشت داده می‌شه.",
        kb,
    )

    from handlers.admin import notify_admins
    akb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 پرداخت شد", callback_data=f"adm_wd_ok_{wd_id}"),
            InlineKeyboardButton(text="↩️ رد + برگشت وجه", callback_data=f"adm_wd_no_{wd_id}"),
        ],
    ])
    uname = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
    await notify_admins(
        message.bot,
        f"🔵 **برداشت جدید #{wd_id}**\n\n"
        f"👤 {uname} (`{message.from_user.id}`)\n"
        f"💠 شبکه: {NETWORKS[net][0]}\n"
        f"🏦 آدرس:\n`{addr}`\n"
        f"💵 پرداخت به کاربر: **{_fmt_usdt(payout)} USDT** (کارمزد {_fmt_usdt(fee)})\n"
        f"🪙 فریز شده: {needed_credits:,} کردیت",
        akb,
    )


async def update_credits_hold(user_id: int, credits: int, desc: str):
    from database import update_credits
    await update_credits(user_id, -credits, "withdraw", desc)


# ---------------- History ----------------

@router.callback_query(F.data == "wh_history")
async def wh_history(callback: CallbackQuery, state: FSMContext):
    from time import time as _now
    deps = await list_user_deposits(callback.from_user.id, 8)
    wds = await list_user_withdrawals(callback.from_user.id, 8)

    icon = {"pending": "⏳", "approved": "✅", "rejected": "❌", "paid": "💸"}
    label = {"pending": "در انتظار", "approved": "تأیید شد", "rejected": "رد شد", "paid": "پرداخت شد"}

    text = "📜 **تاریخچه مالی**\n\n"
    if deps:
        text += "**📥 واریزها:**\n"
        for d in deps:
            age = max(0, int((_now() - (d["created_at"] or _now())) / 3600))
            when = f" · {age}ساعت پیش" if age else " · الان"
            text += (f"{icon.get(d['status'], '•')} #{d['id']} · "
                     f"{_fmt_usdt(d['amount_usdt'])}$ روی {NETWORKS[d['network']][0]} · "
                     f"{label.get(d['status'], d['status'])}{when}\n")
    if wds:
        text += "\n**📤 برداشت‌ها:**\n"
        for w in wds:
            text += (f"{icon.get(w['status'], '•')} #{w['id']} · "
                     f"{_fmt_usdt(w['amount_usdt'])}$ به {NETWORKS[w['network']][0]} · "
                     f"{label.get(w['status'], w['status'])}\n")
    if not deps and not wds:
        text += "_هنوز تراکنشی نداری — اولین واریزت رو همینجا شروع کن!_ 💫"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 کیف پول", callback_data="wallet")],
    ])
    await edit_safe(callback.message, text, kb)
    await callback.answer()
