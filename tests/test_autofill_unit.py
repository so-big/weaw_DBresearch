"""Auto-fill engine on synthetic pages. Layouts mimic the real forms; all values are fake."""

import uuid
from datetime import date

import pytest

from dbresearch.autofill import thai
from dbresearch.autofill.categories import CategoryIndex, Group, Option, compact
from dbresearch.autofill.page import Page
from dbresearch.autofill.pipeline import _infer_roles, best_values, field_warnings, team_people
from dbresearch.autofill.rules import Candidate, extract, match_label
from dbresearch.autofill.sections import TemplateSpec, split_sections
from dbresearch.ocr_layout import Line, Word

H = 40  # text height (px at 300 dpi)
PAGE_H = 3508


def line(text: str, left: int = 300, top: int = 500, conf: float = 92.0) -> Line:
    words, x = [], left
    for part in text.split(" "):
        words.append(Word(part, x, top, 30 * len(part), H, conf))
        x += 30 * len(part) + int(0.8 * H)
    return Line(text, tuple(words), conf)


def page(number: int, *lines: Line) -> Page:
    return Page(number, 2480, PAGE_H, list(lines))


def body(*texts: str, start: int = 400, left: int = 300) -> list[Line]:
    return [line(t, left, start + i * 80) for i, t in enumerate(texts)]


FOOTER_Y = int(PAGE_H * 0.93)


# ───────────── thai helpers ─────────────
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 กันยายน 2568", date(2025, 9, 1)),
        ("3 ก.พ. 68", date(2025, 2, 3)),
        ("1/9/2568", date(2025, 9, 1)),
        ("31 สิงหาคม 2569", date(2026, 8, 31)),
        ("2 กุมภาพันธ 2569", date(2026, 2, 2)),  # OCR dropped the final mark
        ("31 กุมภาพันธ์ 2568", None),  # impossible date
        ("no date", None),
    ],
)
def test_parse_thai_date(text, expected):
    assert thai.parse_thai_date(text) == expected


def test_fiscal_year_runs_october_to_september():
    assert thai.fiscal_year_of(date(2024, 9, 30)) == 2024
    assert thai.fiscal_year_of(date(2024, 10, 1)) == 2025


def test_amount_words_and_people():
    assert thai.words_to_amount("(สองแสนเก้าหมื่นบาทถ้วน)") == 290000
    assert thai.words_to_amount("หนี่งหมื่นบาหล้วน") is None  # garbled OCR → no verdict
    assert thai.split_person("ผศ.ดร.สมชาย ใจดี") == ("ผศ.ดร.", "สมชาย ใจดี")
    assert thai.split_person(".นางสาวสมหญิง รักงาน........., ") == ("นางสาว", "สมหญิง รักงาน")
    assert thai.parse_money("290,000.00") == thai.parse_money("290000")


# ───────────── labels ─────────────
def test_match_label_tolerates_numbering_spaces_and_one_misread():
    assert match_label("ประเภทการวิจัย", "1. ประเภทการวิจัย (ระบุ)") is not None
    score, start = match_label("ชื่อโครงการวิจัย", "ขือโครงการวิจัย : (ภาษาไทย) X")
    assert score >= 88 and "ภาษาไทย" in "ขือโครงการวิจัย : (ภาษาไทย) X"[start:]
    # 'งบประมาณรา…' scores 90 on its own; the separator rule is what rejects it.
    rule = [{"field": "budget", "layout": "label", "labels": ["งบประมาณรวม"]}]
    p = page(1, *body("งบประมาณรายได้คณะตัวอย่าง ประจำปี 2568"))
    assert extract(rule, [p], [p]) == []


TITLE_RULES = [
    {"field": "title", "layout": "label", "labels": ["โครงการ"], "continue": 1},
    {
        "field": "title",
        "layout": "label",
        "labels": ["ชื่อโครงการวิจัย", "(ภาษาไทย)"],
        "continue": 2,
        "pattern": r"(?:\(?\s*ภาษาไทย\s*\)?)?\s*:?\s*(.+)",
        "group": 1,
    },
    {"field": "title_en", "layout": "label", "labels": ["(ภาษาอังกฤษ)"], "continue": 3},
]


def test_inline_label_with_wrapped_continuation_but_not_the_paragraph():
    p = page(
        1,
        line("โครงการ : การพัฒนาระบบทดสอบ", 300, 400),
        line("มหาวิทยาลัยตัวอย่าง", 520, 480),
        line("สัญญานี้ทำขึ้น ณ มหาวิทยาลัยตัวอย่าง", 300, 560),
    )
    (cand,) = [c for c in extract(TITLE_RULES, [p], [p]) if c.field == "title"]
    assert cand.value == "การพัฒนาระบบทดสอบ มหาวิทยาลัยตัวอย่าง"


def test_body_text_starting_with_a_label_word_is_not_a_label():
    p = page(1, *body("โครงการวิจัยไม่เกิน 12 เดือน นับตั้งแต่วันที่ 1 มกราคม 2568"))
    assert extract(TITLE_RULES, [p], [p]) == []


def test_label_alone_then_value_lines_stop_at_next_label():
    p = page(
        3,
        line("ขือโครงการวิจัย :", 300, 400),
        line("(ภาษาไทย ) ระบบทดสอบตัวอย่าง", 600, 480),
        line("คณะตัวอย่าง", 900, 560),
        line("(ภาษาอังกฤษ) Example Test System", 600, 640),
        line("for Demonstration", 900, 720),
    )
    values = {(c.field, c.value) for c in extract(TITLE_RULES, [p], [p])}
    assert ("title", "ระบบทดสอบตัวอย่าง คณะตัวอย่าง") in values
    assert ("title_en", "Example Test System for Demonstration") in values


# ───────────── footer ─────────────
FOOTER_RULES = [
    {
        "field": "reference_no",
        "layout": "footer",
        "pattern": r"R\s?25\d\d\s?[A-Z]\s?\d{1,4}",
        "group": 0,
        "post": ["compact", "upper"],
    },
    {
        "field": "owner",
        "layout": "footer",
        "pattern": r"หน้า\s*\d+\s+(.{3,80}?)\s*(?:สัญญาเลขที่|$)",
        "group": 1,
        "post": ["strip_leaders"],
    },
]


def footer_page(number: int, ref: str, name: str, scrambled: bool = False) -> Page:
    left = line(f"สัญญาเลขที่ {ref} หน้า {number}", 300, FOOTER_Y + 4)
    right = line(name, 1900, FOOTER_Y)  # a few px higher: Tesseract lists it first
    return page(number, *body("เนื้อหา"), *([right, left] if scrambled else [left, right]))


def test_footer_rows_are_read_left_to_right_and_majority_wins():
    pages = [
        footer_page(1, "R2568A001", "สมหญิง รักงาน", scrambled=True),
        footer_page(2, "R2568A001", "สมหญิง รักงาน"),
        footer_page(3, "R2568A007", "สมหญิง รักงาน"),
    ]  # one misread page
    found = extract(FOOTER_RULES, [], pages)
    refs = [c for c in found if c.field == "reference_no"]
    assert refs[0].value == "R2568A001" and refs[0].confidence == pytest.approx(5 / 6, 0.01)
    # One page one character off is an OCR slip, not a second contract in the PDF.
    assert "conflict" not in refs[0].extra
    assert [c.value for c in found if c.field == "owner"] == ["สมหญิง รักงาน"]


def test_footer_conflict_needs_several_pages_with_another_number():
    pages = [footer_page(n, "R2568A001", "สมหญิง รักงาน") for n in (1, 2, 3)]
    pages += [footer_page(n, "R2568E012", "สมชาย ใจดี") for n in (4, 5)]
    refs = [c for c in extract(FOOTER_RULES, [], pages) if c.field == "reference_no"]
    assert refs[0].extra["conflict"] == ["R2568A001", "R2568E012"]


# ───────────── sentences ─────────────
DATE = thai.DATE_RE
SENTENCE_RULES = [
    {
        "field": "document_date",
        "layout": "sentence",
        "pattern": rf"เม\S{{0,2}}อ\s*วันท\S{{0,2}}\s*({DATE})",
        "group": 1,
        "post": ["thai_date"],
    },
    {
        "field": "effective_to",
        "layout": "sentence",
        "pattern": rf"นับ(?:ตั้ง)?แต่วันที่\s*({DATE})\s*ถึงวันที่?\s*({DATE})",
        "group": 2,
        "post": ["thai_date"],
    },
    {
        "field": "budget_total",
        "layout": "sentence",
        "pattern": r"ในวงเงิน\s*([\d,]+(?:\.\d{2})?)\s*\S{0,4}\s*\(([^)]{3,80})\)",
        "group": 1,
        "words_group": 2,
        "post": ["money"],
    },
]


def test_contract_clauses_with_ocr_damage():
    p = page(
        1,
        *body(
            "ตั้งอยู่ที่ 1 ถนนตัวอย่าง เมือวันที",
            "1 กันยายน 2568 ระหว่าง",
            "ในวงเงิน 10,000 vin (หนึ่งแสนบาทถ้วน) โดยมีระยะเวลา",
            "นับตั้งแต่วันที่ 1 กันยายน 2568 ถึงวันที่ 31 สิงหาคม 2569",
        ),
    )
    found = {c.field: c for c in extract(SENTENCE_RULES, [p], [p])}
    assert found["document_date"].value == date(2025, 9, 1)
    assert found["effective_to"].value == date(2026, 8, 31)
    budget = found["budget_total"]
    assert str(budget.value) == "10000" and budget.extra["words_amount"] == 100000
    warnings = field_warnings(best_values(list(found.values())), list(found.values()), [])
    assert {"code": "amount_words_mismatch", "digits": "10000", "words": 100000} in warnings


# ───────────── research team ─────────────
TEAM_RULE = [{"field": "team", "layout": "team", "labels": ["ชื่อ - สกุล", "ชื่อ-สกุล"]}]


def test_team_block_with_misreads_and_dotted_lines():
    p = page(
        3,
        *body(
            "ชื่อ - สกุล .นางสาวสมหญิง รักงาน ........., สัตส่วนการทำวิจั ย %) ......80......",
            "หน่วยงาน ... หน่วยตัวอย่าง คณะตัวอย่าง",
            "บทบาทในโครงการ Me alr ligeeee nen",
            "ชื่อ - สกุล นายสมชาย ใจดี สัดส่วนการทำวิจัย(%) ......2 0",
            "หน่วยงาน ....... งานตัวอย่าง",
            "บทบาทในโครงการ ....ผู้ร่วมวิจัย.........",
        ),
    )
    people = [c.value for c in extract(TEAM_RULE, [p], [p])]
    assert [(x["prefix_th"], x["name"], x["share_pct"]) for x in people] == [
        ("นางสาว", "สมหญิง รักงาน", 80.0),
        ("นาย", "สมชาย ใจดี", 20.0),
    ]
    assert people[0]["unit"] == "หน่วยตัวอย่าง คณะตัวอย่าง"
    assert people[0]["role"] is None  # garbled → inferred later
    assert people[1]["role"] == "co_investigator"


def test_footer_owner_merges_with_team_member_despite_one_misread():
    team = [
        Candidate(
            "team",
            {
                "prefix_th": "นางสาว",
                "name": "สมหญิง รักงาน",
                "role": None,
                "share_pct": 80.0,
                "unit": None,
            },
            0.9,
            3,
            "team",
        )
    ]
    fields = {"owner": {"value": "สมหญิง รักงาม", "confidence": 0.6}}  # one char off
    people = team_people(team, fields)
    assert len(people) == 1 and people[0]["role"] == "owner"


def test_roles_default_to_first_person_without_footer_owner():
    people = [{"name": "ก"}, {"name": "ข", "role": "co_investigator"}, {"name": "ค"}]
    _infer_roles(people, None)
    assert [p["role"] for p in people] == ["owner", "co_investigator", "co_investigator"]


# ───────────── sections ─────────────
def spec(name: str, attachment_no, keywords, checkbox=False) -> TemplateSpec:
    return TemplateSpec(
        uuid.uuid4(),
        name,
        attachment_no,
        None,
        None,
        tuple(keywords),
        2,
        (),
        checkbox,
        10 if attachment_no is None else 5,
    )


TEMPLATES = [
    spec("contract_body", None, ["สัญญารับทุนอุดหนุนการวิจัย", "สัญญานี้ทำขึ้น"]),
    spec("att_budget", 1, ["งบประมาณรวม", "รายละเอียดค่าใช้จ่าย"]),
    spec("att_proposal_form", 5, ["แบบเสนอโครงการวิจัย", "ลักษณะโครงการวิจัย"], checkbox=True),
]


def test_sections_ignore_marker_on_contract_page_and_keep_unknown_attachments():
    pages = [
        page(
            1,
            line("เอกสารแนบ 1", 1900, 150),
            *body(
                "สัญญารับทุนอุดหนุนการวิจัย [ตัวอย่าง]",
                "จากงบประมาณรายได้คณะตัวอย่าง",
                "สัญญานี้ทำขึ้น ณ มหาวิทยาลัยตัวอย่าง",
            ),
        ),
        page(2, *body("ข้อ 5 ผู้รับทุนจะต้อง", "ข้อ 6 ...")),  # contract continues
        page(
            3,
            line("เอกสารแนบหมายเลข 1", 1700, 200),
            *body("งบประมาณรวม ในวงเงิน 10,000 บาท", start=900),
        ),
        page(4, line("เอกสารแนบหมายเลขที่ 3", 1700, 200), *body("แผนการดำเนินงาน", start=900)),
        page(
            5,
            line("เอกสารแนบหมายเลข 5", 1700, 200),
            *body("แบบเสนอโครงการวิจัย", "ส่วน ก : ลักษณะโครงการวิจัย", start=900),
        ),
    ]
    sections = split_sections(pages, TEMPLATES)
    assert [
        (s.template.name if s.template else None, s.attachment_no, [p.number for p in s.pages])
        for s in sections
    ] == [
        ("contract_body", None, [1, 2]),
        ("att_budget", 1, [3]),
        (None, 3, [4]),
        ("att_proposal_form", 5, [5]),
    ]


# ───────────── categories ─────────────
def group(key, names, options, multi=False) -> Group:
    return Group(
        uuid.uuid4(),
        key,
        names[0],
        multi,
        tuple(compact(n) for n in names),
        tuple(Option(uuid.uuid4(), o, (compact(o),)) for o in options),
    )


INDEX = CategoryIndex(
    [
        group(
            "research_type",
            ["ประเภทการวิจัย", "ประเภทวิจัย"],
            ["เพื่อแก้ปัญหา", "เพื่อการวางแผนพัฒนา", "เพื่อการประกันคุณภาพ"],
        ),
        group("research_group", ["กลุ่มการวิจัย"], ["นิสิต / นักศึกษา", "บุคลากร"]),
        group("agency", ["แหล่งทุน"], ["งบประมาณรายได้คณะวิศวกรรมศาสตร์"]),
    ]
)


def test_checkbox_headings_and_options_match_fuzzily():
    research = INDEX.match_group("ประเภทการวิจัย")
    assert research.key == "research_type"
    assert INDEX.match_group("ประเภทวิจัย").key == "research_type"
    assert INDEX.match_group("ส่วน ข : องค์ประกอบ") is None
    assert INDEX.match_option(research, "เพื่อการวางัแผนพัฒนา").category_name == "เพื่อการวางแผนพัฒนา"
    assert INDEX.match_option(research, "เพื่อการ") is None  # ambiguous → no guess
    found = INDEX.find_in_text("agency", "จากงบประมาณรายได้คณะวิศวกรรมศาสตร์ ประจำปี")
    assert found.category_name == "งบประมาณรายได้คณะวิศวกรรมศาสตร์"
