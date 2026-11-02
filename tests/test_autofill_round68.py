"""Rules tuned on the 2568 round-1 contracts and the closing papers.

The real PDFs are confidential: every text here is invented, only the *shapes* (layouts and
OCR mistakes) come from the scans.
"""

from datetime import date
from decimal import Decimal

import pytest

from dbresearch.autofill import closure, thai
from dbresearch.autofill.pipeline import funding_from_title, installments, same_person
from dbresearch.autofill.rules import extract
from tests.test_autofill_unit import body, page


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("สัญญาเลขที่R256BE001 หน้า 17", "R2568E001"),  # B read for 8
        ("R 2568 E 12", "R2568E012"),
        ("R2567A101", "R2567A101"),
        ("no number", None),
    ],
)
def test_contract_no_repairs_digits_but_keeps_the_faculty_letter(text, expected):
    assert thai.contract_no(text) == expected


@pytest.mark.parametrize(
    ("raw", "prefix", "name"),
    [
        ("ผู้ช่วยศาสตราจารย์ os. สมหญิงรักงาน", "ผศ.ดร.", "สมหญิงรักงาน"),
        ("ผศ .ตร.สมชาย ใจดีเอ606004546656553", "ผศ.ดร.", "สมชาย ใจดีเอ"),
        ("ผูผู้้ช่วยศาสตราจ ารย์ คร .สมใจ ทดลอง", "ผศ.ดร.", "สมใจ ทดลอง"),
        ("รองศาสตราจารย์ ดร . สมศักดิ์ ตัวอย่าง", "รศ.ดร.", "สมศักดิ์ ตัวอย่าง"),
        ("ดร.สมพร ทดสอบ. เ", "ดร.", "สมพร ทดสอบ"),
    ],
)
def test_person_names_are_repaired(raw, prefix, name):
    assert thai.split_person(thai.clean_person(raw)) == (prefix, name)


@pytest.mark.parametrize(
    ("text", "noise"),
    [("a i i a a 37", True), ("ow a en! doy aw", True), ("at", True), ("เป็นส่วนเสริมแรง", False)],
)
def test_noise_lines(text, noise):
    assert thai.is_noise(text) is noise


def test_noise_line_inside_a_clause_is_skipped():
    p = page(1, *body("สัญญานี้ทำขึ้น เมื่อวันที่20", "at", "มกราคม 2568 ระหว่าง"))
    rule = {
        "field": "document_date",
        "layout": "sentence",
        "pattern": rf"เม\S{{0,2}}อ\s*วันท\S{{0,2}}\s*({thai.DATE_RE})",
        "group": 1,
        "post": ["thai_date"],
    }
    assert extract([rule], [p], [p])[0].value == date(2025, 1, 20)


@pytest.mark.parametrize(
    ("title_block", "expected"),
    [
        ("สัญญารับทุนอุดหนุนการวิจัย จากง บประมาณรายได้คณะตัวอย่าง ประจำปีงบประมาณ พ.ศ. 2568", "internal"),
        (
            "สัญญารับทุนอุดหนุนการวิจัย ภายใต้บันทึกความเข้าใจ ประจำปี พ.ศ. 2568 "
            "ระหว่าง สำนักงานตัวอย่าง กับ มหาวิทยาลัยตัวอย่าง",
            "external",
        ),
        ("สัญญารับทุนอุดหนุนการวิจัย", None),
    ],
)
def test_funding_type_comes_from_the_title_block(title_block, expected):
    assert funding_from_title(title_block) == expected


def test_team_block_anchored_on_unit_and_role():
    p = page(
        12,
        *body(
            "ชื่อ- ana ผู้ช่วยศาสตราจารย์ os. สมหญิง รักงาน สัต ส่วนการทำวิจัย(%) 100",
            "หน่วยงาน ภาควิชาตัวอย่าง คณะตัวอย่าง",
            "บทบาทในโครงการ หัวหน้าโครงการ",
            "ชื่อ - สกุล",  # value in another column: only the label was read
            "หน่วยงาน",
            "บทบาทในโครงการ 222602220203666",
            "หน่วยงานที่สังกัด",  # report cover, no team entry
        ),
    )
    people = [c.value for c in extract([{"field": "team", "layout": "team"}], [p], [p])]
    assert [(x["prefix_th"], x["name"], x["share_pct"], x["role"]) for x in people] == [
        ("ผศ.ดร.", "สมหญิง รักงาน", 100.0, "owner")
    ]


def test_bracketed_percent_sign_is_not_a_share():
    p = page(
        12,
        *body(
            "ซื่อ- ANA ดร.สมใจ ทดลอง สัดส่วนการทำวิจัย(1) .....1ดดิอน.ร",
            "หน่วยงาน ภาควิชาตัวอย่าง",
            "บทบาทในโครงการ ผู้ร่วมวิจัย",
        ),
    )
    (person,) = [c.value for c in extract([{"field": "team", "layout": "team"}], [p], [p])]
    assert person["share_pct"] is None


def test_english_names_from_the_cv_part():
    p = page(
        16,
        *body(
            "ชื่อ - นามสกุล (ภาษาไทย) นาย / นาง / นางสาว สมหญิง รักงาน",
            "(ภาษาอังกฤษ ) Mr. / Miss / Mrs: Somying Rakngan",
            "(ภาษาอังกฤษ) Development of a Test Method",  # a title, not a person
        ),
    )
    found = [c.value for c in extract([{"field": "team_en", "layout": "names_en"}], [p], [p])]
    assert found == [{"name_th": "สมหญิง รักงาน", "name_en": "Somying Rakngan"}]


def test_same_person_tolerates_an_unread_surname():
    assert same_person("สมชาย", "สมชายใจดี")
    assert not same_person("สม", "สมชายใจดี")


INSTALLMENTS = [{"field": "budget_lines", "layout": "installments"}]


def test_installments_with_amounts():
    p = page(
        5,
        *body(
            "งบประมาณรวม ในวงเงิน 100,000 บาท (หนึ่งแสนบาทถ้วน )",
            "งวดท 1 จานวน 40,000 บาท (สี่หมื่นบาทถ้วน)",
            "(ร้อยละ 40) จ่ายภายใน 30 (สามสิบ ) วัน หลังจากวันลงนามในสัญญา",
            "VIAN 2 จานวน 40,000 un(สี่หมื่นบาทถ้วน)",
            "(จ้อยละ 40) จ่ายเมื่อส่งรายงานความก้าวหน้า",
            "งวดที่ 3 จำนวน 20,000 บาท (สองหมื่นบาทถ้วน )",
            "(ร้อยละ 20) จ่ายเมื่อส่งรายงานฉบับสมบูรณ์",
            "หมายเหตุ: ไม่เกินวันที่19 มกราคม 2569 (นับจากปีงบประมาณ)",
        ),
    )
    (found,) = extract(INSTALLMENTS, [p], [p])
    assert [(x["label"], x["amount"], x["percent"]) for x in found.value] == [
        ("งวดที่ 1", Decimal("40000"), 40.0),
        ("งวดที่ 2", Decimal("40000"), 40.0),
        ("งวดที่ 3", Decimal("20000"), 20.0),
    ]
    assert found.value[0]["condition"] == "จ่ายภายใน 30 (สามสิบ ) วัน หลังจากวันลงนามในสัญญา"
    assert found.value[-1]["due_date"] == date(2026, 1, 19)


def test_installment_amounts_in_another_column_are_computed():
    p = page(5, *body("งวดที่ 1", "(ร้อยละ 70)", "งวดที่ 2", "(ร้อยละ 30)"))
    candidates = extract(INSTALLMENTS, [p], [p])
    lines = installments(candidates, {"budget_total": {"value": "200000"}})
    assert [(x["amount"], x.get("computed")) for x in lines] == [
        (Decimal("140000.00"), True),
        (Decimal("60000.00"), True),
    ]


def test_closing_memo_readings():
    p = page(
        1,
        *body(
            "บันทึกข้อความ",
            "ที่ อว 0000.00/123 วันที่ 7 สิงหาคม 2568",
            "เรื่อง ขอปิดโครงการวิจัยและส่งผลงานตามตัวชี้วัด",
            "ตามคณะตัวอย่างให้ทุนอุดหนุนโครงการวิจัย ให้แก่โครงการวิจัย เรื่อง การทดลองระบบตัวอย่าง",
            "ในวงเงิน 100,000 บาท (หนึ่งแสนบาทถ้วน) โดยมี ผู้ช่วยศาสตราจารย์ ดร. สมใจ ทดลอง สังกัด",
            "ภาควิชาตัวอย่าง เป็นหัวหน้าโครงการ",
        ),
    )
    found = closure.extract([p])
    values = {k: v["value"] for k, v in found["fields"].items()}
    assert found["kind"] == "memo"
    assert values["memo_no"] == "อว 0000.00/123"
    assert values["memo_date"] == "2025-08-07"
    assert values["title"] == "การทดลองระบบตัวอย่าง"
    assert values["owner"] == "ผศ.ดร. สมใจ ทดลอง"
    assert values["amount"] == "100000"


def test_meeting_resolution_readings():
    p = page(
        1,
        *body(
            "ระเบียบวาระที่ 3.4 ขอปิดโครงการวิจัยของผู้ช่วยศาสตราจารย์ตัวอย่าง",
            "นำเสนอที่ประชุม คณะกรรมการประจำคณะตัวอย่าง",
            "ครั้งที่ 9/2568 เมื่อวันที่ 7 สิงหาคม 2568",
            "รับทราบ",
        ),
    )
    found = closure.extract([p])
    values = {k: v["value"] for k, v in found["fields"].items()}
    assert found["kind"] == "resolution"
    assert values["meeting_no"] == "9/2568"
    assert values["meeting_date"] == "2025-08-07"
    assert values["agenda"] == "3.4"
