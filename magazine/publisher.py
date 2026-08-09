"""ناشر المجلة مع استخراج النص ومنع التكرار وتقسيم نصوص تيليجرام."""

import io
import logging
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from . import config, pdf_manager, history, vision


def _split_text(
    text: str,
    first_limit: int,
    next_limit: int,
) -> list[str]:
    """
    تقسيم النص حسب حدود تيليجرام.

    الجزء الأول مخصص لتعليق الصورة، والأجزاء التالية
    ترسل كمنشورات نصية مستقلة.

    يتم الاعتماد على UTF-16 لأن تيليجرام يحسب طول النص
    بهذه الطريقة، مع محاولة عدم قطع الكلمات.
    """

    if not text:
        return []

    def telegram_length(value: str) -> int:
        """حساب طول النص بطريقة UTF-16 المستخدمة في تيليجرام."""

        return len(value.encode("utf-16-le")) // 2

    def take_part(
        remaining: str,
        limit: int,
    ) -> tuple[str, str]:
        """أخذ جزء لا يتجاوز الحد وإرجاع النص المتبقي."""

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

        candidate = remaining[:cut]

        # نفضل الفصل عند سطر جديد أو مسافة حتى لا نقطع الكلمة.
        boundary = max(
            candidate.rfind("\n"),
            candidate.rfind(" "),
        )

        if boundary > 0:
            # إبقاء الفاصل في الجزء السابق يحافظ على النص كما هو.
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

        # حماية إضافية في حال وجود حد صغير جداً.
        if not part:
            part, remaining = take_part(
                remaining,
                limit,
            )

        parts.append(part)
        limit = next_limit

    return parts


def _find_next_unpublished_page() -> Optional[pdf_manager.PageImage]:
    """
    البحث عن أول صفحة غير منشورة من جميع ملفات PDF.
    """

    pdfs = pdf_manager.list_pdf_files()

    if not pdfs:
        logging.warning(
            "[MAGAZINE] لا توجد ملفات PDF في مجلد المجلة."
        )
        return None

    for pdf_path in pdfs:
        total = pdf_manager.get_total_pages(pdf_path)

        logging.info(
            f"[MAGAZINE] Total pages: {total} في {pdf_path}"
        )

        for page_num in range(total):
            page = pdf_manager.render_page(
                pdf_path,
                page_num,
            )

            if page is None:
                continue

            if history.is_page_published(page.page_hash):
                logging.info(
                    "[MAGAZINE] Page already published - SKIP"
                )
                continue

            logging.info("[MAGAZINE] New page found")
            return page

    logging.info(
        "[MAGAZINE] لا توجد صفحات جديدة — "
        "تم نشر كل الصفحات المتاحة."
    )

    return None


async def publish_magazine_page(
    bot: Bot,
    post_type: str,
) -> None:
    """
    نشر صفحة مجلة جديدة.

    يتم إرسال:
    1. الصورة مع الجزء الأول من النص.
    2. بقية النص في منشورات مستقلة متتابعة.
    3. تسجيل الصفحة بعد نجاح جميع عمليات الإرسال.
    """

    logging.info(
        f"[MAGAZINE] Searching for new issue... ({post_type})"
    )

    page = _find_next_unpublished_page()

    if page is None:
        logging.info(
            f"[MAGAZINE] No new {post_type} magazine page available."
        )
        return

    # استخراج النص من نفس الصورة التي سيتم نشرها.
    logging.info("[MAGAZINE] Extracting text...")

    extracted_text = await vision.extract_text_from_image(
        page.image_bytes
    )

    if not extracted_text:
        logging.warning(
            "[MAGAZINE] لم يُستخرج نص من الصورة — "
            "سيُنشر بدون نص."
        )
        caption = ""
    else:
        caption = extracted_text.strip()

    # إضافة اسم القناة إلى نهاية النص.
    if caption:
        full_text = (
            f"{caption}\n\n"
            f"القناة: {config.CHANNEL_USERNAME}"
        )
    else:
        full_text = (
            f"القناة: {config.CHANNEL_USERNAME}"
        )

    # الجزء الأول للصورة، والبقية لمنشورات مستقلة.
    parts = _split_text(
        full_text,
        config.TG_CAPTION_LIMIT,
        config.TG_MESSAGE_LIMIT,
    )

    caption_part = parts[0] if parts else ""
    continuation_parts = (
        parts[1:]
        if len(parts) > 1
        else []
    )

    try:
        logging.info(
            "[MAGAZINE] Publishing to Telegram..."
        )

        photo = io.BytesIO(page.image_bytes)
        photo.name = (
            f"page_{page.page_number + 1}.jpg"
        )

        # المنشور الأول: صورة الصفحة مع الجزء الأول من النص.
        message = await bot.send_photo(
            chat_id=config.CHANNEL_USERNAME,
            photo=photo,
            caption=caption_part,
        )

        logging.info(
            "[MAGAZINE] Published image successfully"
        )

        # نشر بقية النص كمنشورات مستقلة مباشرة بعد منشور الصورة.
        for index, part in enumerate(
            continuation_parts,
            start=2,
        ):
            await bot.send_message(
                chat_id=config.CHANNEL_USERNAME,
                text=part,
            )

            logging.info(
                f"[MAGAZINE] تم إرسال الجزء {index} من النص"
            )

        # تسجيل الصفحة بعد نجاح الصورة وجميع الأجزاء.
        message_id = (
            getattr(message, "message_id", None)
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
            "[MAGAZINE] تم تسجيل الصفحة كسابقة النشر."
        )

    except TelegramError as e:
        logging.error(
            f"[MAGAZINE] خطأ Telegram أثناء النشر: {e}"
        )

    except Exception as e:
        logging.error(
            f"[MAGAZINE] خطأ غير متوقع أثناء النشر: {e}"
        )


async def publish_morning(bot: Bot) -> None:
    """نشر صفحة الصباح."""

    await publish_magazine_page(
        bot,
        "morning",
    )


async def publish_evening(bot: Bot) -> None:
    """نشر صفحة المساء."""

    await publish_magazine_page(
        bot,
        "evening",
    )
