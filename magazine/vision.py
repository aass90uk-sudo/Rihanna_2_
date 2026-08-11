"""استخراج النص من صورة الصفحة عبر Groq Vision (llama-3.2-90b-vision-preview)."""
import asyncio
import base64
import logging
from typing import Optional

from groq import Groq

from . import config

_client: Optional[Groq] = None

def _get_client() -> Optional[Groq]:
    global _client
    if _client is not None:
        return _client
    if not config.GROQ_API_KEY or config.GROQ_API_KEY == "ضع_مفتاح_جروج_هنا":
        logging.warning("[MAGAZINE] GROQ_API_KEY غير مضبوط — لن يعمل استخراج النص بالرؤية.")
        return None
    _client = Groq(api_key=config.GROQ_API_KEY)
    return _client

# تعليمات صارمة لاستخراج النص فقط بدون تغيير أو إضافة
_OCR_PROMPT = (
    "استخرج النص الموجود في صورة صفحة المجلة بدقة شديدة، "
    "وحافظ على ترتيب النص، ولا تضف أي كلام من عندك، "
    "ولا تلخص المحتوى، ولا تغير الكلمات. "
    "النص الناتج يجب أن يكون هو النص الموجود في الصفحة نفسها."
)

def _call_vision(image_bytes: bytes) -> str:
    """استدعاء متزامن لنموذج الرؤية — يُغلّف بـ run_in_executor."""
    client = _get_client()
    if client is None:
        return ""

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64}"

    response = client.chat.completions.create(
        model=config.GROQ_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0.0,
        max_tokens=4000,
    )
    return response.choices[0].message.content.strip()

async def extract_text_from_image(image_bytes: bytes) -> str:
    """يستخرج النص من صورة الصفحة عبر Groq Vision (async)."""
    client = _get_client()
    if client is None:
        return ""

    try:
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, _call_vision, image_bytes)
        logging.info(f"[MAGAZINE] Extracting text... (طول النص: {len(text)})")
        return text
    except Exception as e:
        logging.error(f"[MAGAZINE] خطأ أثناء استخراج النص بالرؤية: {e}")
        return ""
        
