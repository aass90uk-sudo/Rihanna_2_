#!/usr/bin/env python3
"""اختبار سريع لنظام المجلة — PDF، Hash، منع التكرار، الحفظ."""
import sys
import os

# تأكد أن مجلد المشروع في المسار
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from magazine import pdf_manager, history

def main():
    print("=" * 60)
    print("اختبار 1: فحص ملفات PDF في مجلد المجلة")
    print("=" * 60)
    pdfs = pdf_manager.list_pdf_files()
    assert len(pdfs) > 0, "لا توجد ملفات PDF!"
    print(f"  ✓ تم العثور على {len(pdfs)} ملف PDF")
    for p in pdfs:
        print(f"    - {p}")

    print()
    print("=" * 60)
    print("اختبار 2: معرفة عدد صفحات أول ملف PDF")
    print("=" * 60)
    total = pdf_manager.get_total_pages(pdfs[0])
    assert total > 0, "الملف لا يحتوي على صفحات!"
    print(f"  ✓ عدد الصفحات: {total}")

    print()
    print("=" * 60)
    print("اختبار 3: استخراج الصفحة الأولى كصورة وحساب Hash")
    print("=" * 60)
    page = pdf_manager.render_page(pdfs[0], 0)
    assert page is not None, "فشل استخراج الصفحة!"
    assert len(page.image_bytes) > 0, "الصورة فارغة!"
    assert len(page.page_hash) == 64, f"طول Hash غير صحيح: {len(page.page_hash)}"
    print(f"  ✓ تم استخراج الصورة ({len(page.image_bytes)} bytes)")
    print(f"  ✓ Hash: {page.page_hash}")
    print(f"  ✓ ملف PDF: {page.pdf_file}, صفحة: {page.page_number + 1}/{page.total_pages}")

    print()
    print("=" * 60)
    print("اختبار 4: فحص منع التكرار — الصفحة غير منشورة بعد")
    print("=" * 60)
    is_dup = history.is_page_published(page.page_hash)
    assert is_dup == False, "الصفحة يفترض ألا تكون منشورة بعد!"
    print(f"  ✓ الصفحة غير منشورة (is_published={is_dup})")

    print()
    print("=" * 60)
    print("اختبار 5: تسجيل الصفحة كمنشورة ثم التحقق من التكرار")
    print("=" * 60)
    history.record_published(
        page_hash=page.page_hash,
        pdf_file=page.pdf_file,
        page_number=page.page_number,
        post_type="morning",
        telegram_message_id=12345,
    )
    is_dup_after = history.is_page_published(page.page_hash)
    assert is_dup_after == True, "الصفحة يفترض أن تكون منشورة الآن!"
    print(f"  ✓ تم تسجيل الصفحة، والتكرار الآن: {is_dup_after}")

    print()
    print("=" * 60)
    print("اختبار 6: محاولة نشر نفس الصفحة مرة أخرى — يجب أن يُرفض")
    print("=" * 60)
    page2 = pdf_manager.render_page(pdfs[0], 0)
    is_dup2 = history.is_page_published(page2.page_hash)
    assert is_dup2 == True, "يجب رفض الصفحة المكررة!"
    print(f"  ✓ الصفحة المكررة تم رفضها (is_published={is_dup2})")

    print()
    print("=" * 60)
    print("اختبار 7: استخراج صفحة جديدة (الثانية) — يجب أن تكون غير منشورة")
    print("=" * 60)
    if total > 1:
        page3 = pdf_manager.render_page(pdfs[0], 1)
        assert page3 is not None
        is_dup3 = history.is_page_published(page3.page_hash)
        assert is_dup3 == False, "الصفحة الثانية يفترض ألا تكون منشورة!"
        print(f"  ✓ الصفحة الثانية غير منشورة (is_published={is_dup3})")
        print(f"  ✓ Hash مختلف: {page3.page_hash[:32]}... != {page.page_hash[:32]}...")
    else:
        print("  - الملف يحتوي على صفحة واحدة فقط، تخطي هذا الاختبار")

    print()
    print("=" * 60)
    print("اختبار 8: جلب آخر منشور صباحي")
    print("=" * 60)
    last = history.get_last_post("morning")
    assert last is not None, "يجب أن يكون هناك منشور صباحي!"
    print(f"  ✓ آخر منشور صباحي: {last}")

    print()
    print("=" * 60)
    print("جميع الاختبارات نجحت!")
    print("=" * 60)

    # تنظيف: حذف السجل التجريبي من Supabase
    try:
        from magazine import config
        if history._SB_CLIENT is not None:
            history._SB_CLIENT.table("magazine_published_pages").delete().eq("page_hash", page.page_hash).execute()
            print("  ✓ تم تنظيف السجل التجريبي من Supabase")
    except Exception as e:
        print(f"  - تحذير أثناء التنظيف: {e}")

if __name__ == "__main__":
    main()
