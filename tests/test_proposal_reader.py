"""Proposal-development memos (DESIGN §11). Synthetic pages: the layout and OCR quirks of the
real scans (random spaces inside Thai words, 'เรือง', garbled subjects), all values invented."""

from dbresearch.autofill import proposal
from tests.test_autofill_unit import body, line, page

MEMO_NO = line("ที่ อว 0000.00.01/123 วันที่ 3 ธันวาคม 2568", top=300)


def memo(*texts: str, extra=()) -> list:
    return [page(1, MEMO_NO, *body(*texts)), *extra]


def fields(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def test_request_memo():
    result = proposal.extract(
        memo(
            "เรือง ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย ประจำปีงบประมาณ พ.ศ. 2569",
            "เรียน คณบดีคณะทดสอบ",
            "ด้วยข้าพเจ้า ผู้ช่วยศาสตราจารย์ ดร.สมมติ ทดสอบดี สังกัดภาควิชาวิศวกรรมสมมติ มีความ",
            "ประสงค์ขอรับทุน เรื่อง “ระบบตัว อย่างสำหรับ Sample Data Platform” โดยข้าพเจ้าจะต้อง",
            "ดำเนินการจัดทำข้อเสนอสำหรับการขอทุนวิจัยและ Impact Pathway ให้แล้วเสร็จภายในวันที่",
            "1 กันยายน 2569 นั้น จึงใคร่ขออนุมัติ เป็นเงิน 20,000 บาท (สองหมื่นบาทถ้วน)",
            "โดยมีระยะเวลาในการเบิกจ่ายตั้งแต่วันที่ 15 ธันวาคม 2568 ถึง 30 กันยายน 2569",
            "โดยเบิกจ่ายจากงบประมาณเงินรายได้คณะทดสอบ ประจำปีงบประมาณ 2569",
        ),
    )
    assert result["kind"] == "request" and result["warnings"] == []
    assert fields(result) == {
        "memo_ref": "อว 0000.00.01/123",  # its line has no long word: read from the raw lines
        "document_date": "2025-12-03",
        "fiscal_year": 2026,
        "owner": "ผศ.ดร. สมมติ ทดสอบดี",  # first and last name stay apart
        "department": "ภาควิชาวิศวกรรมสมมติ",
        "title": "ระบบตัวอย่างสำหรับ Sample Data Platform",  # Thai rejoined, English spaced
        "kpi_target": "จัดทำข้อเสนอสำหรับการขอทุนวิจัยและ Impact Pathway",
        "kpi_due": "2026-09-01",
        "budget_total": "20000",
        "effective_from": "2025-12-15",
        "effective_to": "2026-09-30",
        "funding_source": "faculty_income",
    }


def test_research_area_comes_from_the_attachment():
    attachment = page(
        3,
        *body(
            "1. ชื่อข้อเสนอโครงการที่คาดว่าจะถูกพัฒนา : ระบบตัวอย่าง",
            "2. กรอบงานวิจัยที่ถูกพัฒนาเป็นข้อเสนอ : เทคโนโลยีสมมติ",
            "3. รายละเอียดกิจกรรม : ประมาณการค่าใช้จ่าย",
        ),
    )
    result = proposal.extract(memo("เรื่อง ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย", extra=[attachment]))
    assert result["fields"]["research_area"] == {"value": "เทคโนโลยีสมมติ", "page": 3}


def test_cancel_with_a_garbled_subject():
    result = proposal.extract(
        memo(
            "เร้อง ขออนุมติยกเลิกทุนพัฒนาข้อเสนอโครงการวิจัย",
            "เรียน คณบดีคณะทดสอบ",
            "ตามที่ข้าพเจ้า ดร.สมมติ ทดสอบดี สังกัดภาควิชาวิศวกรรมสมมติ ได้รับอนุมัติค่าใช้จ่าย",
            "ทุนพัฒนาข้อเสนอโครงการวิจัย เรื่อง “ระบบตัวอย่าง” เป็นจำนวนเงิน 20,000 บาท",
            "ประจำปีงบประมาณ พ.ศ. 2566 นั้น ทั้งนี้ข้าพเจ้าจึงใคร่ขออนุมัติยกเลิกทุนดังกล่าว",
            "เนื่องจากต้องรอผลการทดลองจากห้องปฏิบัติการ จึงเรียนมาเพื่อโปรดพิจารณา",
        ),
    )
    found = fields(result)
    assert result["kind"] == "cancel"
    assert found["cancel_reason"] == "ต้องรอผลการทดลองจากห้องปฏิบัติการ"
    assert found["title"] == "ระบบตัวอย่าง" and found["fiscal_year"] == 2023


def test_closing_result_wordings():
    new = proposal.extract(
        memo(
            "เรื่อง ขออนุมัติปิดโครงการ ทุนพัฒนาข้อเสนอโครงการวิจัย ประจำปีงบประมาณ 2569",
            "เรียน คณบดีคณะทดสอบ",
            "ตามที่ข้าพเจ้า รศ.ดร.สมมติ ทดสอบดี สังกัดภาควิชาวิศวกรรมสมมติ ได้อนุมัติดำเนินโครงการ",
            "เรื่อง “ระบบตัวอย่าง” พร้อมค่าใช้จ่ายในวงเงิน 20,000 บาท นั้น ขณะนี้ได้มีผลงานตาม",
            "ข้อชี้วัดความสำเร็จของโครงการ คอ ข้อเสนอสำหรับการขอทุนวิจัยภายนอก รายละเอียดตาม",
            "เอกสารแนบ จึงเรียนมาเพื่อโปรดพิจารณาอนุมัติ",
        ),
    )
    assert new["kind"] == "close"
    assert fields(new)["kpi_result"] == "ข้อเสนอสำหรับการขอทุนวิจัยภายนอก"
    old = proposal.extract(
        memo(
            "เรือง ขออนุมัติปิดโครงการ",
            "ในการนี้ข้าพเจ้าได้ดำเนินการจัดทำข้อเสนอดังกล่าวเรียบร้อยแล้ว จึงใคร่ขอนำส่ง",
        ),
    )
    assert fields(old)["kpi_result"] == "จัดทำข้อเสนอโครงการวิจัยเรียบร้อยแล้ว"
    assert {"code": "missing_field", "field": "owner"} in old["warnings"]


def test_title_change_that_also_closes():
    result = proposal.extract(
        memo(
            "เรื่อง ขออนุมัติเปลี่ยนเปลงชื่อเรื่อง และนำส่งข้อเสนอ เพื่อปิดโครงการ",
            "เรียน คณบดีคณะทดสอบ",
            "ด้วยข้าพเจ้า ดร.สมมติ ทดสอบดี สังกัดภาควิชาวิศวกรรมสมมติ ได้รับทุน เรื่อง “ระบบเดิม",
            "สำหรับทดสอบ” จึงใคร่ขออนุมัติเปลี่ยนแปลงจากเรื่อง “ระบบเดิมสำหรับทดสอบ” เป็น",
            "“ระบบใหม่สำหรับทดสอบ” และขอปิดโครงการ",
        ),
    )
    found = fields(result)
    assert result["kind"] == "title_change"
    assert found["title"] == "ระบบเดิมสำหรับทดสอบ" and found["new_title"] == "ระบบใหม่สำหรับทดสอบ"
    assert found["also_close"] is True


def test_owner_from_the_signature_when_the_opening_is_unreadable():
    result = proposal.extract(
        memo(
            "เรื่อง ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย",
            "ด๊วยข้าพเจ๊ามีความประสงค์ขอรับทุน เรื่อง “ระบบตัวอย่าง” โดยข้าพเจ้า",
            "ลงชื่อ",
            "(ผู้ช่วยศาสตราจารย์ ดร.สมมติ ทดสอบดี) ผู้ขอทุนสนับสนุน",
        ),
    )
    assert fields(result)["owner"] == "ผศ.ดร. สมมติ ทดสอบดี"


def test_programme_papers_and_unknown_pages():
    call = proposal.extract(
        memo("เรื่อง ขอความอนุเคราะห์เวียนแจ้งการเปิดรับข้อเสนอโครงการ", "เรียน คณบดีคณะทดสอบ")
    )
    assert call["kind"] == "programme" and call["warnings"] == []
    blank = proposal.extract(memo("รายงานการประชุมทั่วไป"))
    assert blank["kind"] is None and blank["warnings"] == [{"code": "unknown_paper_type"}]
    assert proposal.extract([]) == {"kind": None, "fields": {}, "warnings": []}


def test_received_no_comes_from_the_file_name():
    from dbresearch.autofill.proposal import received_no

    assert received_no("10221 ขออนุมัติทุนพัฒนาข้อเสนอ 2569.pdf") == "10221"
    assert received_no("268 ปิดโครงการ 2567..pdf") == "268"
    assert received_no("5035(แก้ไข).pdf") == "5035"
    assert received_no("0018_scan.pdf") == "0018"
    assert received_no("ขออนุมัติทุน 2568.pdf") is None
    assert received_no("2568ทุน.pdf") is None
    assert received_no(None) is None
