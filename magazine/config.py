"""إعدادات نظام المجلة — يقرأ المتغيرات البيئية الموجودة فقط."""

import os
import logging
import unicodedata

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ==========================================
# Telegram
# ==========================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "ضع_توكن_البوت_هنا",
)

CHANNEL_USERNAME = os.getenv(
    "CHANNEL_USERNAME",
    "@Athar_Dz_Islamic",
)


# ==========================================
# Groq
# ==========================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "ضع_مفتاح_جروج_هنا",
)


# ==========================================
# مجلد المجلات
# ==========================================

MAGAZINE_DIR = os.getenv(
    "PDF_PATH",
    "magazine_pdf",
)


# ==========================================
# ملفات المجلات
# ==========================================

# المجلة الأولى
MAGAZINE_1_FILE = os.getenv(
    "MAGAZINE_1_FILE",
    "magazine_issue_5.pdf",
)

# المجلة الثانية
MAGAZINE_2_FILE = os.getenv(
    "MAGAZINE_2_FILE",
    "القياده.pdf",
)


def resolve_magazine_file(filename: str) -> str:
    """يرجع اسم الملف الفعلي مع دعم اختلافات الكتابة العربية البسيطة."""
    direct_path = os.path.join(MAGAZINE_DIR, filename)
    if os.path.isfile(direct_path):
        return filename

    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        # بعض الملفات تُكتب بالتاء المربوطة، وأخرى بالهاء في الاسم نفسه.
        return value.replace("ة", "ه").casefold()

    wanted = normalized(filename)
    try:
        candidates = sorted(
            name
            for name in os.listdir(MAGAZINE_DIR)
            if name.lower().endswith(".pdf")
            and normalized(name) == wanted
        )
    except OSError:
        candidates = []

    if candidates:
        resolved = candidates[0]
        logging.warning(
            f"[MAGAZINE] اسم الملف مضبوط كـ {filename!r}، "
            f"وسيتم استخدام الملف الموجود {resolved!r}."
        )
        return resolved

    return filename


# ==========================================
# حدود Telegram
# ==========================================

TG_CAPTION_LIMIT = 1024
TG_MESSAGE_LIMIT = 4096


# ==========================================
# جودة الصور
# ==========================================

PDF_DPI = int(
    os.getenv(
        "PDF_DPI",
        "200",
    )
)


# ==========================================
# نموذج Groq للرؤية
# ==========================================

GROQ_VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL",
    "llama-3.2-90b-vision-preview",
)


# ==========================================
# التذييل الإجباري
# ==========================================

MANDATORY_FOOTER = (
    "هذي القناة هي صدقه جارية للأخت الأندلسية أم عقيدة وحمزة "
    "غفر الله لها وجعلها في ميزان حسناتها."
)


# ==========================================
# السجل المحلي
# ==========================================

LOCAL_HISTORY_FILE = os.getenv(
    "LOCAL_HISTORY_FILE",
    "data/magazine_history.json",
)


# ==========================================
# Supabase
# ==========================================

SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("VITE_SUPABASE_URL")
)

SUPABASE_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY")
)


# ==========================================
# Logging
# ==========================================

logging.info(
    f"[MAGAZINE] مجلد المجلة: {MAGAZINE_DIR}"
)

logging.info(
    f"[MAGAZINE] المجلة الأولى: {MAGAZINE_1_FILE}"
)

logging.info(
    f"[MAGAZINE] المجلة الثانية: {MAGAZINE_2_FILE}"
)

logging.info(
    f"[MAGAZINE] نموذج الرؤية: {GROQ_VISION_MODEL}"
)
