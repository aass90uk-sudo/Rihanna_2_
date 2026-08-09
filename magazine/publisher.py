"""ناشر المجلات مع استخراج النص ومنع التكرار وتقسيم نصوص تيليجرام."""

import io
import logging
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
        return len(
            value.encode("utf-16-le")
        ) // 2

    def take_part(
        remaining: str,
        limit: int,
    ) -> tuple[str, str]:

        if telegram_length(remaining) <= limit:
            return remaining, ""

        cut = 0
        used = 0

        for index, character in enumerate(remaining):

            character_length = telegram_length(
                character
            )

            if used + character_length > limit:
                break

            used += character_length
            cut = index + 1

        candidate = remaining[:cut]

        # عدم قطع الكلمة إن أمكن
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
            break

        parts.append(part)

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

    مهم:
    لا يبحث في بقية المجلات.

    كل مجلة لها تسلسل مستقل.
    """

    pdf_path = (
        config.MAGAZINE_DIR
        + "/"
        + pdf_file
    )

    if not pdf_path.lower().endswith(".pdf"):
        logging.warning(
            f"[MAGAZINE] الملف ليس PDF: {pdf_file}"
        )
        return None

    import os

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
            f"[MAGAZINE] لا توجد صفحات في: {pdf_file}"
        )
        return None

    logging.info(
        f"[MAGAZINE] فحص {pdf_file} — "
        f"{total} صفحة"
    )

    for page_num in range(total):

        page = pdf_manager.render_page(
            pdf_path,
            page_num,
        )

        if page is None:
            continue

        if history.is_page_published(
            page.page_hash
        ):
            logging.info(
                f"[MAGAZINE] "
                f"{pdf_file} — "
                f"صفحة {page_num + 1} منشورة سابقاً — SKIP"
            )
            continue

        logging.info(
            f"[MAGAZINE] صفحة جديدة: "
            f"{pdf_file} — "
            f"{page_num + 1}/{total}"
        )

        return page

    logging.info(
        f"[MAGAZINE] انتهت جميع صفحات: "
        f"{pdf_file}"
    )

    return None


# ==========================================
# نشر مجلة محددة
# ==========================================

async def publish_magazine_file(
    bot: Bot,
    pdf_file: str,
    post_type: str,
) -> None:
    """
    نشر صفحة واحدة من مجلة محددة.

    الصفحة الطويلة قد تنتج:
    - صورة + نص أول
    - تكملة 1
    - تكملة 2
    - ...

    ولا تسجل الصفحة في التاريخ إلا بعد
    نجاح إرسال جميع الأجزاء.
    """

    logging.info(
        f"[MAGAZINE] "
        f"بدء نشر {pdf_file} "
        f"({post_type})"
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

    extracted_text = (
        await vision.extract_text_from_image(
            page.image_bytes
        )
    )

    if extracted_text:
        caption = extracted_text.strip()
    else:
        logging.warning(
            "[MAGAZINE] لم يتم استخراج نص."
        )
        caption = ""

    # ======================================
    # إضافة اسم القناة
    # ======================================

    if caption:

        full_text = (
            f"{caption}\n\n"
            f"القناة: "
            f"{config.CHANNEL_USERNAME}"
        )

    else:

        full_text = (
            f"القناة: "
            f"{config.CHANNEL_USERNAME}"
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
    # النشر
    # ======================================

    try:

        logging.info(
            f"[MAGAZINE] "
            f"نشر {pdf_file} "
            f"صفحة {page.page_number + 1}"
        )

        # ------------------------------
        # الصورة
        # ------------------------------

        photo = io.BytesIO(
            page.image_bytes
        )

        photo.name = (
            f"{pdf_file}_"
            f"page_{page.page_number + 1}.jpg"
        )

        message = await bot.send_photo(
            chat_id=config.CHANNEL_USERNAME,
            photo=photo,
            caption=caption_part,
        )

        logging.info(
            "[MAGAZINE] تم نشر الصورة بنجاح."
        )

        # ------------------------------
        # التكملات
        # ------------------------------

        for index, part in enumerate(
            continuation_parts,
            start=2,
        ):

            await bot.send_message(
                chat_id=config.CHANNEL_USERNAME,
                text=part,
            )

            logging.info(
                f"[MAGAZINE] "
                f"تم إرسال تكملة {index} "
                f"للصفحة "
                f"{page.page_number + 1}"
            )

        # ==================================
        # تسجيل الصفحة بعد نجاح كل شيء
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
            f"[MAGAZINE] "
            f"تم تسجيل الصفحة "
            f"{page.page_number + 1} "
            f"من {pdf_file} "
            f"كسابقة نشر."
        )

    except TelegramError as e:

        logging.error(
            f"[MAGAZINE] خطأ Telegram "
            f"أثناء نشر {pdf_file}: {e}"
        )

    except Exception as e:

        logging.error(
            f"[MAGAZINE] خطأ غير متوقع "
            f"أثناء نشر {pdf_file}: {e}"
        )


# ==========================================
# نشر المجلة الأولى والثانية صباحاً
# ==========================================

async def publish_morning(
    bot: Bot,
) -> None:
    """
    النشر الصباحي:

    المجلة الأولى → صفحة
    القيادة → صفحة
    """

    logging.info(
        "========== النشر الصباحي =========="
    )

    # المجلة الأولى
    try:
        await publish_magazine_file(
            bot,
            config.MAGAZINE_1_FILE,
            "morning",
        )
    except Exception as e:
        logging.error(
            f"[MAGAZINE] "
            f"فشل نشر المجلة الأولى صباحاً: {e}"
        )

    # المجلة الثانية
    try:
        await publish_magazine_file(
            bot,
            config.MAGAZINE_2_FILE,
            "morning",
        )
    except Exception as e:
        logging.error(
            f"[MAGAZINE] "
            f"فشل نشر القيادة صباحاً: {e}"
        )

    logging.info(
        "========== انتهى النشر الصباحي =========="
    )


# ==========================================
# نشر المجلة الأولى والثانية مساءً
# ==========================================

async def publish_evening(
    bot: Bot,
) -> None:
    """
    النشر المسائي:

    المجلة الأولى → صفحة
    القيادة → صفحة
    """

    logging.info(
        "========== النشر المسائي =========="
    )

    # المجلة الأولى
    try:
        await publish_magazine_file(
            bot,
            config.MAGAZINE_1_FILE,
            "evening",
        )
    except Exception as e:
        logging.error(
            f"[MAGAZINE] "
            f"فشل نشر المجلة الأولى مساءً: {e}"
        )

    # المجلة الثانية
    try:
        await publish_magazine_file(
            bot,
            config.MAGAZINE_2_FILE,
            "evening",
        )
    except Exception as e:
        logging.error(
            f"[MAGAZINE] "
            f"فشل نشر القيادة مساءً: {e}"
        )

    logging.info(
        "========== انتهى النشر المسائي =========="
        )
