import asyncio
import time

from aiogram.exceptions import TelegramBadRequest


def esc_md(text: str) -> str:
    """Escape Telegram Markdown (V1) special characters."""
    if text is None:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


# ---------- money formatting (UX: always show credit value in USD) ----------

def usd(credits: float, per_usdt: int = 1000) -> str:
    """Human USD equivalent of a credit amount, e.g. '≈0.35$'."""
    try:
        v = float(credits) / max(1, int(per_usdt))
    except Exception:
        return "≈—$"
    if v >= 100:
        return f"≈{v:,.0f}$"
    if v >= 1:
        return f"≈{v:,.2f}".rstrip("0").rstrip(".") + "$"
    return f"≈{v:.2f}$"


def fmt_credits(credits: int | float, per_usdt: int = 1000) -> str:
    """'1,000 کردیت (≈1$)' — the standard way to show any balance/price."""
    try:
        n = int(credits)
    except Exception:
        return str(credits)
    return f"{n:,} کردیت ({usd(n, per_usdt)})"


def _is_not_modified(e: TelegramBadRequest) -> bool:
    return "message is not modified" in str(e).lower()


async def send_safe(message, text: str, reply_markup=None, parse_mode="Markdown"):
    """answer(); on Markdown parse failure retry as plain text (explicitly
    disabling the bot-wide default parse_mode)."""
    try:
        return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if _is_not_modified(e):
            return None
        return await message.answer(
            text[:4000], reply_markup=reply_markup, parse_mode=None
        )


async def edit_safe(callback_message, text: str, reply_markup=None, parse_mode="Markdown"):
    """Edit text menus robustly:
    1) edit_text  2) edit_caption (media messages)  3) send a fresh message.
    Tolerates identical-content edits and Markdown parse failures."""
    body = text[:4000]
    last_err = None
    for method in ("edit_text", "edit_caption"):
        try:
            return await getattr(callback_message, method)(
                body, reply_markup=reply_markup, parse_mode=parse_mode
            )
        except TelegramBadRequest as e:
            if _is_not_modified(e):
                return None
            last_err = e
            continue
        except AttributeError:
            last_err = None
            continue
    # media without editable text (or other persistent failure) → fresh message
    try:
        return await callback_message.answer(body, reply_markup=reply_markup, parse_mode=None)
    except Exception:
        raise last_err or RuntimeError("edit_safe failed")


class LiveEditor:
    """Hermes-style 'alive' output: typing indicator + throttled progressive
    message edits while the model streams."""

    EDIT_INTERVAL = 1.4      # seconds between edits
    MIN_GROWTH = 40          # chars added before an edit is worth it

    def __init__(self, bot, chat_id: int, placeholder: str = "⏳ هرمس در حال نوشتن…"):
        self.bot = bot
        self.chat_id = chat_id
        self.msg = None
        self._buf = ""
        self._shown = ""
        self._last_edit = 0.0
        self._typing_task = None
        self._placeholder = placeholder

    async def start(self):
        try:
            self.msg = await self.bot.send_message(self.chat_id, self._placeholder)
        except Exception:
            self.msg = None

        async def _typing_loop():
            while True:
                try:
                    await self.bot.send_chat_action(self.chat_id, "typing")
                except Exception:
                    pass
                await asyncio.sleep(4.5)

        self._typing_task = asyncio.create_task(_typing_loop())

    async def on_delta(self, accumulated: str):
        self._buf = accumulated or ""
        now = time.monotonic()
        if not self.msg or (now - self._last_edit) < self.EDIT_INTERVAL:
            return
        if len(self._buf) - len(self._shown) < self.MIN_GROWTH and (now - self._last_edit) < 6:
            return
        self._last_edit = now
        self._shown = self._buf[-3800:]
        try:
            await self.msg.edit_text("✍️ " + self._shown + "\n\n▌")
        except TelegramBadRequest as e:
            if not _is_not_modified(e):
                try:
                    await self.msg.edit_text(("✍️ " + self._shown)[:4000])
                except Exception:
                    pass
        except Exception:
            pass

    async def set_status(self, text: str):
        """Fleet-style live status line on the draft message (plain text)."""
        if not self.msg:
            return
        self._last_edit = time.monotonic()
        try:
            await self.msg.edit_text(text[:4000])
        except TelegramBadRequest as e:
            if not _is_not_modified(e):
                pass
        except Exception:
            pass

    async def finish(self, final_text: str, reply_markup=None) -> None:
        if self._typing_task:
            self._typing_task.cancel()
            self._typing_task = None

        final_text = (final_text or "").strip()[:4000]
        kb = reply_markup
        if self.msg:
            try:
                await self.msg.edit_text(final_text, reply_markup=kb, parse_mode="Markdown")
                return
            except TelegramBadRequest as e:
                if _is_not_modified(e):
                    return
                try:
                    await self.msg.edit_text(final_text[:4000], reply_markup=kb, parse_mode=None)
                    return
                except Exception:
                    pass
            except Exception:
                pass
            try:
                await self.bot.send_message(self.chat_id, final_text, reply_markup=kb, parse_mode="Markdown")
                return
            except Exception:
                try:
                    await self.bot.send_message(self.chat_id, final_text[:4000], reply_markup=kb)
                except Exception:
                    pass
            return
        await self.bot.send_message(self.chat_id, final_text[:4000], reply_markup=kb)

    async def fail(self, err_text: str) -> None:
        if self._typing_task:
            self._typing_task.cancel()
            self._typing_task = None
        if self.msg:
            try:
                await self.msg.edit_text(err_text)
                return
            except Exception:
                pass
        try:
            await self.bot.send_message(self.chat_id, err_text)
        except Exception:
            pass


class ChatStream:
    """Human-style chat delivery — like a friend texting fast on Telegram.

    Streams the model output and sends it as several short messages at natural
    sentence boundaries, with a typing indicator between them. No document-
    style editing, no cursors: messages just arrive one after another."""

    MIN_CHUNK = 60          # chars before a break is worth sending
    MAX_CHUNK = 420         # one "long text" cap per message
    SEND_GAP = 1.15         # min seconds between consecutive messages
    MAX_SENDS = 9           # after this, rest merges into the final message

    _BREAKS = ("\n\n", "\n", ". ", "! ", "؟ ", "… ", "; ")

    def __init__(self, bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self._buf = ""          # full accumulated text seen so far
        self._pending = ""      # tail not yet sent
        self._last_send = 0.0
        self._sends = 0
        self.last_msg = None
        self._typing_task = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self):
        async def _loop():
            while True:
                try:
                    await self.bot.send_chat_action(self.chat_id, "typing")
                except Exception:
                    pass
                await asyncio.sleep(4.5)

        self._typing_task = asyncio.create_task(_loop())

    def _stop_typing(self):
        if self._typing_task:
            self._typing_task.cancel()
            self._typing_task = None

    async def set_status(self, text: str):
        """Compatibility with Fleet/tools paths — keep the human illusion,
        only refresh the typing indicator instead of showing machine status."""
        try:
            await self.bot.send_chat_action(self.chat_id, "typing")
        except Exception:
            pass

    # -- streaming -------------------------------------------------------------

    @staticmethod
    def _find_break(s: str) -> int:
        best = -1
        for b in ChatStream._BREAKS:
            i = s.rfind(b)
            if i != -1:
                end = i + len(b)
                if b.endswith(" ") and end > 0 and s[end - 1:end] == " ":
                    end -= 1  # don't eat the space into the chunk
                if end > best:
                    best = end
        return best  # index AFTER the break, -1 when none

    async def on_delta(self, accumulated: str):
        acc = accumulated or ""
        if len(acc) <= len(self._buf):
            self._buf = acc
            return
        self._pending += acc[len(self._buf):]
        self._buf = acc
        while self._sends < self.MAX_SENDS:
            p = self._pending.lstrip("\n")
            if not p.strip():
                self._pending = ""
                return
            brk = self._find_break(p)
            take = brk if 0 < brk <= self.MAX_CHUNK else (
                self.MAX_CHUNK if len(p) >= self.MAX_CHUNK else 0)
            if not take or take < self.MIN_CHUNK:
                return
            since = time.monotonic() - self._last_send
            if since < self.SEND_GAP:
                return  # next delta tick will flush it
            piece = p[:take].strip()
            self._pending = p[take:]
            if piece:
                await self._send_piece(piece)

    async def _send_piece(self, piece: str):
        gap = time.monotonic() - self._last_send
        if gap < self.SEND_GAP:
            await asyncio.sleep(self.SEND_GAP - gap)
        try:
            self.last_msg = await self.bot.send_message(self.chat_id, piece[:4000])
        except Exception:
            pass
        self._sends += 1
        self._last_send = time.monotonic()

    # -- completion --------------------------------------------------------------

    async def finish(self, final_text: str = "", tag: str = "",
                     reply_markup=None) -> None:
        """Send whatever is left, then attach the keyboard to the last message."""
        self._stop_typing()

        leftover = self._pending.strip()
        body = (final_text or "").strip()

        # de-dupe: body IS the full streamed text and leftover is its unsent
        # tail — concatenating them doubles short replies that never flushed.
        if self._sends == 0:
            full = body or leftover or "…"
            for i in range(0, min(len(full), 7800), 3900):
                part = full[i:i + 3900]
                if part.strip():
                    await self._send_piece(part.strip())
        else:
            tail = leftover[:3800]
            if tag:
                tail = (tail + "\n" + tag).strip() if tail else tag.strip()
            if tail.strip():
                await self._send_piece(tail.strip())

        if reply_markup and self.last_msg:
            try:
                await self.last_msg.edit_reply_markup(reply_markup=reply_markup)
                return
            except Exception:
                pass
        if reply_markup:
            try:
                await self.bot.send_message(self.chat_id, "⬇️", reply_markup=reply_markup)
            except Exception:
                pass

    async def fail(self, err_text: str) -> None:
        self._stop_typing()
        try:
            await self.bot.send_message(self.chat_id, err_text)
        except Exception:
            pass


async def get_or_create_user(from_user):
    """Get user or create if missing — for any handler entry point."""
    from database import get_user, create_user
    u = await get_user(from_user.id)
    if not u:
        u = await create_user(from_user.id, from_user.username, from_user.first_name)
    # v3.5.0: ردیابی فعالیت برای win-back — حداکثر یک نوشتن در ۱۵ دقیقه (سبک)
    try:
        import time as _t
        ls = 0
        try:
            ls = u["last_seen"] or 0
        except (KeyError, IndexError):
            ls = 0
        if _t.time() - ls > 900:
            from database import raw_db
            async with raw_db() as db:
                await db.execute("UPDATE users SET last_seen = ? WHERE user_id = ?",
                                 (_t.time(), from_user.id))
                await db.commit()
    except Exception:
        pass
    return u
