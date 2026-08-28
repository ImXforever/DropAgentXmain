# -*- coding: utf-8 -*-
"""🛡️ فیلتر خودکار ضدکلاهبرداری — آپشن جدید ۰.۶.۰

عنوان/توضیح محصول (و هر متن ورودی دیگر) قبل از انتشار بررسی می‌شود؛
ادعاهای غیرواقعی و کلمات پرخطر مسدود می‌شوند تا مارکت‌پلیس تمیز بماند.

- روشن/خاموش: فرمان /moderation در بات (ادمین) یا setting «moderation_enabled»
- کلمات سفارشی: /moderation add کلمه۱,کلمه۲ یا setting «moderation_extra_words»
- ضد دورزدن: نرمال‌سازی ی/ك عربی، ارقام فارسی، نیم‌فاصله و کاراکترهای مخفی
"""
from database import get_setting

DEFAULT_BLOCK = [
    # تضمین‌های مالی غیرواقعی
    "دوبرابر", "سود تضمینی", "درآمد تضمینی", "پول رایگان", "بی نیاز",
    # دورزدن پرداخت امن بات
    "پرداخت مستقیم", "کارت به کارت خارج", "واریز به پیج",
    # بدافزار / نفوذ
    "کرک", "کیجن", "keygen", "cracked", "rat v", "stealer", "بات نت", "botnet", "ddos",
    # غیرقانونی
    "مخدر", "شیشه", "اسلحه", "مهمات جنگی",
]

_AR2FA = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ے": "ی", "أ": "ا", "إ": "ا", "ؤ": "و",
                        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
                        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"})

_STRIP_CHARS = "\u200c\u200e\u200f*_.~-`'\" "


def _normalize(text: str) -> str:
    t = (text or "").translate(_AR2FA).lower()
    for ch in _STRIP_CHARS:
        t = t.replace(ch, "")
    return t


async def _words() -> list[str]:
    try:
        enabled = (await get_setting("moderation_enabled", "1")) == "1"
    except Exception:
        enabled = True
    if not enabled:
        return []
    extra = ""
    try:
        extra = (await get_setting("moderation_extra_words", "")) or ""
    except Exception:
        pass
    extra_words = [w.strip() for w in extra.replace("،", ",").split(",") if w.strip()]
    return DEFAULT_BLOCK + extra_words


async def check_text(text: str) -> tuple[bool, str]:
    """بررسی متن. برمی‌گرداند: (مجاز؟, اولین عبارت متخلف)"""
    if not (text or "").strip():
        return True, ""
    words = await _words()
    if not words:
        return True, ""
    t = _normalize(text)
    for w in words:
        nw = _normalize(w)
        if nw and nw in t:
            return False, w
    return True, ""
