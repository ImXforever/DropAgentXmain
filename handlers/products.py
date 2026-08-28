import os
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils import get_or_create_user,  send_safe, edit_safe
from database import (
    get_user, get_my_products, get_product, get_db, update_credits,
    get_purchased_products, update_product_field,
)
from ai_agent import (
    generate_product_idea, generate_product_title,
    generate_product_description, IDEA_JSON_CONTRACT,
)
from config import config

router = Router()

CATEGORIES = {
    "all": "📂 همه",
    "education": "📚 آموزش",
    "graphics": "🎨 گرافیک",
    "coding": "💻 کدنویسی",
    "content": "📝 محتوا",
    "template": "📦 قالب",
    "tools": "🔧 ابزار",
    "general": "📂 سایر",
}


class ProductCreation(StatesGroup):
    waiting_for_idea = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_category = State()
    waiting_for_file = State()
    waiting_for_tags = State()


class ProductEdit(StatesGroup):
    waiting_price = State()
    waiting_description = State()
    waiting_photo = State()
    waiting_file = State()
    waiting_tags = State()
    waiting_link = State()


@router.callback_query(F.data == "my_products")
async def my_products_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    products = await get_my_products(callback.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ساخت محصول جدید", callback_data="create_product")],
        [InlineKeyboardButton(text="✏️ ویرایش محصولاتم", callback_data="edit_products")],
        [InlineKeyboardButton(text="📥 خریداری‌شده‌ها", callback_data="purchased_products")],
        [InlineKeyboardButton(text="🗑 حذف محصول", callback_data="delete_product")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    text = f"📦 **محصولات من** ({len(products)} محصول)\n\n"
    st_icon = {"approved": "🟢", "pending": "⏳", "rejected": "❌"}
    if products:
        for pr in products[:10]:
            status = st_icon.get(pr.get("status") or "approved",
                                 "🟢") if pr["is_active"] else "🔴"
            imgs = "🖼️" * (bool(pr.get("img_main")) + bool(pr.get("img_feed")) +
                           bool(pr.get("img_story")))
            text += f"{status} **{pr['title']}** — {pr['price_credits']}💰 | فروش: {pr['sales_count']} {imgs}\n"
    else:
        text += "هنوز محصولی نساختی!\n"

    text += f"\n💰 کردیت شما: **{user['credits']:,}** (≈{user['credits'] / 1000:.2f}$)"

    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# ---- delete product by owner ----

@router.callback_query(F.data == "delete_product")
async def delete_product_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    products = await get_my_products(callback.from_user.id)
    deletable = [p for p in products if not p.get("sales_count")]
    if not deletable:
        await edit_safe(
            callback.message,
            "🗑 هیچ محصول قابل حذفی نداری.\n"
            "(محصولاتی که فروش داشته‌اند قابل حذف نیستند — از پنل ادمین تماس بگیر)",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")]]))
        return
    kb_buttons = []
    for p in deletable[:15]:
        kb_buttons.append([InlineKeyboardButton(
            text=f"🗑 {p['title'][:40]} ({p['price_credits']}💰)",
            callback_data=f"delprod_{p['id']}")])
    kb_buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")])
    await edit_safe(
        callback.message,
        f"🗑 **حذف محصول**\n\n"
        f"کدام محصول را حذف کنی؟ ({len(deletable)} قابل حذف)\n"
        f"⚠️ این عمل برگشت‌پذیر نیست!",
        InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="Markdown")
    await callback.answer()


# NOTE: do_delete_product MUST be registered BEFORE confirm_delete_product
# because aiogram matches in registration order — otherwise delprod_yes_*
# would be caught by the broader delprod_* pattern.

@router.callback_query(F.data.startswith("delprod_yes_"))
async def do_delete_product(callback: CallbackQuery):
    pid = int(callback.data.replace("delprod_yes_", ""))
    from database import delete_product
    ok, msg = await delete_product(pid, callback.from_user.id)
    if ok:
        await edit_safe(
            callback.message,
            f"🗑 «{msg or 'محصول'}» حذف شد ✅",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 محصولات من",
                                      callback_data="my_products")]]))
        await callback.answer("حذف شد ✅", show_alert=True)
    else:
        await callback.answer(msg, show_alert=True)


@router.callback_query(F.data.regexp(r"^delprod_\d+$"))
async def confirm_delete_product(callback: CallbackQuery):
    pid = int(callback.data.replace("delprod_", ""))
    from database import get_product
    p = await get_product(pid)
    if not p or p["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری ❌", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 بله، حذفش کن!", callback_data=f"delprod_yes_{pid}")],
        [InlineKeyboardButton(text="❌ نه، منصرف شدم", callback_data="delete_product")],
    ])
    await edit_safe(callback.message,
                    f"⚠️ **حذف «{p['title']}»؟**\n\nاین عمل برگشت‌پذیر نیست!\n"
                    f"عکس‌ها و فایل هم پاک می‌شوند.",
                    reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "purchased_products")
async def purchased_products(callback: CallbackQuery):
    products = await get_purchased_products(callback.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")],
    ])

    if not products:
        await edit_safe(callback.message, 
            "📥 **محصول خریداری شده‌ای نداری**\n\n"
            "برو marketplace و چیزی بخر!",
            reply_markup=kb, parse_mode="Markdown",
        )
        await callback.answer()
        return

    text = "📥 **محصولات خریداری شده:**\n\n"
    buttons = []
    for p in products:
        text += f"• **{p['title']}** — خریداری شده\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"📥 {p['title']}",
                callback_data=f"download_product_{p['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("download_product_"))
async def download_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)

    if not product:
        await callback.answer("محصول پیدا نشد!", show_alert=True)
        return

    # SECURITY GATE: only the owner or a verified buyer may fetch the file
    from database import is_product_purchased_by_user
    is_owner = product["creator_id"] == callback.from_user.id
    purchased = await is_product_purchased_by_user(product_id, callback.from_user.id)
    if not (is_owner or purchased):
        await callback.answer("⛔ این فایل مال شما نیست — اول محصول را بخرید.", show_alert=True)
        return

    if product["file_path"] and os.path.exists(product["file_path"]):
        await callback.message.answer_document(
            FSInputFile(product["file_path"]),
            caption=f"📥 **{product['title']}**\n\n{product['description'] or ''}",
            parse_mode="Markdown",
        )
    else:
        if product["description"]:
            await callback.message.answer(
                f"📥 **{product['title']}**\n\n{product['description']}",
                parse_mode="Markdown",
            )
        else:
            await callback.answer("فایل محصول موجود نیست!", show_alert=True)
            return
    await callback.answer()


@router.callback_query(F.data == "create_product")
async def create_product_start(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 با کمک هوش مصنوعی", callback_data="ai_assisted_create")],
        [InlineKeyboardButton(text="✍️ ساخت دستی", callback_data="manual_create")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")],
    ])

    await edit_safe(callback.message, 
        "➕ **ساخت محصول جدید**\n\n"
        "روش ساخت رو انتخاب کن:\n\n"
        "🤖 **AI Help:** هوش مصنوعی بهت کمک می‌کنه ایده بده، عنوان و توضیحات بنویسه\n"
        "✍️ **Manual:** خودت اطلاعات رو وارد کن",
        reply_markup=kb, parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "ai_assisted_create")
async def ai_assisted_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductCreation.waiting_for_idea)
    await edit_safe(callback.message, 
        "🤖 **ساخت محصول با کمک AI**\n\n"
        "📝 ایده یا موضوع محصولت رو بگو:\n\n"
        "مثال:\n"
        "• 'آموزش HTML از صفر'\n"
        "• 'پکیج آیکون‌های SVG'\n"
        "• 'قالب رزومه حرفه‌ای'\n"
        "• 'آموزش Python برای مبتدی‌ها'\n\n"
        "AI بهت ایده، عنوان، توضیحات و قیمت پیشنهاد میده!",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(ProductCreation.waiting_for_idea, F.photo)
async def process_idea_photo(message: Message, state: FSMContext):
    """Vision: analyze product photo → auto listing."""
    import base64
    import tempfile
    from hermes_engine import llm_call_raw
    from hermes_engine import extract_json

    status = await message.answer("👁️ هرمس در حال دیدن عکس محصول...")
    photo = message.photo[-1]

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    await message.bot.download(photo, destination=tmp.name)
    with open(tmp.name, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    try:
        os.remove(tmp.name)
    except OSError:
        pass

    msgs = [{
        "role": "user",
        "content": [
            {"type": "text",
             "text": "این عکس یک محصول دیجیتال است. آن را دقیق تحلیل کن و " + IDEA_JSON_CONTRACT},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ],
    }]

    try:
        msg = await llm_call_raw(msgs, max_tokens=800, temperature=0.5)
        result = _content_of(msg)
    except Exception as e:
        await status.edit_text(f"⚠️ مدل vision در دسترس نیست: {str(e)[:150]}")
        return
    try:
        await status.delete()
    except Exception:
        pass
    await _present_idea(message, state, result)


def _content_of(msg: dict) -> str:
    c = msg.get("content")
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return str(c or "")


async def _present_idea(message: Message, state: FSMContext, result: str):
    from hermes_engine import extract_json
    data = extract_json(result) or {
        "title": "", "description": result[:500], "suggested_price": 100,
        "category": "general", "tags": "", "cover_idea": "",
    }
    if not data.get("title"):
        data["title"] = "محصول جدید"
    await state.update_data(
        ai_title=data.get("title", ""),
        ai_description=data.get("description", ""),
        ai_price=data.get("suggested_price", 100),
        ai_category=data.get("category", "general"),
        ai_tags=data.get("tags", ""),
        ai_cover=data.get("cover_idea", ""),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 استفاده از پیشنهاد AI", callback_data="use_ai_suggestions")],
        [InlineKeyboardButton(text="✍️ ساخت دستی", callback_data="manual_create")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="my_products")],
    ])
    await message.answer(
        f"🤖 **تحلیل کامل شد:**\n\n"
        f"📌 **عنوان:** {data.get('title', '-')}\n"
        f"📝 **توضیحات:** {data.get('description', '-')[:200]}...\n"
        f"💰 **قیمت پیشنهادی:** {data.get('suggested_price', 100)} کردیت\n"
        f"📂 **دسته‌بندی:** {data.get('category', '-')}\n"
        f"🏷️ **تگ‌ها:** {data.get('tags', '-')}\n\n"
        f"از پیشنهادات استفاده کن یا دستی ادامه بده:",
        reply_markup=kb, parse_mode="Markdown",
    )


@router.message(ProductCreation.waiting_for_idea)
async def process_idea(message: Message, state: FSMContext):
    await message.answer("⏳ هرمس در حال پردازش ایده شماست...")

    result = await generate_product_idea(message.text, user_key=message.from_user.id)

    from hermes_engine import extract_json
    data = extract_json(result) or {
        "title": message.text[:50],
        "description": result[:500],
        "suggested_price": 100,
        "category": "general",
        "tags": "",
        "cover_idea": "",
    }

    await state.update_data(
        ai_title=data.get("title", ""),
        ai_description=data.get("description", ""),
        ai_price=data.get("suggested_price", 100),
        ai_category=data.get("category", "general"),
        ai_tags=data.get("tags", ""),
        ai_cover=data.get("cover_idea", ""),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 استفاده از پیشنهاد AI", callback_data="use_ai_suggestions")],
        [InlineKeyboardButton(text="✍️ ساخت دستی", callback_data="manual_create")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="my_products")],
    ])

    await message.answer(
        f"🤖 **AI ایده شما رو پردازش کرد:**\n\n"
        f"📌 **عنوان:** {data.get('title', '-')}\n"
        f"📝 **توضیحات:** {data.get('description', '-')[:200]}...\n"
        f"💰 **قیمت پیشنهادی:** {data.get('suggested_price', 100)} کردیت\n"
        f"📂 **دسته‌بندی:** {data.get('category', '-')}\n"
        f"🏷️ **تگ‌ها:** {data.get('tags', '-')}\n\n"
        f"از پیشنهادات AI استفاده کن یا خودت ویرایش کن:",
        reply_markup=kb, parse_mode="Markdown",
    )


@router.callback_query(F.data == "use_ai_suggestions")
async def use_ai_suggestions(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(
        title=data.get("ai_title", ""),
        description=data.get("ai_description", ""),
        price=data.get("ai_price", 100),
        category=data.get("ai_category", "general"),
        tags=data.get("ai_tags", ""),
    )
    await state.set_state(ProductCreation.waiting_for_file)
    await edit_safe(callback.message, 
        "📦 **مرحله ۴: آپلود فایل محصول**\n\n"
        "فایل محصول رو بفرست (PDF, ZIP, HTML, PNG, ...)\n"
        "یا اگه فقط محتوای متنی داری، 'skip' بزن.",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "manual_create")
async def manual_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductCreation.waiting_for_title)
    await edit_safe(callback.message, 
        "✍️ **ساخت دستی محصول**\n\n"
        "📝 **مرحله ۱:** عنوان محصول رو بنویس:",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(ProductCreation.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ProductCreation.waiting_for_description)
    await message.answer(
        f"✅ عنوان: **{message.text}**\n\n"
        f"📝 **مرحله ۲:** توضیحات محصول رو بنویس:",
        parse_mode="Markdown",
    )


@router.message(ProductCreation.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ProductCreation.waiting_for_price)
    await message.answer(
        "✅ توضیحات ذخیره شد\n\n"
        "💰 **مرحله ۳:** قیمت محصول (بر حسب کردیت):\n\n"
        "💡 پیشنهاد:\n"
        "• آموزش ساده: 50-100 کردیت\n"
        "• آموزش حرفه‌ای: 100-300 کردیت\n"
        "• پکیج کامل: 300-1000 کردیت",
        parse_mode="Markdown",
    )


@router.message(ProductCreation.waiting_for_price)
async def process_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        if price < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد صحیح وارد کن!")
        return

    await state.update_data(price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 آموزش", callback_data="cat_education")],
        [InlineKeyboardButton(text="🎨 گرافیک", callback_data="cat_graphics")],
        [InlineKeyboardButton(text="💻 کدنویسی", callback_data="cat_coding")],
        [InlineKeyboardButton(text="📝 محتوا", callback_data="cat_content")],
        [InlineKeyboardButton(text="📦 قالب", callback_data="cat_template")],
        [InlineKeyboardButton(text="🔧 ابزار", callback_data="cat_tools")],
        [InlineKeyboardButton(text="📂 سایر", callback_data="cat_general")],
    ])

    await message.answer(
        f"✅ قیمت: **{price}** کردیت\n\n"
        "📂 **مرحله ۴:** دسته‌بندی محصول رو انتخاب کن:",
        reply_markup=kb, parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category_map = {
        "cat_education": "education",
        "cat_graphics": "graphics",
        "cat_coding": "coding",
        "cat_content": "content",
        "cat_template": "template",
        "cat_tools": "tools",
        "cat_general": "general",
    }
    category = category_map.get(callback.data, "general")
    category_names = {
        "education": "📚 آموزش",
        "graphics": "🎨 گرافیک",
        "coding": "💻 کدنویسی",
        "content": "📝 محتوا",
        "template": "📦 قالب",
        "tools": "🔧 ابزار",
        "general": "📂 سایر",
    }

    await state.update_data(category=category)
    await state.set_state(ProductCreation.waiting_for_file)
    await edit_safe(callback.message, 
        f"✅ دسته‌بندی: **{category_names.get(category, category)}**\n\n"
        f"📦 **مرحله ۵:** فایل محصول رو آپلود کن\n\n"
        f"فرمت‌های پشتیبانی شده:\n"
        f"PDF, ZIP, HTML, CSS, JS, PNG, JPG, MP4\n\n"
        f"اگه فقط محتوای متنی داری، 'skip' بزن.",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(ProductCreation.waiting_for_file, F.document)
async def process_file(message: Message, state: FSMContext):
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    file = message.document
    file_size_mb = file.file_size / (1024 * 1024)
    if file_size_mb > config.MAX_FILE_SIZE_MB:
        await message.answer(f"❌ فایل خیلی بزرگه! حداکثر {config.MAX_FILE_SIZE_MB}MB")
        return

    file_path = os.path.join(config.UPLOAD_DIR, f"{message.from_user.id}_{file.file_name}")
    await message.bot.download(file, destination=file_path)

    await state.update_data(file_path=file_path, file_type=file.mime_type)
    await state.set_state(ProductCreation.waiting_for_tags)
    await message.answer(
        f"✅ فایل آپلود شد: **{file.file_name}** ({file_size_mb:.1f}MB)\n\n"
        f"🏷️ **مرحله ۶:** تگ‌ها رو بنویس (با کاما جدا کن):\n\n"
        f"مثال: `HTML, آموزش, وب, مبتدی`",
        parse_mode="Markdown",
    )


@router.message(ProductCreation.waiting_for_file, F.text)
async def skip_file(message: Message, state: FSMContext):
    if message.text.strip().lower() not in ("skip", "رد", "رد شدن"):
        await message.answer(
            "❓ فایل بفرست یا برای رد کردن بنویس `skip`.",
            parse_mode="Markdown",
        )
        return
    await state.update_data(file_path=None, file_type=None)
    await state.set_state(ProductCreation.waiting_for_tags)
    await message.answer(
        "⏭️ فایل رد شد\n\n"
        "🏷️ **مرحله ۶:** تگ‌ها رو بنویس (با کاما جدا کن):\n\n"
        "مثال: `HTML, آموزش, وب, مبتدی`",
        parse_mode="Markdown",
    )


@router.message(ProductCreation.waiting_for_tags)
async def process_tags(message: Message, state: FSMContext):
    data = await state.get_data()

    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO products (creator_id, title, description, price_credits,
                                     file_path, file_type, category, tags, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                message.from_user.id,
                data["title"],
                data.get("description", ""),
                data["price"],
                data.get("file_path"),
                data.get("file_type"),
                data.get("category", "general"),
                message.text,
            ),
        )
        product_id = cursor.lastrowid
        await db.commit()

    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products")],
        [InlineKeyboardButton(text="➕ ساخت محصول بعدی", callback_data="create_product")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await message.answer(
        f"🎉 **محصول ساخته شد!** 🛡️\n\n"
        f"📌 **{data['title']}**\n"
        f"💰 قیمت: {data['price']} کردیت\n"
        f"📂 دسته: {data.get('category', '-')}\n\n"
        f"⏳ **در انتظار تأیید ادمین** — بعد از تأیید، خودکار در مارکت منتشر می‌شود و بهت خبر می‌دهیم.",
        reply_markup=kb, parse_mode="Markdown",
    )

    # notify admins for approval
    from handlers.admin import notify_admins
    akb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید", callback_data=f"adm_appr_{product_id}"),
            InlineKeyboardButton(text="❌ رد", callback_data=f"adm_rej_{product_id}"),
        ],
    ])
    uname = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
    await notify_admins(
        message.bot,
        f"🆕 **محصول جدید در انتظار تأیید** #{product_id}\n\n"
        f"📌 {data['title']}\n💰 {data['price']} کردیت | 📂 {data.get('category','general')}\n"
        f"👤 {uname}",
        akb,
    )


# ================= Product full editing =================

@router.callback_query(F.data == "edit_products")
async def edit_products_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    products = await get_my_products(callback.from_user.id)
    if not products:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ساخت محصول", callback_data="create_product")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")],
        ])
        await edit_safe(callback.message, "📦 هنوز محصولی برای ویرایش نداری!", reply_markup=kb)
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"✏️ {p['title'][:32]} ({p['price_credits']}💰)",
            callback_data=f"edit_prod_{p['id']}",
        )]
        for p in products[:12]
    ]
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="my_products")])
    await edit_safe(callback.message, 
        "✏️ **ویرایش محصولات**\n\nمحصول موردنظر رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_prod_"))
async def edit_product_menu(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    product = await get_product(pid)

    if not product or product["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری!", show_alert=True)
        return

    await state.set_state(None)
    await state.update_data(edit_pid=pid)

    photo = "✅ دارد" if product.get("photo_path") else "— ندارد"
    file = "✅ دارد" if product.get("file_path") else "— ندارد"
    link_s = "✅ ثبت شده" if product.get("link") else "— ندارد"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 تغییر قیمت", callback_data=f"ep_f_price_{pid}"),
         InlineKeyboardButton(text="📝 توضیحات", callback_data=f"ep_f_desc_{pid}")],
        [InlineKeyboardButton(text="📷 عکس کاور", callback_data=f"ep_f_photo_{pid}"),
         InlineKeyboardButton(text="📦 فایل محصول", callback_data=f"ep_f_file_{pid}")],
        [InlineKeyboardButton(text="🏷️ تگ‌ها", callback_data=f"ep_f_tags_{pid}"),
         InlineKeyboardButton(text="🔗 لینک خارجی", callback_data=f"ep_f_link_{pid}")],
    ])

    await edit_safe(callback.message, 
        f"⚙️ **ویرایش: {product['title']}**\n\n"
        f"💰 قیمت فعلی: {product['price_credits']} کردیت\n"
        f"📷 عکس: {photo} | 📦 فایل: {file}\n        🔗 لینک: {link_s}\n\n"
        f"کدوم فیلد رو عوض کنم؟",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ep_f_"))
async def edit_field_pick(callback: CallbackQuery, state: FSMContext):
    _, _, field, pid = callback.data.split("_")
    data = await get_product(int(pid))
    if not data or data["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری!", show_alert=True)
        return

    prompts = {
        "price": ("💰 قیمت جدید (عدد کردیت):", ProductEdit.waiting_price),
        "desc": ("📝 توضیحات جدید رو بفرست:", ProductEdit.waiting_description),
        "photo": ("📷 عکس کاور جدید رو بفرست (Photo):\nبرای حذف بنویس `حذف`", ProductEdit.waiting_photo),
        "file": ("📦 فایل جدید رو بفرست (Document):\nبرای حذف بنویس `حذف`", ProductEdit.waiting_file),
        "tags": ("🏷️ تگ‌های جدید (با کاما):", ProductEdit.waiting_tags),
        "link": ("🔗 لینک جدید (با https شروع شود):\nبرای حذف بنویس `حذف`", ProductEdit.waiting_link),
    }
    prompt, st = prompts[field]
    await state.set_state(st)
    await state.update_data(edit_pid=int(pid), edit_field=field)
    await edit_safe(callback.message, prompt, parse_mode="Markdown")
    await callback.answer()


@router.message(ProductEdit.waiting_price)
async def ep_price(message: Message, state: FSMContext):
    try:
        price = int((message.text or "").strip())
        if price < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ عدد صحیح مثبت بفرست.")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "price_credits", price)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ ادامه ویرایش", callback_data=f"edit_prod_{data['edit_pid']}")],
    ])
    await message.answer(f"✅ قیمت → **{price} کردیت**", reply_markup=kb, parse_mode="Markdown")


@router.message(ProductEdit.waiting_description)
async def ep_desc(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ فقط متن.")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "description", message.text.strip()[:1500])
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ ادامه ویرایش", callback_data=f"edit_prod_{data['edit_pid']}")],
    ])
    await message.answer("✅ توضیحات آپدیت شد.", reply_markup=kb)


@router.message(ProductEdit.waiting_photo, F.photo)
async def ep_photo(message: Message, state: FSMContext):
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    photo = message.photo[-1]
    path = os.path.join(config.UPLOAD_DIR, f"cover_{message.from_user.id}_{int(time.time())}.jpg")
    await message.bot.download(photo, destination=path)

    data = await state.get_data()
    await update_product_field(data["edit_pid"], "photo_path", path)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ ادامه ویرایش", callback_data=f"edit_prod_{data['edit_pid']}")],
    ])
    await message.answer("✅ عکس کاور آپدیت شد.", reply_markup=kb)


@router.message(ProductEdit.waiting_photo, F.text)
async def ep_photo_del(message: Message, state: FSMContext):
    if (message.text or "").strip() != "حذف":
        await message.answer("❓ یک Photo بفرست یا بنویس `حذف`.")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "photo_path", None)
    await state.set_state(None)
    await message.answer("🗑 عکس حذف شد.")


@router.message(ProductEdit.waiting_file, F.document)
async def ep_file(message: Message, state: FSMContext):
    file = message.document
    size_mb = (file.file_size or 0) / (1024 * 1024)
    if size_mb > config.MAX_FILE_SIZE_MB:
        await message.answer(f"❌ حداکثر {config.MAX_FILE_SIZE_MB}MB.")
        return
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(config.UPLOAD_DIR, f"{message.from_user.id}_{int(time.time())}_{file.file_name}")
    await message.bot.download(file, destination=path)

    data = await state.get_data()
    await update_product_field(data["edit_pid"], "file_path", path)
    await update_product_field(data["edit_pid"], "file_type", file.mime_type)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ ادامه ویرایش", callback_data=f"edit_prod_{data['edit_pid']}")],
    ])
    await message.answer(f"✅ فایل جدید ثبت شد ({size_mb:.1f}MB).", reply_markup=kb)


@router.message(ProductEdit.waiting_file, F.text)
async def ep_file_del(message: Message, state: FSMContext):
    if (message.text or "").strip() != "حذف":
        await message.answer("❓ یک Document بفرست یا بنویس `حذف`.")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "file_path", None)
    await update_product_field(data["edit_pid"], "file_type", None)
    await state.set_state(None)
    await message.answer("🗑 فایل حذف شد.")


@router.message(ProductEdit.waiting_tags)
async def ep_tags(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ فقط متن.")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "tags", message.text.strip()[:200])
    await state.set_state(None)
    await message.answer("✅ تگ‌ها آپدیت شدند.")


@router.message(ProductEdit.waiting_link)
async def ep_link(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt == "حذف":
        val = None
    elif txt.startswith(("http://", "https://")) and " " not in txt and len(txt) <= 300:
        val = txt
    else:
        await message.answer("❌ لینک باید با `https://` شروع شود و بدون فاصله باشد.", parse_mode="Markdown")
        return
    data = await state.get_data()
    await update_product_field(data["edit_pid"], "link", val)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ ادامه ویرایش", callback_data=f"edit_prod_{data['edit_pid']}")],
    ])
    await message.answer("🔗 لینک حذف شد." if val is None else f"✅ لینک ثبت شد:\n{val}", reply_markup=kb)
