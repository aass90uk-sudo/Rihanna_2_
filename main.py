import os
import asyncio
import logging
import random

# ==========================================
# تفعيل Logging منذ بداية تشغيل البرنامج
# ==========================================

print("========== STARTING TELEGRAM BOT ==========")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)

logging.info("========== MAIN.PY STARTED ==========")

# ==========================================
# مكتبات Telegram
# ==========================================

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

# ==========================================
# مكتبات الجدولة والذكاء الاصطناعي
# ==========================================

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq
import pytz

# ==========================================
# نظام المجلات
# ==========================================

from magazine import config as mag_config
from magazine.publisher import publish_morning, publish_evening

# ==========================================
# إعدادات البوت
# ==========================================

TELEGRAM_TOKEN = mag_config.TELEGRAM_TOKEN
CHANNEL_USERNAME = mag_config.CHANNEL_USERNAME
GROQ_API_KEY = mag_config.GROQ_API_KEY

TG_CAPTION_LIMIT = mag_config.TG_CAPTION_LIMIT
TG_MESSAGE_LIMIT = mag_config.TG_MESSAGE_LIMIT

MANDATORY_FOOTER = mag_config.MANDATORY_FOOTER

# ==========================================
# تهيئة Groq
# ==========================================

groq_client = (
    Groq(api_key=GROQ_API_KEY)
    if GROQ_API_KEY
    and GROQ_API_KEY != "ضع_مفتاح_جروج_هنا"
    else None
)

# ==========================================
# منشور دوري كل 3 ساعات
# ==========================================

async def generate_motivational_content():
    """توليد منشور إيماني وتوجيهي."""

    fallback_messages = [
        (
            "نسأل الله أن يثبت القلوب على الخير، "
            "وأن يرزقنا الصبر والإخلاص وحسن العمل.\n\n"
            "#ثبات\n"
            "#الصبر"
        ),
        (
            "اجعلوا العلم والوعي والصبر أساساً في حياتكم، "
            "وكونوا من أهل الكلمة الطيبة والعمل الصالح.\n\n"
            "#وعي\n"
            "#العمل_الصالح"
        ),
        (
            "الثبات على الخير يحتاج إلى صبر وإخلاص، "
            "فاستعينوا بالله وأكثروا من الدعاء والعمل الصالح.\n\n"
            "#الإخلاص\n"
            "#الدعاء"
        ),
    ]

    if not groq_client:
        return random.choice(fallback_messages)

    prompt = """
أكتب منشوراً إيمانياً وتوجيهياً قصيراً ومؤثراً.

المطلوب:
- نصيحة عن الصبر والثبات والإخلاص والوعي.
- أسلوب عربي جميل ومؤثر.
- لا تستخدم أي إيموجي أو رموز تعبيرية.
- أضف هاشتاجات مناسبة في النهاية.
- كل هاشتاج في سطر مستقل.
- المنشور فقرة أو فقرتان قصيرتان.
- أعد النص مباشرة بدون مقدمات.
"""

    try:
        loop = asyncio.get_running_loop()

        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
            ),
        )

        return response.choices[0].message.content

    except Exception as e:
        logging.error(
            f"خطأ في Groq أثناء توليد المنشور الدوري: {e}"
        )

        return random.choice(fallback_messages)

async def publish_interval_post(bot: Bot):
    """النشر التلقائي كل 3 ساعات."""

    try:
        logging.info(
            "جاري إعداد ونشر المنشور الدوري..."
        )

        content = await generate_motivational_content()

        final_post = (
            f"{content}\n\n"
            f"{MANDATORY_FOOTER}"
        )

        await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=final_post,
            parse_mode=ParseMode.MARKDOWN,
        )

        logging.info(
            "تم نشر المنشور الدوري بنجاح."
        )

    except TelegramError as e:

        logging.error(
            f"خطأ Telegram في المنشور الدوري: {e}"
        )

    except Exception as e:

        logging.error(
            f"خطأ غير متوقع في المنشور الدوري: {e}"
        )

# ==========================================
# التعليق على منشورات القناة
# ==========================================

async def generate_channel_post_comment(
    post_text: str,
) -> str:

    fallback = (
        "بارك الله فيكم على هذا المنشور القيّم.\n"
        "نسأل الله أن ينفع به ويجعله في ميزان الحسنات."
    )

    if not groq_client:
        return fallback

    prompt = f"""
أنت مشرف متفاعل في مجموعة تيليجرام.

نص المنشور:
{post_text[:1000]}

اكتب تعليقاً قصيراً ومفيداً ودافئاً.
لا تستخدم أي إيموجي.
لا يزيد التعليق عن خمسة أسطر.
اكتب التعليق مباشرة.
"""

    try:
        loop = asyncio.get_running_loop()

        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=200,
            ),
        )

        return response.choices[0].message.content

    except Exception as e:

        logging.error(
            f"خطأ في Groq أثناء توليد التعليق: {e}"
        )

        return fallback

# ==========================================
# الرد على رسائل الأعضاء
# ==========================================

async def generate_islamic_reply(
    user_message: str,
    user_name: str,
) -> str:

    fallback = (
        f"أهلاً بك أخي/أختي {user_name}.\n"
        "جزاك الله خيراً وبارك الله فيك."
    )

    if not groq_client:
        return fallback

    prompt = f"""
أنت مساعد ومشرف في مجموعة تيليجرام.

رسالة العضو ({user_name}):
{user_message}

المطلوب:
- رد مختصر ومفيد ومؤدب.
- إذا كانت تحية فرد بتحية طيبة.
- إذا كان سؤالاً عاماً فأجب بما يناسبه.
- استخدم أسلوباً دافئاً.
- لا تستخدم أي إيموجي.
- لا يزيد الرد عن خمسة أسطر.
- لا تذكر أنك ذكاء اصطناعي.
- اكتب الرد مباشرة.
"""

    try:
        loop = asyncio.get_running_loop()

        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=300,
            ),
        )

        return response.choices[0].message.content

    except Exception as e:

        logging.error(
            f"خطأ في Groq أثناء توليد الرد: {e}"
        )

        return fallback

# ==========================================
# معالجة رسائل المجموعة
# ==========================================

async def handle_group_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        message = update.message

        if not message or not message.text:
            return

        user_text = message.text.strip()

        is_channel_post = (
            message.sender_chat is not None
            and message.sender_chat.type == "channel"
        )

        if is_channel_post:

            logging.info(
                "منشور قناة جديد في المجموعة، "
                "جاري التعليق عليه..."
            )

            await context.bot.send_chat_action(
                chat_id=message.chat_id,
                action="typing",
            )

            comment = (
                await generate_channel_post_comment(
                    user_text
                )
            )

            await message.reply_text(
                text=comment,
                parse_mode=ParseMode.MARKDOWN,
            )

            return

        if (
            message.from_user
            and message.from_user.is_bot
        ):
            return

        user_name = (
            message.from_user.first_name
            if message.from_user
            else "عضو"
        )

        logging.info(
            f"رسالة من {user_name}: "
            f"{user_text[:50]}..."
        )

        await context.bot.send_chat_action(
            chat_id=message.chat_id,
            action="typing",
        )

        reply_text = await generate_islamic_reply(
            user_text,
            user_name,
        )

        await message.reply_text(
            text=reply_text,
            parse_mode=ParseMode.MARKDOWN,
        )

    except TelegramError as e:

        logging.error(
            f"خطأ Telegram في معالجة الرسالة: {e}"
        )

    except Exception as e:

        logging.error(
            f"خطأ غير متوقع في معالجة الرسالة: {e}"
        )

# ==========================================
# أمر اختبار الصباح
# ==========================================

async def test_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        await update.message.reply_text(
            "جاري اختبار نشر المجلات والمنشور الدوري..."
        )

        await publish_morning(
            context.bot
        )

        await publish_interval_post(
            context.bot
        )

        await update.message.reply_text(
            "تم إرسال منشورات الاختبار بنجاح."
        )

    except Exception as e:

        await update.message.reply_text(
            f"حدث خطأ أثناء الاختبار: {e}"
        )

# ==========================================
# أمر اختبار المساء
# ==========================================

async def test_evening_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        await update.message.reply_text(
            "جاري اختبار نشر صفحات المساء..."
        )

        await publish_evening(
            context.bot
        )

        await update.message.reply_text(
            "تم إرسال صفحات المساء بنجاح."
        )

    except Exception as e:

        await update.message.reply_text(
            f"حدث خطأ أثناء الاختبار: {e}"
        )

# ==========================================
# تشغيل الجدولة
# ==========================================

async def post_init(
    application: Application,
) -> None:

    bot = application.bot

    # توقيت الجزائر
    tz = pytz.timezone(
        "Africa/Algiers"
    )

    scheduler = AsyncIOScheduler(
        timezone=tz
    )

    # ======================================
    # المجلات صباحاً
    # ======================================

    scheduler.add_job(
        publish_morning,
        "cron",
        hour=8,
        minute=0,
        args=[bot],
    )

    # ======================================
    # المجلات مساءً
    # ======================================

    scheduler.add_job(
        publish_evening,
        "cron",
        hour=19,
        minute=0,
        args=[bot],
    )

    # ======================================
    # المنشور الدوري كل 3 ساعات
    # ======================================

    scheduler.add_job(
        publish_interval_post,
        "interval",
        hours=3,
        args=[bot],
    )

    scheduler.start()

    application.bot_data[
        "scheduler"
    ] = scheduler

    logging.info(
        "تم تشغيل الجدولة بنجاح."
    )

    logging.info(
        "موعد المجلات: 08:00 و 19:00 "
        "بتوقيت Africa/Algiers."
    )

# ==========================================
# إيقاف الجدولة
# ==========================================

async def post_stop(
    application: Application,
) -> None:

    scheduler = application.bot_data.get(
        "scheduler"
    )

    if (
        scheduler
        and scheduler.running
    ):

        scheduler.shutdown()

        logging.info(
            "تم إيقاف الجدولة بأمان."
        )

# ==========================================
# تشغيل البوت
# ==========================================

def main():

    logging.info(
        "جاري إنشاء تطبيق Telegram..."
    )

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # ======================================
    # أوامر الاختبار
    # ======================================

    application.add_handler(
        CommandHandler(
            "test",
            test_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "test_evening",
            test_evening_command,
        )
    )

    # ======================================
    # الرسائل النصية
    # ======================================

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_group_message,
        )
    )

    logging.info(
        "البوت يعمل ومستعد للاستجابة..."
    )

    logging.info(
        "بدء Telegram polling..."
    )

    application.run_polling(
        drop_pending_updates=True
    )

# ==========================================
# نقطة البداية
# ==========================================

if __name__ == "__main__":

    main()
        
