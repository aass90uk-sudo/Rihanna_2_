#!/usr/bin/env python3
"""اختبار سريع لنظام مجلة القيادة — PDF، Hash، منع التكرار، الحفظ."""

import sys
import os

# تأكد أن مجلد المشروع في المسار
sys.path.insert(
    0,
    os.path.dirname(
        os.path.abspath(__file__)
    ),
)

from magazine import pdf_manager, history, config


def main():

    print("=" * 60)
    print("اختبار 1: فحص ملف مجلة القيادة")
    print("=" * 60)

    magazine_filename = config.MAGAZINE_2_FILE

    magazine_filename = (
        config.resolve_magazine_file(
            magazine_filename
        )
    )

    pdf_path = os.path.join(
        config.MAGAZINE_DIR,
        magazine_filename,
    )

    assert os.path.isfile(
        pdf_path
    ), f"ملف مجلة القيادة غير موجود: {pdf_path}"

    print(
        f"  ✓ تم العثور على مجلة القيادة: "
        f"{pdf_path}"
    )

    print()
    print("=" * 60)
    print("اختبار 2: معرفة عدد صفحات مجلة القيادة")
    print("=" * 60)

    total = pdf_manager.get_total_pages(
        pdf_path
    )

    assert total > 0, (
        "ملف القيادة لا يحتوي على صفحات!"
    )

    print(
        f"  ✓ عدد الصفحات: {total}"
    )

    print()
    print("=" * 60)
    print("اختبار 3: استخراج الصفحة الأولى كصورة وحساب Hash")
    print("=" * 60)

    page = pdf_manager.render_page(
        pdf_path,
        0,
    )

    assert page is not None, (
        "فشل استخراج الصفحة!"
    )

    assert len(page.image_bytes) > 0, (
        "الصورة فارغة!"
    )

    assert len(page.page_hash) == 64, (
        f"طول Hash غير صحيح: "
        f"{len(page.page_hash)}"
    )

    print(
        f"  ✓ تم استخراج الصورة "
        f"({len(page.image_bytes)} bytes)"
    )

    print(
        f"  ✓ Hash: {page.page_hash}"
    )

    print(
        f"  ✓ ملف PDF: {page.pdf_file}, "
        f"صفحة: {page.page_number + 1}/"
        f"{page.total_pages}"
    )

    print()
    print("=" * 60)
    print("اختبار 4: فحص منع التكرار — الصفحة غير منشورة بعد")
    print("=" * 60)

    is_dup = history.is_page_published(
        page.page_hash
    )

    if is_dup:
        print(
            "  ! الصفحة مسجلة مسبقاً في سجل النشر."
        )
        print(
            "  ! سيتم تخطي اختبار التسجيل "
            "التجريبي حتى لا نكرر السجل."
        )
    else:
        print(
            f"  ✓ الصفحة غير منشورة "
            f"(is_published={is_dup})"
        )

    print()
    print("=" * 60)
    print("اختبار 5: تسجيل الصفحة كمنشورة ثم التحقق من التكرار")
    print("=" * 60)

    test_record_created = False

    if not is_dup:

        history.record_published(
            page_hash=page.page_hash,
            pdf_file=page.pdf_file,
            page_number=page.page_number,
            post_type="test",
            telegram_message_id=12345,
        )

        test_record_created = True

        is_dup_after = (
            history.is_page_published(
                page.page_hash
            )
        )

        assert is_dup_after is True, (
            "الصفحة يفترض أن تكون منشورة الآن!"
        )

        print(
            f"  ✓ تم تسجيل الصفحة، "
            f"والتكرار الآن: "
            f"{is_dup_after}"
        )

    else:

        print(
            "  - تم تخطي التسجيل لأن الصفحة "
            "مسجلة مسبقاً."
        )

    print()
    print("=" * 60)
    print("اختبار 6: محاولة نشر نفس الصفحة مرة أخرى — يجب أن تُرفض")
    print("=" * 60)

    page2 = pdf_manager.render_page(
        pdf_path,
        0,
    )

    assert page2 is not None

    is_dup2 = (
        history.is_page_published(
            page2.page_hash
        )
    )

    assert is_dup2 is True, (
        "يجب رفض الصفحة المكررة!"
    )

    print(
        f"  ✓ الصفحة المكررة تم رفضها "
        f"(is_published={is_dup2})"
    )

    print()
    print("=" * 60)
    print("اختبار 7: استخراج صفحة جديدة (الثانية)")
    print("=" * 60)

    if total > 1:

        page3 = pdf_manager.render_page(
            pdf_path,
            1,
        )

        assert page3 is not None

        is_dup3 = (
            history.is_page_published(
                page3.page_hash
            )
        )

        print(
            f"  ✓ الصفحة الثانية "
            f"(is_published={is_dup3})"
        )

        print(
            f"  ✓ Hash الصفحة الثانية: "
            f"{page3.page_hash[:32]}..."
        )

        print(
            f"  ✓ Hash الصفحة الأولى: "
            f"{page.page_hash[:32]}..."
        )

        assert (
            page3.page_hash
            != page.page_hash
        ), "Hash الصفحة الثانية يجب أن يختلف!"

    else:

        print(
            "  - الملف يحتوي على صفحة واحدة فقط، "
            "تخطي هذا الاختبار"
        )

    print()
    print("=" * 60)
    print("اختبار 8: جلب آخر منشور صباحي")
    print("=" * 60)

    last = history.get_last_post(
        "morning"
    )

    if last is not None:

        print(
            f"  ✓ آخر منشور صباحي: {last}"
        )

    else:

        print(
            "  - لا يوجد منشور صباحي مسجل حالياً."
        )

    print()
    print("=" * 60)
    print("جميع اختبارات مجلة القيادة الأساسية نجحت!")
    print("=" * 60)

    # ==========================================
    # تنظيف السجل التجريبي فقط
    # ==========================================

    if test_record_created:

        try:

            if history._SB_CLIENT is not None:

                history._SB_CLIENT.table(
                    "magazine_published_pages"
                ).delete().eq(
                    "page_hash",
                    page.page_hash,
                ).execute()

                print(
                    "  ✓ تم تنظيف السجل التجريبي "
                    "من Supabase"
                )

            else:

                print(
                    "  - لا يوجد اتصال بـ Supabase؛ "
                    "تم تسجيل الاختبار محلياً."
                )

        except Exception as e:

            print(
                f"  - تحذير أثناء التنظيف: {e}"
            )


if __name__ == "__main__":
    main()
