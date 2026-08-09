"""إدارة ملفات PDF — يفحص المجلد ويستخرج الصفحات كصور ويحسب Hash.

يدعم ملفات PDF السليمة (عبر PyMuPDF) وكذلك الملفات التالفة التي تحتوي
على صور JPEG مضمّنة بدون بنية صفحات صحيحة (fallback عبر استخراج JPEG).
"""
import os
import io
import re
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, List

import fitz  # PyMuPDF

from . import config


@dataclass
class PageImage:
    """صفحة واحدة محوّلة إلى صورة مع بياناتها."""
    pdf_file: str        # اسم ملف PDF
    page_number: int     # رقم الصفحة (0-based)
    total_pages: int     # إجمالي صفحات هذا الملف
    image_bytes: bytes   # bytes الصورة بصيغة JPEG
    page_hash: str       # SHA-256 لمحتوى الصورة


def list_pdf_files() -> List[str]:
    """يرجع قائمة مسارات ملفات PDF المرتبة داخل مجلد المجلة."""
    directory = config.MAGAZINE_DIR
    if not os.path.isdir(directory):
        logging.warning(f"[MAGAZINE] مجلد المجلة غير موجود: {directory}")
        return []

    pdfs = []
    for fname in sorted(os.listdir(directory)):
        if fname.lower().endswith(".pdf"):
            pdfs.append(os.path.join(directory, fname))

    logging.info(f"[MAGAZINE] تم العثور على {len(pdfs)} ملف PDF")
    for p in pdfs:
        logging.info(f"[MAGAZINE] PDF found: {p}")
    return pdfs


def get_total_pages(pdf_path: str) -> int:
    """يرجع عدد صفحات ملف PDF (يدعم PDF السليم والملف التالف)."""
    count = _get_total_pages_native(pdf_path)
    if count > 0:
        return count
    # fallback: عدّ صور JPEG المضمّنة
    return _count_embedded_jpegs(pdf_path)


def _get_total_pages_native(pdf_path: str) -> int:
    """يحاول قراءة عدد الصفحات عبر PyMuPDF (PDF سليم)."""
    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        doc.close()
        return total
    except Exception:
        return 0


def _count_embedded_jpegs(pdf_path: str) -> int:
    """يعدّ صور JPEG المضمّنة في ملف PDF تالف (fallback)."""
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        soi = b"\xff\xd8\xff"
        count = 0
        pos = 0
        while True:
            start = data.find(soi, pos)
            if start == -1:
                break
            end = data.find(b"\xff\xd9", start)
            if end == -1:
                break
            count += 1
            pos = end + 2
        return count
    except Exception:
        return 0


def _extract_embedded_jpegs(pdf_path: str) -> List[bytes]:
    """يستخرج صور JPEG الخام من ملف (عندما يكون PDF التالف بدون بنية صفحات)."""
    with open(pdf_path, "rb") as f:
        data = f.read()

    soi = b"\xff\xd8\xff"
    eoi = b"\xff\xd9"
    images = []
    pos = 0
    while True:
        start = data.find(soi, pos)
        if start == -1:
            break
        end = data.find(eoi, start)
        if end == -1:
            break
        jpg = data[start:end + 2]
        if len(jpg) > 100:  # تجاهل الصور الصغيرة جداً (أيقونات)
            images.append(jpg)
        pos = end + 2
    return images


def render_page(pdf_path: str, page_number: int) -> Optional[PageImage]:
    """يحوّل صفحة واحدة إلى صورة JPEG ويحسب بصمتها (SHA-256).

    يحاول أولاً عبر PyMuPDF (PDF سليم)، وإذا فشل يلجأ إلى استخراج
    صور JPEG المضمّنة مباشرة من الملف الخام.
    """
    # المحاولة الأولى: PDF سليم عبر PyMuPDF
    page = _render_page_native(pdf_path, page_number)
    if page is not None:
        return page

    # المحاولة الثانية: استخراج JPEG من ملف تالف
    return _render_page_from_jpegs(pdf_path, page_number)


def _render_page_native(pdf_path: str, page_number: int) -> Optional[PageImage]:
    """يستخرج صفحة عبر PyMuPDF (PDF سليم)."""
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if total_pages == 0:
            doc.close()
            return None

        if page_number < 0 or page_number >= total_pages:
            doc.close()
            return None

        page = doc[page_number]
        pix = page.get_pixmap(dpi=config.PDF_DPI)
        image_bytes = pix.tobytes(output="jpeg")
        doc.close()

        page_hash = hashlib.sha256(image_bytes).hexdigest()
        pdf_name = os.path.basename(pdf_path)

        logging.info(f"[MAGAZINE] Checking page: {pdf_name} #{page_number + 1}/{total_pages}")
        logging.info(f"[MAGAZINE] Page hash: {page_hash}")

        return PageImage(
            pdf_file=pdf_name,
            page_number=page_number,
            total_pages=total_pages,
            image_bytes=image_bytes,
            page_hash=page_hash,
        )
    except Exception:
        return None


def _render_page_from_jpegs(pdf_path: str, page_number: int) -> Optional[PageImage]:
    """يستخرج صورة JPEG من ملف تالف (fallback)."""
    try:
        jpegs = _extract_embedded_jpegs(pdf_path)
        if not jpegs:
            logging.error(f"[MAGAZINE] لا توجد صور JPEG في {pdf_path}")
            return None

        total_pages = len(jpegs)
        if page_number < 0 or page_number >= total_pages:
            return None

        image_bytes = jpegs[page_number]
        page_hash = hashlib.sha256(image_bytes).hexdigest()
        pdf_name = os.path.basename(pdf_path)

        logging.info(f"[MAGAZINE] Checking page: {pdf_name} #{page_number + 1}/{total_pages} (JPEG fallback)")
        logging.info(f"[MAGAZINE] Page hash: {page_hash}")

        return PageImage(
            pdf_file=pdf_name,
            page_number=page_number,
            total_pages=total_pages,
            image_bytes=image_bytes,
            page_hash=page_hash,
        )
    except Exception as e:
        logging.error(f"[MAGAZINE] خطأ في استخراج JPEG من {pdf_path}: {e}")
        return None
