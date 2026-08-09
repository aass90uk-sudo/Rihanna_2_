import os
import asyncio
import logging
import random
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq
import pytz

# نظام المجلة الجديد (استخراج صفحات PDF + منع التكرار بالـ Hash)
from magazine import config as mag_config
from magazine.publisher import publish_morning, publish_evening

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==========================================
# 🛠️ إعدادات المتغيرات البيئية والمعلومات الأساسية
# ==========================================
TELEGRAM_TOKEN = mag_config.TELEGRAM_TOKEN
CHANNEL_USERNAME = mag_config.CHANNEL_USERNAME
GROQ_API_KEY = mag_config.GROQ_API_KEY

# حدود تيليجرام
TG_CAPTION_LIMIT = mag_config.TG_CAPTION_LIMIT   # الحد الأقصى لنص صورة تيليجرام
TG_MESSAGE_LIMIT = mag_config.TG_MESSAGE_LIMIT   # الحد الأقصى لرسالة نصية عادية

# التذييل الإجباري لمنشورات كل 3 ساعات (بدون إيموجي)
MANDATORY_FOOTER = mag_config.MANDATORY_FOOTER

# تهيئة مكتبة جروج (Groq) — تُستخدم للمنشورات الدورية والردود (نصوص)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY and GROQ_API_KEY != "ضع_مفتاح_جروج_هنا" else None


# ==========================================
# 🔄 وظيفة النشر كل 3 ساعات عبر جروج (Groq)
# ==========================================
async def generate_motivational_content():
    """توليد توجيهات ونصائح تحفيزية بدون إيموجي ومع هاشتاجات مرتبة"""
    fallback_messages = [
        "إلى الإخوة والأخوات الموحدين: ثباتكم على الحق هو الحصن المنيع للأمة. استعينوا بالله ولا تعجزوا، وكونوا دائماً يداً واحدة ودرعاً حامياً لقضايا أمتكم الإسلامية.\n\n#ثبات_الموحدين\n#سبحان_الله",
        "نصيحة للموحدين المناصرين: اجعلوا عملكم خالصاً لوجه الله، وتسلحوا بالوعي والعلم، واعلموا أن كلمة الحق ونصرة المظلوم هي سهم في حماية الأمة ودفع الظلم عنها.\n\n#نصرة_الحق\n#الحمدلله_ربي",
        "يا أبناء الأمة الإسلامية: إن الأمة اليوم بأشد الحاجة إلى الوعي والثبات. كونوا درعاً للأمة ونوراً يضيء طريق الموحدين بالتذكير والدعاء والنصرة بالكلمة الطيبة.\n\n#وعي_الأمة\n#الله_أكبر"
    ]

    if not groq_client:
        return random.choice(fallback_messages)

    prompt = """
أكتب منشوراً إيمانياً وتوجيهياً قصيراً ومؤثراً وموجهاً للإخوة والأخوات (الموحدين المناصرين).
المواضيع المطلوبة:
1. نصائح وتوجيهات هامة للموحدين في الثبات، الصبر، الإخلاص، والوعي.
2. رسائل تحفيزية ومشجعة تحثهم على أن يكونوا درعاً حامياً للأمة الإسلامية ونصرة قضاياها بالكلمة والحق.

التعليمات الصارمة:
- أسلوب قوي، إيماني، وبليغ.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية نهائياً.
- أضف هاشتاجات إسلامية مناسبة في النهاية بحيث يكون كل هاشتاج في سطر منفصل، مثل:
#تنظيم_قاعدة_الجهاد
#أنصار_الشريعة
#ولاية_حضرموت
- الطول: فقرة إلى فقرتين قصيرة فقط.
- اعد النص المكتوب مباشرة بدون أي مقدمات أو كلام جانبي.
"""
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في جروج أثناء توليد منشور الـ 3 ساعات: {e}")
        return random.choice(fallback_messages)


async def publish_interval_post(bot: Bot):
    """النشر التلقائي كل 3 ساعات مع التذييل الإجباري"""
    try:
        logging.info("جاري إعداد ونشر المنشور الدوري بواسطة جروج (كل 3 ساعات)...")
        content = await generate_motivational_content()

        final_post = f"{content}\n\n{MANDATORY_FOOTER}"

        await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=final_post,
            parse_mode=ParseMode.MARKDOWN
        )
        logging.info("تم نشر المنشور الدوري بنجاح.")

    except TelegramError as e:
        logging.error(f"خطأ في إرسال المنشور الدوري على التليجرام: {e}")
    except Exception as e:
        logging.error(f"حدث خطأ في عملية النشر الدوري: {e}")


# ==========================================
# 💬 الرد والتفاعل مع رسائل الأعضاء والمجموعة
# ==========================================
async def generate_channel_post_comment(post_text: str) -> str:
    """توليد تعليق إسلامي تلقائي على منشورات القناة في المجموعة بدون إيموجي"""
    fallback = (
        "بارك الله فيكم على هذا المنشور القيّم.\n"
        "نسأل الله أن ينفع به الأمة ويجعله في ميزان حسنات الجميع."
    )

    if not groq_client:
        return fallback

    prompt = f"""أنت مشرف إسلامي متفاعل في مجموعة تليجرام إسلامية. القناة نشرت هذا المنشور وظهر في المجموعة.

نص المنشور:
{post_text[:1000]}

المطلوب:
- اكتب تعليقاً قصيراً ومحفزاً على هذا المنشور (3 أسطر كحد أقصى).
- أسلوب إيماني دافئ يشجع الإخوة والأخوات على التفاعل والقراءة.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية.
- اكتب التعليق مباشرة بدون مقدمات مع ذكر الدعاء لإخواننا المجاهدين في جزيرة العرب."""

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=200,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في Groq أثناء توليد تعليق منشور القناة: {e}")
        return fallback


async def generate_islamic_reply(user_message: str, user_name: str) -> str:
    """توليد رد إسلامي دافئ على كل رسائل الأعضاء عبر Groq بدون إيموجي"""
    fallback = (
        f"أهلاً بك أخي/أختي {user_name}.\n"
        "جزاك الله خيراً وبارك الله فيك، ونسأل الله أن يثبتنا وإياك على الحق."
    )

    if not groq_client:
        return fallback

    prompt = f"""أنت مساعد ومشرف إسلامي في مجموعة تليجرام، تتحدث بأسلوب لطيف ومحبب ومباشر موجه للإخوة والأخوات الموحدين والمناصرين.

رسالة العضو ({user_name}):
{user_message}

المطلوب:
- أجب أو تفاعل مع الرسالة بشكل مختصر ومفيد ومؤدب ودافئ.
- إذا كانت الرسالة سؤالاً شرعياً أو عاماً، أجب بما يوافق مذهب أهل السنة والجماعة مع الاستشهاد بالدليل إن أمكن.
- إذا كانت مشاركة أو تحية أو تعليقاً، رد بتحية طيبة ودعاء رائع.
- اختم دائماً بدعاء أو جملة تحفيزية قصيرة.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية.
- الرد لا يزيد عن 4 إلى 5 أسطر.
- لا تذكر أبداً أنك ذكاء اصطناعي.
- اكتب الرد مباشرة بدون مقدمات."""

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=300,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في Groq أثناء توليد الرد: {e}")
        return fallback


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة كافة رسائل المجموعة والخاص"""
    try:
        message = update.message
        if not message or not message.text:
            return

        user_text = message.text.strip()

        # ✅ الحالة 1: منشور القناة المستورد تلقائياً للمجموعة
        is_channel_post = (
            message.sender_chat is not None
            and message.sender_chat.type == "channel"
        )

        if is_channel_post:
            logging.info(f"منشور قناة جديد في المجموعة، جاري التعليق عليه...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            comment = await generate_channel_post_comment(user_text)
            await message.reply_text(text=comment, parse_mode=ParseMode.MARKDOWN)
            return

        # تجاهل رسائل البوتات الأخرى
        if message.from_user and message.from_user.is_bot:
            return

        # ✅ الحالة 2: الرد التفاعلي المباشر على كافة رسائل الإخوة والأخوات
        user_name = message.from_user.first_name if message.from_user else "عضو"

        logging.info(f"رسالة من {user_name}: {user_text[:50]}...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
        reply_text = await generate_islamic_reply(user_text, user_name)
        await message.reply_text(text=reply_text, parse_mode=ParseMode.MARKDOWN)

    except TelegramError as e:
        logging.error(f"خطأ Telegram في معالجة الرسالة: {e}")
    except Exception as e:
        logging.error(f"خطأ غير متوقع في معالجة الرسالة: {e}")


# ==========================================
# 🧪 أوامر تجريبية لتجربة النشر الفوري
# ==========================================
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر لتجربة النشر الفوري للمجلة والمنشور الدوري"""
    try:
        await update.message.reply_text("جاري اختبار النشر الفوري للمجلة (صباح) والمنشور الدوري...")
        await publish_morning(context.bot)
        await publish_interval_post(context.bot)
        await update.message.reply_text("تم إرسال المنشورات بنجاح إلى القناة.")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء الاختبار: {e}")


async def test_evening_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر لتجربة نشر صفحة المساء"""
    try:
        await update.message.reply_text("جاري اختبار نشر صفحة المساء...")
        await publish_evening(context.bot)
        await update.message.reply_text("تم إرسال صفحة المساء بنجاح.")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء الاختبار: {e}")


# ==========================================
# ⏰ المحرك والجدولة الرئيسية
# ==========================================
async def post_init(application: Application) -> None:
    """تفعيل جدولة المهام تلقائياً"""
    bot = application.bot
    tz = pytz.timezone("Africa/Algiers")

    scheduler = AsyncIOScheduler(timezone=tz)

    # 1. نشر المجلة — صفحة الصباح (09:00) وصفحة المساء (20:00)
    scheduler.add_job(publish_morning, 'cron', hour=9, minute=0, args=[bot])
    scheduler.add_job(publish_evening, 'cron', hour=20, minute=0, args=[bot])

    # 2. المنشور الدوري (كل 3 ساعات)
    scheduler.add_job(publish_interval_post, 'interval', hours=3, args=[bot])

    scheduler.start()
    application.bot_data['scheduler'] = scheduler
    logging.info("تم تشغيل الجدولة بنجاح...")


async def post_stop(application: Application) -> None:
    """إيقاف الجدولة بأمان"""
    scheduler = application.bot_data.get('scheduler')
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logging.info("تم إيقاف الجدولة بأمان.")


def main():
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # 1. أوامر الاختبار المباشر
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("test_evening", test_evening_command))

    # 2. معالج الرسائل التفاعلي لكافة النصوص
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message)
    )

    logging.info("البوت يعمل واستعد للاستجابة...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
