"""Seed the three section templates auto-fill needs (DESIGN §6 "Package structure").

- contract_body       the grant contract itself (header, parties, clauses, footer)
- att_budget          เอกสารแนบหมายเลข 1: money (only the total is auto-filled)
- att_proposal_form   เอกสารแนบหมายเลข 5: titles, checkbox groups, research team

Attachments 2–4 get no template: they are OCR'd for search only. ADMIN can tune these rows
later; the rule format is documented in dbresearch/autofill/rules.py.

Revision ID: 595587b56f80
Revises: b3bfb163b94e
Create Date: 2026-10-28 11:26:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "595587b56f80"
down_revision: str | Sequence[str] | None = "b3bfb163b94e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Thai date as written in contracts (same as dbresearch.autofill.thai.DATE_RE).
DATE = r"\d{1,2}\s*(?:[฀-๿.]{2,12}|/\s*\d{1,2}\s*/)\s*(?:25\d\d|\d{2})"
MONEY = r"[\d,]+(?:\.\d{2})?"
FISCAL_YEAR = {
    "field": "fiscal_year",
    "layout": "sentence",
    "pattern": r"ประจำปี(?:งบประมาณ)?.{0,20}?(25\d\d)",
    "group": 1,
    "post": ["be_year"],
}

TEMPLATES = [
    {
        "name": "contract_body",
        "attachment_no": None,
        "kind": "grant",
        "priority": 10,
        "checkbox_groups": False,
        "match_rules": {
            "keywords": ["สัญญารับทุนอุดหนุนการวิจัย", "สัญญานี้ทำขึ้น", "การให้และรับทุน"],
            "min_score": 2,
        },
        "rules": [
            {
                "field": "title",
                "layout": "label",
                "labels": ["โครงการ"],
                "continue": 1,
                "post": ["strip_leaders"],
            },
            {
                "field": "title",
                "layout": "sentence",
                "pattern": r"เรื่อง\s*[“\"](.{5,300}?)[”\"]",
                "group": 1,
                "post": ["strip_leaders"],
            },
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
                "pattern": r"หน้า\s*\d+\s+(.{3,80})$",
                "group": 1,
                "post": ["strip_leaders"],
            },
            FISCAL_YEAR,
            {
                "field": "document_date",
                "layout": "sentence",
                "pattern": rf"เมื่อวันที่\s*({DATE})",
                "group": 1,
                "post": ["thai_date"],
            },
            {
                "field": "effective_from",
                "layout": "sentence",
                "pattern": rf"นับ(?:ตั้ง)?แต่วันที่\s*({DATE})\s*ถึงวันที่?\s*({DATE})",
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
                "pattern": rf"ในวงเงิน\s*({MONEY})\s*\S{{0,4}}\s*\(([^)]{{3,80}})\)",
                "group": 1,
                "words_group": 2,
                "post": ["money"],
            },
        ],
    },
    {
        "name": "att_budget",
        "attachment_no": 1,
        "kind": None,
        "priority": 5,
        "checkbox_groups": False,
        "match_rules": {
            "keywords": ["งบประมาณรวม", "รายละเอียดค่าใช้จ่าย", "การจ่ายเงิน"],
            "min_score": 2,
        },
        "rules": [
            {
                "field": "title",
                "layout": "label",
                "labels": ["โครงการ"],
                "continue": 1,
                "post": ["strip_leaders"],
            },
            {
                "field": "budget_total",
                "layout": "sentence",
                "pattern": rf"งบประมาณรวม\s*ในวงเงิน\s*({MONEY})\s*\S{{0,4}}\s*\(([^)]{{3,80}})\)",
                "group": 1,
                "words_group": 2,
                "post": ["money"],
            },
        ],
    },
    {
        "name": "att_proposal_form",
        "attachment_no": 5,
        "kind": None,
        "priority": 5,
        "checkbox_groups": True,
        "match_rules": {
            "keywords": [
                "แบบเสนอโครงการวิจัย",
                "ลักษณะโครงการวิจัย",
                "ชื่อโครงการวิจัย",
                "องค์ประกอบในการจัดทำโครงการวิจัย",
            ],
            "min_score": 2,
        },
        "rules": [
            {
                "field": "title",
                "layout": "label",
                "labels": ["ชื่อโครงการวิจัย", "(ภาษาไทย)"],
                "continue": 2,
                "pattern": r"(?:\(?\s*ภาษาไทย\s*\)?)?\s*:?\s*(.+)",
                "group": 1,
                "post": ["strip_leaders"],
            },
            {
                "field": "title_en",
                "layout": "label",
                "labels": ["(ภาษาอังกฤษ)"],
                "continue": 3,
                "post": ["strip_leaders"],
            },
            FISCAL_YEAR,
            {"field": "team", "layout": "team", "labels": ["ชื่อ - สกุล", "ชื่อ-สกุล"]},
        ],
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for t in TEMPLATES:
        conn.execute(
            sa.text(
                "INSERT INTO extraction_templates (name, attachment_no, kind, match_rules, "
                "field_rules, checkbox_groups, priority) VALUES (:name, :attachment_no, "
                "CAST(:kind AS doc_kind), CAST(:match AS jsonb), CAST(:rules AS jsonb), "
                ":checkbox_groups, :priority)"
            ),
            {
                "name": t["name"],
                "attachment_no": t["attachment_no"],
                "kind": t["kind"],
                "match": json.dumps(t["match_rules"], ensure_ascii=False),
                "rules": json.dumps({"rules": t["rules"]}, ensure_ascii=False),
                "checkbox_groups": t["checkbox_groups"],
                "priority": t["priority"],
            },
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM extraction_templates WHERE name = ANY(:names)"),
        {"names": [t["name"] for t in TEMPLATES]},
    )
