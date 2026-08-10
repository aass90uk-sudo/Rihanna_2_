"""ناشر المجلات مع استخراج النص ومنع التكرار وتقسيم نصوص تيليجرام."""

import io
import logging
import os
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from . import config, pdf_manager, history, vision


# ==========================================
# تقسيم النص حسب حدود Telegram
# ==========================================

def _split_text(
    text: str,
    first_limit: int,
    next_limit: int,
) -> list[str]:
    """
    تقسيم النص حسب حدود تيليجرام.

    الجزء الأول يذهب مع الصورة.
    الأجزاء التالية ترسل كرسائل نصية مستقلة.

    يتم حساب UTF-16 لأن Telegram يعتمد هذا الأسلوب
    في حساب طول النص.
    """

    if not text:
        return []

    def telegram_length(value: str) -> int:
        return len(value.encode("utf-16-le")) // 2

    def take_part(
        remaining: str,
        limit: int,
    ) -> tuple[str, str]:

        if telegram_length(remaining) <= limit:
            return remaining, ""

        cut = 0
        used = 0

        for index, character in enumerate(remaining):

            character_length = telegram_length(character)

            if used + character_length > limit:
                break

            used += character_length
            cut = index + 1

        if cut <= 0:
            return "", remaining

        candidate = remaining[:cut]

        # نحاول عدم قطع الكلمة
        boundary = max(
            candidate.rfind("\n"),
            candidate.rfind(" "),
        )

        if boundary > 0:
            cut = boundary + 1

        part = remaining[:cut]
        rest = remaining[cut:]

        return part, rest

    parts: list[str] = []

    remaining = text.strip()
    limit = first_limit

    while remaining:

        part, remaining = take_part(
            remaining,
            limit,
        )

        if not part:
            # حماية من الدخول في حلقة لا نهائية
            # إذا كان هناك حد غير صالح.
            logging.error(
                "[MAGAZINE] تعذر تقسيم النص ضمن حد Telegram."
            )
            break

        parts.append(part)

        # الجزء الأول = Caption
        # الأجزاء التالية = Messages
        limit = next_limit

    return parts


# ==========================================
# البحث عن صفحة داخل مجلة محددة
# ==========================================

def _find_next_unpublished_page(
    pdf_file: str,
) -> Optional[pdf_manager.PageImage]:
    """
    البحث عن أول صفحة غير منشورة داخل ملف PDF محدد.

    كل مجلة لها تسلسل مستقل.
    """

    resolved_pdf_file = config.resolve_magazine_file(pdf_file)
    pdf_path = os.path.join(
        config.MAGAZINE_DIR,
        resolved_pdf_file,
    )

    if not pdf_file.lower().endswith(".pdf"):
        logging.warning(
            f"[MAGAZINE] الملف ليس PDF: {resolved_pdf_file}"
        )
        return None

    if not os.path.isfile(pdf_path):
        logging.error(
            f"[MAGAZINE] ملف المجلة غير موجود: {pdf_path}"
        )
        return None

    total = pdf_manager.get_total_pages(
        pdf_path
    )

    if total <= 0:
        logging.warning(
            f"[MAGAZINE] لا توجد صفحات في: {resolved_pdf_file}"
        )
        return None

    logging.info(
        f"[MAGAZINE] فحص المجلة: {resolved_pdf_file} "
        f"— إجمالي الصفحات: {total}"
    )

    for page_num in range(total):

        page = pdf_manager.render_page(
            pdf_path,
            page_num,
        )

        if page is None:
            logging.warning(
                f"[MAGAZINE] تعذر استخراج "
                f"صفحة {page_num + 1} من {resolved_pdf_file}"
            )
            continue

        if history.is_page_published(
            page.page_hash
        ):
            logging.info(
                f"[MAGAZINE] {resolved_pdf_file} "
                f"— صفحة {page_num + 1} "
                f"منشورة سابقاً — SKIP"
            )
            continue

        logging.info(
            f"[MAGAZINE] صفحة جديدة: "
            f"{resolved_pdf_file} — "
            f"{page_num + 1}/{total}"
        )

        # خزّن الاسم الموجود فعلياً كي يكون السجل مفهوماً في Railway.
        page.pdf_file = resolved_pdf_file
        return page

    logging.info(
        f"[MAGAZINE] انتهت جميع صفحات: "
        f"{pdf_file}"
    )

    return None


# ==========================================
# نشر صفحة من مجلة محددة
# ==========================================

async def publish_magazine_file(
    bot: Bot,
    pdf_file: str,
    post_type: str,
) -> None:
    """
    نشر صفحة واحدة من مجلة محددة.

    إذا كان النص أطول من حد Telegram:
        صورة + الجزء الأول
        ثم بقية النص في رسائل مستقلة.

    لا يتم تسجيل الصفحة في السجل
    إلا بعد نجاح إرسال الصورة وجميع التكملات.
    """

    logging.info(
        f"[MAGAZINE] بدء نشر المجلة: "
        f"{pdf_file} | النوع: {post_type}"
    )

    page = _find_next_unpublished_page(
        pdf_file
    )

    if page is None:
        logging.info(
            f"[MAGAZINE] لا توجد صفحة جديدة "
            f"في {pdf_file}"
        )
        return

    # ======================================
    # استخراج النص من نفس صورة الصفحة
    # ======================================

    logging.info(
        f"[MAGAZINE] استخراج النص من "
        f"{pdf_file} — صفحة "
        f"{page.page_number + 1}"
    )

    extracted_text = await vision.extract_text_from_image(
        page.image_bytes
    )

    if extracted_text:
        caption = extracted_text.strip()
    else:
        logging.warning(
            f"[MAGAZINE] لم يتم استخراج نص من "
            f"{pdf_file} — صفحة "
            f"{page.page_number + 1}"
        )
        caption = ""

    # ======================================
    # إضافة اسم القناة
    # ======================================

    if caption:
        full_text = (
            f"{caption}\n\n"
            f"القناة: {config.CHANNEL_USERNAME}"
        )
    else:
        full_text = (
            f"القناة: {config.CHANNEL_USERNAME}"
        )

    # ======================================
    # تقسيم النص
    # ======================================

    parts = _split_text(
        full_text,
        config.TG_CAPTION_LIMIT,
        config.TG_MESSAGE_LIMIT,
    )

    caption_part = (
        parts[0]
        if parts
        else ""
    )

    continuation_parts = (
        parts[1:]
        if len(parts) > 1
        else []
    )

    # ======================================
    # النشر في Telegram
    # ======================================

    try:

        logging.info(
            f"[MAGAZINE] نشر "
            f"{pdf_file} — صفحة "
            f"{page.page_number + 1}"
        )

        # ----------------------------------
        # نشر الصورة + أول جزء من النص
        # ----------------------------------

        photo = io.BytesIO(
            page.image_bytes
        )

        photo.name = (
            f"page_{page.page_number + 1}.jpg"
        )

        message = await bot.send_photo(
            chat_id=config.CHANNEL_USERNAME,
            photo=photo,
            caption=caption_part,
        )

        logging.info(
            f"[MAGAZINE] تم نشر صورة "
            f"{pdf_file} — صفحة "
            f"{page.page_number + 1}"
        )

        # ----------------------------------
        # نشر بقية النص
        # ----------------------------------

        for index, part in enumerate(
            continuation_parts,
            start=2,
        ):

            await bot.send_message(
                chat_id=config.CHANNEL_USERNAME,
                text=part,
            )

            logging.info(
                f"[MAGAZINE] تم إرسال "
                f"تكملة {index} "
                f"لصفحة {page.page_number + 1} "
                f"من {pdf_file}"
            )

        # ==================================
        # تسجيل الصفحة بعد نجاح كل الرسائل
        # ==================================

        message_id = (
            getattr(
                message,
                "message_id",
                None,
            )
            if message
            else None
        )

        history.record_published(
            page_hash=page.page_hash,
            pdf_file=page.pdf_file,
            page_number=page.page_number,
            post_type=post_type,
            telegram_message_id=message_id,
        )

        logging.info(
            f"[MAGAZINE] تم تسجيل الصفحة "
            f"{page.page_number + 1} "
            f"من {pdf_file} كسابقة نشر."
        )

    except TelegramError as e:

        logging.error(
            f"[MAGAZINE] خطأ Telegram أثناء "
            f"نشر {pdf_file}: {e}"
        )

    except Exception as e:

        logging.error(
            f"[MAGAZINE] خطأ غير متوقع أثناء "
            f"نشر {pdf_file}: {e}"
        )


# ==========================================
# النشر الصباحي
# ==========================================

async def publish_morning(
    bot: Bot,
) -> None:
    """
    النشر الصباحي:

    1. المجلة الأولى → صفحة واحدة
    2. مجلة القيادة → صفحة واحدة

    لكل مجلة تسلسل مستقل.
    """

    logging.info(
        "========== بداية النشر الصباحي =========="
    )

    # --------------------------------------
    # المجلة الأولى
    # --------------------------------------

    try:

        await publish_magazine_file(
            bot,
            config.MAGAZINE_1_FILE,
            "morning",
        )

    except Exception as e:

        logging.error(
            "[MAGAZINE] فشل نشر "
            f"المجلة الأولى صباحاً: {e}"
        )

    # --------------------------------------
    # مجلة القيادة
    # --------------------------------------

    try:

        await publish_magazine_file(
            bot,
            config.MAGAZINE_2_FILE,
            "morning",
        )

    except Exception as e:

        logging.error(
            "[MAGAZINE] فشل نشر "
            f"مجلة القيادة صباحاً: {e}"
        )

    logging.info(
        "========== انتهى النشر الصباحي =========="
    )


# ==========================================
# النشر المسائي
# ==========================================

async def publish_evening(
    bot: Bot,
) -> None:
    """
    النشر المسائي:

    1. المجلة الأولى → صفحة واحدة
    2. مجلة القيادة → صفحة واحدة

    لكل مجلة تسلسل مستقل.
    """

    logging.info(
        "========== بداية النشر المسائي =========="
    )

    # --------------------------------------
    # المجلة الأولى
    # --------------------------------------

    try:

        await publish_magazine_file(
            bot,
            config.MAGAZINE_1_FILE,
            "evening",
        )

    except Exception as e:

        logging.error(
            "[MAGAZINE] فشل نشر "
            f"المجلة الأولى مساءً: {e}"
        )

    # --------------------------------------
    # مجلة القيادة
    # --------------------------------------

    try:

        await publish_magazine_file(
            bot,
            config.MAGAZINE_2_FILE,
            "evening",
        )

    except Exception as e:

        logging.error(
            "[MAGAZINE] فشل نشر "
            f"مجلة القيادة مساءً: {e}"
        )

    logging.info(
        "========== انتهى النشر المسائي =========="
        )
