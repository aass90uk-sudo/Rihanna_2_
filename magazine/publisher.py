"""ناشر المجلة — يختار صفحة جديدة، يتحقق من التكرار، يستخرج النص، ويرسل لـ Telegram."""
import logging
from typing import Optional, Callable

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from . import config, pdf_manager, history, vision


def _split_text(text: str, first_limit: int, next_limit: int) -> list[str]:
    """يقسّم النص إلى أجزاء مع احترام حدود تيليجرام."""
    parts = []
    if not text:
        return parts
    if len(text) <= first_limit:
        parts.append(text)
        return parts
    parts.append(text[:first_limit])
    remaining = text[first_limit:]
    while remaining:
        parts.append(remaining[:next_limit])
        remaining = remaining[next_limit:]
    return parts


def _find_next_unpublished_page() -> Optional[pdf_manager.PageImage]:
    """يبحث عن أول صفحة غير منشورة عبر جميع ملفات PDF الموجودة."""
    pdfs = pdf_manager.list_pdf_files()
    if not pdfs:
        logging.warning("[MAGAZINE] لا توجد ملفات PDF في مجلد المجلة.")
        return None

    for pdf_path in pdfs:
        total = pdf_manager.get_total_pages(pdf_path)
        logging.info(f"[MAGAZINE] Total pages: {total} في {pdf_path}")

        for page_num in range(total):
            page = pdf_manager.render_page(pdf_path, page_num)
            if page is None:
                continue

            if history.is_page_published(page.page_hash):
                logging.info("[MAGAZINE] Page already published - SKIP")
                continue

            logging.info("[MAGAZINE] New page found")
            return page

    logging.info("[MAGAZINE] لا توجد صفحات جديدة — تم نشر كل الصفحات المتاحة.")
    return None


async def publish_magazine_page(bot: Bot, post_type: str) -> None:
    """ينشر صفحة مجلة جديدة لنوع معين (morning/evening) مع منع التكرار."""
    logging.info(f"[MAGAZINE] Searching for new issue... ({post_type})")

    page = _find_next_unpublished_page()
    if page is None:
        logging.info(f"[MAGAZINE] No new {post_type} magazine page available.")
        return

    # استخراج النص من نفس الصورة المراد نشرها
    logging.info("[MAGAZINE] Extracting text...")
    extracted_text = await vision.extract_text_from_image(page.image_bytes)

    if not extracted_text:
        logging.warning("[MAGAZINE] لم يُستخرج نص من الصورة — سيُنشر بدون نص.")
        caption = ""
    else:
        caption = extracted_text

    # إضافة اسم القناة في النهاية
    full_text = f"{caption}\n\nالقناة: {config.CHANNEL_USERNAME}" if caption else f"القناة: {config.CHANNEL_USERNAME}"

    parts = _split_text(full_text, config.TG_CAPTION_LIMIT, config.TG_MESSAGE_LIMIT)
    caption_part = parts[0] if parts else ""
    continuation_parts = parts[1:] if len(parts) > 1 else []

    try:
        logging.info("[MAGAZINE] Publishing to Telegram...")

        import io
        photo = io.BytesIO(page.image_bytes)
        photo.name = f"page_{page.page_number + 1}.jpg"

        msg = await bot.send_photo(
            chat_id=config.CHANNEL_USERNAME,
            photo=photo,
            caption=caption_part,
            parse_mode=ParseMode.MARKDOWN,
        )
        logging.info("[MAGAZINE] Published successfully")

        # إرسال بقية النص إن وُجد
        for idx, part in enumerate(continuation_parts, start=2):
            await bot.send_message(
                chat_id=config.CHANNEL_USERNAME,
                text=part,
                parse_mode=ParseMode.MARKDOWN,
            )
            logging.info(f"[MAGAZINE] تم إرسال الجزء {idx} من النص")

        # تسجيل الصفحة بعد نجاح النشر
        message_id = getattr(msg, "message_id", None) if msg else None
        history.record_published(
            page_hash=page.page_hash,
            pdf_file=page.pdf_file,
            page_number=page.page_number,
            post_type=post_type,
            telegram_message_id=message_id,
        )

    except TelegramError as e:
        logging.error(f"[MAGAZINE] خطأ Telegram أثناء النشر: {e}")
    except Exception as e:
        logging.error(f"[MAGAZINE] خطأ غير متوقع أثناء النشر: {e}")


async def publish_morning(bot: Bot) -> None:
    """منشور الصباح — يبحث عن صفحة صباحية جديدة."""
    await publish_magazine_page(bot, "morning")


async def publish_evening(bot: Bot) -> None:
    """منشور المساء — يبحث عن صفحة مسائية جديدة."""
    await publish_magazine_page(bot, "evening")
