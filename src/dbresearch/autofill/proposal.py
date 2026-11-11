"""Read proposal-development papers (ทุนพัฒนาข้อเสนอโครงการวิจัย, DESIGN §11).

Every paper is a faculty memo (บันทึกข้อความ) in running prose:

    ที่ อว 0000.00.00/123   วันที่ 3 ธันวาคม 2568
    เรื่อง ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย ประจำปีงบประมาณ พ.ศ. 2569
    ด้วยข้าพเจ้า <researcher> สังกัดภาควิชา<department> มีความประสงค์ขอรับทุน … เรื่อง “<title>”
    โดยข้าพเจ้าจะต้องดำเนินการจัดทำ<KPI> ให้แล้วเสร็จภายในวันที่ <due> … เป็นเงิน 20,000 บาท
    โดยมีระยะเวลาในการเบิกจ่ายตั้งแต่วันที่ <from> ถึง <to> … งบประมาณเงินรายได้คณะ…

Closing, cancellation and change memos follow the same frame. OCR garbles the `เรื่อง` line in
about half the scans, so the memo body decides the paper type too (DESIGN §6 findings).
Patterns run on space-free text (Tesseract's Thai spacing is random); values are cut from the
original text so English titles keep their spaces. Only suggestions: people confirm them.
"""

import re
from typing import Any

from dbresearch.autofill import thai
from dbresearch.autofill.page import Page
from dbresearch.ocr_layout import MIN_LINE_CONFIDENCE

PAPER_TYPES = ("request", "close", "cancel", "title_change", "budget_change", "programme")

# ───────────── Text helpers ─────────────
_THAI = "฀-๿"
_DATE = r"\d{1,2}[฀-๿.]{2,12}(?:25\d\d|\d{2})"  # a Thai date with its spaces removed
_TOPIC = r"เร[ื่ิ]{0,2}อ[่]?ง"  # เรื่อง, often read as เรือง / เร่ือง
_SPACE_IN_THAI = re.compile(rf"(?<=[{_THAI}])\s+(?=[{_THAI}])")


class Text:
    """Running text plus a space-free copy whose positions map back to the original."""

    def __init__(self, text: str):
        self.raw = text
        self.index = [i for i, ch in enumerate(text) if not ch.isspace()]
        self.compact = "".join(text[i] for i in self.index)

    def search(self, pattern: re.Pattern) -> re.Match | None:
        return pattern.search(self.compact)

    def group(self, match: re.Match, group: int = 1, join_thai: bool = True) -> str:
        """The matched group as written, spaces collapsed. `join_thai` also drops spaces
        between Thai letters (OCR splits words: 'การประเมิ นและทำ นาย'); names keep them."""
        start, end = match.span(group)
        if start == end:
            return ""
        piece = self.raw[self.index[start] : self.index[end - 1] + 1]
        if join_thai:
            piece = _SPACE_IN_THAI.sub("", piece)
        return re.sub(r"\s+", " ", piece).strip(" .,:;“”\"'")


def _body_text(pages: list[Page]) -> str:
    return " ".join(line.text for page in pages for line in page.body)


def _raw_text(page: Page) -> str:
    """All confident lines: the memo-no. line has no long word, so `Page.body` drops it."""
    return " ".join(ln.text for ln in page.lines if ln.conf >= MIN_LINE_CONFIDENCE)


# ───────────── Paper type ─────────────
_SUBJECT = re.compile(rf"{_TOPIC}(.{{10,160}}?)เรียน")
# Only in the subject: request bodies name the programme too ('…โครงการสนับสนุนพัฒนาข้อเสนอ…').
_PROGRAMME_SUBJECT = re.compile(r"โครงการสนับสนุนพัฒนาข้อเสนอ|ResearchHangout")
_TYPE_RULES = (
    (
        "programme",
        re.compile(
            r"เวียนแจ้ง|อนุเคราะห์เวียน|ขออนุมัติโครงการ(?:สนับสนุน|ทุน)|ระเบียบวาระ"
            r"|มติที่ประชุม|ResearchHangout"
        ),
    ),
    # 'อนุมัติ' is often misread ('อนุมติ', 'อบนุมัติ'): allow a few letters in between.
    ("cancel", re.compile(r"ขอ\S{0,8}ยกเลิก")),
    ("budget_change", re.compile(r"หมวดค่าใช้จ่าย")),
    ("title_change", re.compile(r"เปลี่ยน\S{0,6}?(?:หัวข้อ|ช[ื]?[่]?อ(?:เรื่อง)?|เรื่อง)")),
    (
        "close",
        # 'ปิด' is read as 'ปิต' at times; 'ส่งผลงานตามตัวชี้วัด' is the closing's other phrase.
        re.compile(
            r"ปิ[ดต]\S?(?:โครงการ|ทุน)|ขอ(?:นำ)?ส่งข้อเสนอ|ข้อเสนอโครงการวิจัยเรียบร้อยแล้ว"
            r"|ส่งผลงานตาม"
        ),
    ),
    ("request", re.compile(r"ขออนุมัติ\S{0,6}ทุนพัฒนา|ขอรับทุน\S{0,4}พัฒนา|พัฒนาข้อเสนอ")),
)


def paper_type(first_page: str) -> str | None:
    """Subject line first, then the opening of the memo body (space-free text)."""
    subject = _SUBJECT.search(first_page[:900])
    if subject and _PROGRAMME_SUBJECT.search(subject[1]):
        # The programme by name, unless the subject is about one project (cancel, change, close).
        project_level = [p for name, p in _TYPE_RULES if name not in ("programme", "request")]
        if not any(p.search(subject[1]) for p in project_level):
            return "programme"
    for source in ((subject[1] if subject else ""), first_page[:1500]):
        for name, pattern in _TYPE_RULES:
            if source and pattern.search(source):
                return name
    return None


# ───────────── Fields ─────────────
_MEMO_NO = re.compile(r"อว\.?(\d{4}\.\d{2}(?:\.\d{1,2})?(?:\(\d\))?/\d{1,5})")
_MEMO_DATE = re.compile(rf"วันท\S{{0,2}}({_DATE})")
_FISCAL = re.compile(r"ปีงบ\S{0,4}ประมาณ(?:พ\.?ศ\.?)?(25\d\d)")
_FISCAL_LOOSE = re.compile(r"ปีงบ\S{0,8}?(25\d\d)")  # 'ปีงบประเ1"ศ2567': garbled พ.ศ.
_OWNER = re.compile(r"(?:ด้วย|ตามที\S?)ข้าพเจ้า(.{4,70}?)(?:ตำแหน่ง|อาจารย์ประ|สังกัด)")
# The signature: '(ผู้ช่วยศาสตราจารย์ ดร.… …) ผู้ขอทุนสนับสนุน / ผู้รับทุน / หัวหน้าโครงการ'.
_SIGNER = re.compile(r"\(([^()]{6,70}?)\)(?:ผู้ขอทุน|ผู้รับทุน|หัวหน้าโครงการ)")
_DEPARTMENT = re.compile(r"สังกัด(ภาควิชา.{3,45}?)(?:คณะ|ได้|มี|ขอ|โทร|$)")
# The quoted title may follow a few words ('เรื่องที่เกี่ยวข้องกับ “…”').
_TITLE_QUOTED = re.compile(rf"{_TOPIC}(?!ขอ)\S{{0,20}}?[“\"](?!ขอ)(.{{8,300}}?)[”\"]")
_TITLE = re.compile(
    rf"{_TOPIC}(?!ขอ)(.{{8,300}}?)(?:พร้อม|เป็นจำนวนเงิน|เป็นเงิน|ในวงเงิน|โดย|ภายใต้|ซึ่ง|นั้น)"
)
# `เรื่อง` itself unreadable ('Gas“…”'): curly quotes only, a stray '"' is OCR noise.
_ANY_QUOTED = re.compile(r"“(?!ขอ)(.{8,300}?)”")
_NEW_TITLE = re.compile(r"[”\"]\S{0,3}เป็น(?:เรื่อง)?[“\"](.{8,300}?)[”\"]")
_CLOSE_TOO = re.compile(r"ปิด(?:โครงการ|ทุน)")
_AMOUNT = re.compile(r"(?:เป็นเงิน|วงเงิน|จำนวนเงิน|เป็นจำนวน)([\d,]{4,10}(?:\.\d\d)?)บาท")
_PERIOD = re.compile(rf"ตั้งแต่(?:วันที่)?({_DATE})(?:ถึง|-)(?:วันที่)?({_DATE})")
_KPI = re.compile(r"ต้อง(?:ดำเนินการ)?(จัดทำ.{5,160}?)(?:ให้แล้วเสร็จ|นั้น)")
_KPI_DUE = re.compile(rf"แล้วเสร็จภายใน(?:วันที่)?({_DATE})")
# 'ตัวชี้วัด' / 'ข้อชี้วัด' … 'คือ' (OCR: 'คอ'); older memos only say the proposal is done.
_KPI_RESULT = re.compile(r"(?:ตัว|ข้อ)ชี้วัด\S{0,25}?ค[ืิ]?อ(.{5,200}?)(?:\(?รายละเอียด|ตามเอกสาร|จึงเรียน)")
_DELIVERED = re.compile(
    r"ได้ดำเนินการ(?:จัดทำ)?(?:ขอ)?(?:ส่ง)?ข้อเสนอ(?:โครงการวิจัย|ดังกล่าว)\S{0,20}?เรียบร้อย"
)
_REASON = re.compile(r"เนื่องจาก(.{5,400}?)(?:จึงเรียน|ดังนั้น|$)")
_AREA = re.compile(
    r"กรอบ(?:งาน)?วิจัย(?:ที่\S{0,4}พัฒนา\S{0,4}ข้อเสนอ)?[:：]?(.{3,80}?)(?:\d\.|รายละเอียด|$)"
)
_SPENT = re.compile(r"รวม\s*(?:ทั้ง\s*สิ้น)?\s*([\d,]{3,10}(?:\.\d\d)?)\s+([\d,]{1,10}(?:\.\d\d)?)")
_FUNDING = (
    ("faculty_income", re.compile(r"รายได้\S{0,4}คณะ")),
    ("nu_income", re.compile(r"รายได้\S{0,4}มหาวิทยาลัย")),
    ("ff", re.compile(r"FundamentalFund|\bFF\b|กองทุนส่งเสริมวิทยาศาสตร์")),
    ("external", re.compile(r"แหล่งทุนภายนอก")),
)
REQUIRED = {
    "request": ("owner", "title", "fiscal_year", "budget_total"),
    "close": ("owner", "title"),
    "cancel": ("owner", "title"),
    "title_change": ("owner", "title", "new_title"),
    "budget_change": ("owner", "title"),
}


def _date(text: str) -> str | None:
    day = thai.parse_thai_date(text)
    return day.isoformat() if day else None


def _person(text: str) -> str | None:
    prefix, name = thai.split_person(thai.clean_person(text))
    if not name:
        return None
    return f"{prefix} {name}" if prefix else name


_RECEIVED_NO = re.compile(r"\s*(\d{2,6})(?=[\s_\-.(]|$)")


def received_no(filename: str | None) -> str | None:
    """The faculty's received no. (เลขรับ): the office names each scan '<no> <subject>.pdf'.
    The stamp itself is handwritten, so the file name is the reliable source."""
    m = _RECEIVED_NO.match(filename or "")
    return m[1] if m else None


def extract(pages: list[Page]) -> dict[str, Any]:
    """Paper type + field suggestions. Same shape as `closure.extract`."""
    if not pages:
        return {"kind": None, "fields": {}, "warnings": []}
    memo = Text(_body_text(pages[:2]))
    raw_first = Text(_raw_text(pages[0]))
    kind = paper_type(Text(_body_text(pages[:1])).compact)
    fields: dict[str, Any] = {}

    def put(name: str, value: Any, page: int = 1) -> None:
        if value not in (None, ""):
            fields[name] = {"value": value, "page": page}

    if m := raw_first.search(_MEMO_NO):
        put("memo_ref", f"อว {m[1]}")
    if m := raw_first.search(_MEMO_DATE):
        put("document_date", _date(m[1]))
    if m := memo.search(_FISCAL) or memo.search(_FISCAL_LOOSE):
        put("fiscal_year", thai.be_to_gregorian(int(m[1])))
    if m := memo.search(_OWNER) or memo.search(_SIGNER):
        put("owner", _person(memo.group(m, join_thai=False)))
    if m := memo.search(_DEPARTMENT):
        put("department", m[1])
    if m := memo.search(_TITLE_QUOTED) or memo.search(_TITLE) or memo.search(_ANY_QUOTED):
        put("title", memo.group(m))
    if kind == "title_change":
        if m := memo.search(_NEW_TITLE):
            put("new_title", memo.group(m))
        # 'ขออนุมัติเปลี่ยนแปลงหัวข้อ … เพื่อปิดโครงการ': one memo, two events.
        if memo.search(_CLOSE_TOO):
            put("also_close", True)
    if m := memo.search(_AMOUNT):
        amount = thai.parse_money(m[1])
        put("budget_total", str(amount) if amount else None)
    if m := memo.search(_PERIOD):
        put("effective_from", _date(m[1]))
        put("effective_to", _date(m[2]))
    if m := memo.search(_KPI):
        put("kpi_target", memo.group(m))
    if m := memo.search(_KPI_DUE):
        put("kpi_due", _date(m[1]))
    if kind == "close":
        if m := memo.search(_KPI_RESULT):
            put("kpi_result", memo.group(m))
        elif memo.search(_DELIVERED):
            put("kpi_result", "จัดทำข้อเสนอโครงการวิจัยเรียบร้อยแล้ว")
    if kind == "cancel" and (m := memo.search(_REASON)):
        put("cancel_reason", memo.group(m))
    for name, pattern in _FUNDING:
        if memo.search(pattern):
            put("funding_source", name)
            break
    # Attachments: research area (request), actual spending (closing report).
    for page in pages[1:]:
        text = Text(_body_text([page]))
        if "research_area" not in fields and (m := text.search(_AREA)):
            put("research_area", text.group(m), page.number)
        # Spaced text here: the table's columns (planned, actual) are separate numbers.
        report = kind == "close" and "ค่าใช้จ่ายจริง" in text.compact
        if report and "spent_total" not in fields and (m := _SPENT.search(_body_text([page]))):
            spent = thai.parse_money(m[2])
            put("spent_total", str(spent) if spent is not None else None, page.number)

    warnings = [
        {"code": "missing_field", "field": name}
        for name in REQUIRED.get(kind or "", ())
        if name not in fields
    ]
    if kind is None:
        warnings.append({"code": "unknown_paper_type"})
    return {"kind": kind, "fields": fields, "warnings": warnings}
