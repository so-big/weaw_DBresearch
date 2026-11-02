"""Read closing papers (ปิดโครงการ): the closing memo and the faculty-meeting resolution.

Memo (บันทึกข้อความ):
    เรื่อง ขอปิดโครงการวิจัยและส่งผลงานตามตัวชี้วัด
    ที่ อว 0000.00/123   วันที่ 7 สิงหาคม 2568
    … ให้แก่โครงการวิจัย เรื่อง <title> ในวงเงิน 100,000 บาท … โดยมี <PI> สังกัด … เป็นหัวหน้าโครงการ
Resolution (มติที่ประชุม):
    ระเบียบวาระที่ 3.4 ขอปิดโครงการวิจัย… ครั้งที่ 9/2568 เมื่อวันที่ 7 สิงหาคม 2568   มติ รับทราบ

Only suggestions for the closing form: the approval itself is handwritten and isn't read.
"""

import re
from typing import Any

from dbresearch.autofill import thai
from dbresearch.autofill.page import Page

DATE = thai.DATE_RE
_MEMO = re.compile(r"ขอ\s*ปิด\s*โครงการ")
_RESOLUTION = re.compile(r"ระเบียบวาระ|มติที่ประชุม")
_MEMO_NO = re.compile(r"(?:^|\s)ที่\s*(อว\.?\s*\d{3,4}(?:\.\d{1,3})?\s*/\s*\d{1,5})")
_FIRST_DATE = re.compile(rf"วันท\S{{0,2}}\s*({DATE})")
_TITLE = re.compile(
    r"วิจัย\s*เรื่อง\s*[“\"]?\s*(.{5,300}?)\s*[”\"]?\s*"
    r"(?:เลขที่\s*สัญญา|รหัส\s*โครงการ|ใน\s*วงเงิน|ของ\s*ผู้)"
)
_OWNER = re.compile(r"โดยมี\s*(.{3,80}?)\s*(?:สังกัด|เป็นหัวหน้า)")
_MEETING = re.compile(rf"ครั้ง\S{{0,3}}ที่\s*(\d{{1,2}}\s*/\s*25\d\d)\s*เมื่อ\s*วันท\S{{0,2}}\s*({DATE})")
_AGENDA = re.compile(r"ระเบียบวาระ\S{0,3}ที่\s*(\d{1,2}(?:\.\d{1,2})?)")
_AMOUNT = re.compile(r"ใน\s*วงเงิน\s*([\d,]{4,})")


def _text(pages: list[Page], count: int = 2) -> str:
    return " ".join(line.text for page in pages[:count] for line in page.body)


def extract(pages: list[Page]) -> dict[str, Any]:
    text = _text(pages)
    compact = re.sub(r"\s+", "", text)
    # A resolution quotes the memo's subject ('ขอปิดโครงการ…'), so test it first.
    if _RESOLUTION.search(compact) or _MEETING.search(text):
        kind = "resolution"
    else:
        kind = "memo" if _MEMO.search(text) else None
    fields: dict[str, Any] = {}

    def put(name: str, value: Any, page: int = 1) -> None:
        if value not in (None, ""):
            fields[name] = {"value": value, "page": page}

    if match := _MEMO_NO.search(text):
        put("memo_no", re.sub(r"\s+", " ", match[1]).strip())
    if match := _MEETING.search(text):
        put("meeting_no", match[1].replace(" ", ""))
        meeting_date = thai.parse_thai_date(match[2])
        put("meeting_date", meeting_date.isoformat() if meeting_date else None)
    elif match := _FIRST_DATE.search(text):
        memo_date = thai.parse_thai_date(match[1])
        put("memo_date", memo_date.isoformat() if memo_date else None)
    if match := _AGENDA.search(text):
        put("agenda", match[1])
    if match := _TITLE.search(text):
        put("title", thai.strip_leaders(match[1]))
    if match := _OWNER.search(text):
        prefix, name = thai.split_person(thai.clean_person(match[1]))
        put("owner", f"{prefix} {name}" if prefix else name)
    if match := _AMOUNT.search(text):
        amount = thai.parse_money(match[1])
        put("amount", str(amount) if amount else None)
    if (ref := thai.contract_no(text)) is not None:
        put("reference_no", ref)
    return {"kind": kind, "fields": fields, "warnings": []}
