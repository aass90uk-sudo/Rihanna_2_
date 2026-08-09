"""إعدادات نظام المجلة — يقرأ المتغيرات البيئية الموجودة فقط."""
import os
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_توكن_البوت_هنا")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@Athar_Dz_Islamic")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "ضع_مفتاح_جروج_هنا")

# مجلد المجلة الافتراضي — يمكن تغييره عبر PDF_PATH
MAGAZINE_DIR = os.getenv("PDF_PATH", "magazine_pdf")

# حدود تيليجرام
TG_CAPTION_LIMIT = 1024
TG_MESSAGE_LIMIT = 4096

# جودة الصورة المستخرجة من PDF
PDF_DPI = int(os.getenv("PDF_DPI", "200"))

# نموذج Groq للرؤية (استخراج النص من الصورة)
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-3.2-90b-vision-preview")

# التذييل الإجباري للمنشورات الدورية (بدون إيموجي)
MANDATORY_FOOTER = (
    "هذي القناة هي صدقه جارية للأخت الأندلسية أم عقيدة وحمزة "
    "غفر الله لها وجعلها في ميزان حسناتها."
)

# ملف السجل المحلي الاحتياطي (يُستخدم فقط إذا لم تتوفر Supabase)
LOCAL_HISTORY_FILE = os.getenv("LOCAL_HISTORY_FILE", "data/magazine_history.json")

# Supabase (اختياري — يستخدمه البوت إذا كانت المتغيرات موجودة)
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")

logging.info(f"[MAGAZINE] مجلد المجلة: {MAGAZINE_DIR}")
logging.info(f"[MAGAZINE] نموذج الرؤية: {GROQ_VISION_MODEL}")
