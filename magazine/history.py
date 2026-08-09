"""سجل الصفحات المنشورة — يستخدم Supabase إن توفر، وإلا ملف JSON محلي."""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from . import config

try:
    from supabase import create_client, Client
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


def _get_supabase_client() -> Optional["Client"]:
    if not _HAS_SUPABASE:
        return None
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        return None
    try:
        return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    except Exception as e:
        logging.error(f"[MAGAZINE] تعذّر الاتصال بـ Supabase: {e}")
        return None


_SB_CLIENT = _get_supabase_client()
_TABLE = "magazine_published_pages"


def _load_local_history() -> dict:
    """يحمّل السجل المحلي من ملف JSON."""
    path = config.LOCAL_HISTORY_FILE
    if not os.path.exists(path):
        return {"published_hashes": [], "records": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"published_hashes": [], "records": []}


def _save_local_history(history: dict) -> None:
    path = config.LOCAL_HISTORY_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def is_page_published(page_hash: str) -> bool:
    """يتحقق هل الصفحة (ببصمتها) سبق نشرها أم لا."""
    if _SB_CLIENT is not None:
        try:
            resp = _SB_CLIENT.table(_TABLE).select("id").eq("page_hash", page_hash).maybeSingle().execute()
            return resp.data is not None
        except Exception as e:
            logging.error(f"[MAGAZINE] خطأ Supabase أثناء فحص التكرار: {e}")

    history = _load_local_history()
    return page_hash in history.get("published_hashes", [])


def record_published(
    page_hash: str,
    pdf_file: str,
    page_number: int,
    post_type: str,
    telegram_message_id: Optional[int] = None,
) -> None:
    """يسجّل صفحة كمنشورة بعد نجاح النشر في Telegram."""
    published_at = datetime.now(timezone.utc).isoformat()

    if _SB_CLIENT is not None:
        try:
            _SB_CLIENT.table(_TABLE).insert({
                "page_hash": page_hash,
                "pdf_file": pdf_file,
                "page_number": page_number,
                "post_type": post_type,
                "telegram_message_id": telegram_message_id,
                "published_at": published_at,
            }).execute()
            logging.info("[MAGAZINE] History saved (Supabase)")
            return
        except Exception as e:
            logging.error(f"[MAGAZINE] خطأ Supabase أثناء الحفظ: {e}")

    history = _load_local_history()
    if "published_hashes" not in history:
        history["published_hashes"] = []
    if "records" not in history:
        history["records"] = []

    history["published_hashes"].append(page_hash)
    history["records"].append({
        "page_hash": page_hash,
        "pdf_file": pdf_file,
        "page_number": page_number,
        "post_type": post_type,
        "telegram_message_id": telegram_message_id,
        "published_at": published_at,
    })
    _save_local_history(history)
    logging.info("[MAGAZINE] History saved (local JSON)")


def get_last_post(post_type: str) -> Optional[dict]:
    """يرجع آخر سجل منشور لنوع معين (morning/evening) أو None."""
    if _SB_CLIENT is not None:
        try:
            resp = (
                _SB_CLIENT.table(_TABLE)
                .select("*")
                .eq("post_type", post_type)
                .order("published_at", desc=True)
                .limit(1)
                .maybeSingle()
                .execute()
            )
            return resp.data
        except Exception as e:
            logging.error(f"[MAGAZINE] خطأ Supabase في جلب آخر منشور: {e}")

    history = _load_local_history()
    records = [r for r in history.get("records", []) if r.get("post_type") == post_type]
    return records[-1] if records else None
