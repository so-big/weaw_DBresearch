"""Tune auto-fill on the 13 contracts of ทุนวิจัย ปี 68 รอบ 1, and add the form's options.

Templates (replaced as a whole; downgrade restores the seed + first tune):
- contract_body: owner from the parties clause ('… ฝ่ายหนึ่ง กับ <name> ซึ่งต่อไป…ผู้รับทุน'),
  title stops at 'สัญญานี้ทำขึ้น', contract no. repaired ('R256BE001' → 'R2568E001'),
  looser heading keywords ('ญารับทุนอุดหนุน…' must still classify the page)
- att_budget: installments (งวดที่ N จำนวน X บาท / ร้อยละ P / condition) as suggestions
- att_proposal_form: team block anchored on หน่วยงาน + บทบาทในโครงการ, English names from
  the CV part, English title never a person's name

Categories: options printed on the real proposal form that the seed lacked.

Revision ID: c5e1f0a7d392
Revises: a3d9c2e71b54
Create Date: 2026-11-02 10:10:00
"""

import copy
import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "c5e1f0a7d392"
down_revision: str | Sequence[str] | None = "a3d9c2e71b54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed = _load("2026_10_28_1126-595587b56f80_seed_extraction_templates.py")
_tune = _load("2026_10_28_1129-29040f1da640_tune_contract_body_rules.py")

DATE = _seed.DATE
MONEY = _seed.MONEY
FISCAL_YEAR = _seed.FISCAL_YEAR
# 'นับตั้งแต่ วันที่20 มกราคม 2568ถึงวันที่19 มกราคม 2569' (OCR adds and drops spaces).
PERIOD = rf"นับ\s*(?:ตั้ง)?\s*แต่\s*วันท\S{{0,2}}\s*({DATE})\s*ถึง\s*วันท\S{{0,2}}\s*({DATE})"
# '(งบประมาณรวม) ใน / วงเงิน 100,000 บาท (หนึ่งแสนบาทถ้วน)': the clause may wrap after 'ใน'.
TOTAL = rf"ใน\s*วงเงิน\s*({MONEY})\s*\S{{0,4}}\s*\(([^)]{{3,80}})\)"
CONTRACT_FOOTER = {
    "field": "reference_no",
    "layout": "footer",
    # B/S/O/I misread as digits are repaired by the 'contract_no' step.
    "pattern": r"R\s?[25BSO][0-9BSOIl]{3}\s?[A-Z]\s?[0-9BSOIl]{1,4}",
    "group": 0,
    "post": ["contract_no"],
}

NEW = {
    "contract_body": {
        "match_rules": {
            "keywords": [
                "สัญญารับทุนอุดหนุนการวิจัย",
                "รับทุนอุดหนุนการวิจัย",
                "สัญญานี้ทำขึ้น",
                "การให้และรับทุน",
                "ผู้รับทุน",
            ],
            "min_score": 2,
        },
        "rules": [
            {
                "field": "title",
                "layout": "label",
                "labels": ["โครงการ"],
                "continue": 2,
                "stop": ["สัญญานี้ทำขึ้น", "สัญญาฉบับนี้"],
                "post": ["strip_leaders"],
            },
            {
                "field": "title",
                "layout": "sentence",
                "pattern": r"เรื่อง\s*[“\"](.{5,300}?)[”\"]",
                "group": 1,
                "post": ["strip_leaders"],
            },
            CONTRACT_FOOTER,
            {
                "field": "owner",
                "layout": "sentence",
                # '… “ผู้ให้ทุน” ฝ่ายหนึ่ง กับ ผศ. ดร.<name> ซึ่งต่อไปในสัญญานี้เรียกว่า “ผู้รับทุน”'
                "pattern": r"ฝ่ายหนึ่ง\s*(?:กับ|\S{0,3})\s*(\S.{2,80}?)\s*ซ\S{0,2}ง\s*ต่อ\s*ไป",
                "group": 1,
                "post": ["person"],
            },
            {
                "field": "owner",
                "layout": "footer",
                "pattern": _tune.NEW["owner"],
                "group": 1,
                "post": ["person"],
            },
            FISCAL_YEAR,
            {
                "field": "document_date",
                "layout": "sentence",
                "pattern": _tune.NEW["document_date"],
                "group": 1,
                "post": ["thai_date"],
            },
            {
                "field": "effective_from",
                "layout": "sentence",
                "pattern": PERIOD,
                "group": 1,
                "post": ["thai_date"],
            },
            {
                "field": "effective_to",
                "layout": "sentence",
                "pattern": PERIOD,
                "group": 2,
                "post": ["thai_date"],
            },
            {
                "field": "budget_total",
                "layout": "sentence",
                "pattern": TOTAL,
                "group": 1,
                "words_group": 2,
                "post": ["money"],
            },
        ],
    },
    "att_budget": {
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
                "stop": ["การจ่ายเงิน", "งบประมาณรวม", "งบประมาณ"],
                "post": ["strip_leaders"],
            },
            {
                "field": "budget_total",
                "layout": "sentence",
                "pattern": TOTAL,
                "group": 1,
                "words_group": 2,
                "post": ["money"],
            },
            {"field": "budget_lines", "layout": "installments"},
        ],
    },
    "att_proposal_form": {
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
                "stop": ["ประเภททุน", "ส่วน ก"],
                "reject": r"(?i)^(?:mr|mrs|miss|ms|dr|asst|assoc|prof)\b",
                "post": ["strip_leaders"],
            },
            FISCAL_YEAR,
            {"field": "team", "layout": "team"},
            {"field": "team_en", "layout": "names_en"},
        ],
    },
}

NEW_OPTIONS = {
    "research_type": ["ประยุกต์"],
    "research_group": ["มนุษยศาสตร์และสังคมศาสตร์"],
    # The 12 NRCT disciplines as printed on the form (สาขาวิชาการ).
    "discipline": [
        "วิทยาศาสตร์กายภาพและคณิตศาสตร์",
        "วิทยาศาสตร์การแพทย์",
        "วิทยาศาสตร์เคมีและเภสัช",
        "เกษตรศาสตร์และชีววิทยา",
        "วิศวกรรมศาสตร์และอุตสาหกรรมวิจัย",
        "ปรัชญา",
        "นิติศาสตร์",
        "รัฐศาสตร์และรัฐประศาสนศาสตร์",
        "เศรษฐศาสตร์",
        "สังคมวิทยา",
        "เทคโนโลยีสารสนเทศและนิเทศศาสตร์",
        "การศึกษา",
    ],
}


def _old() -> dict[str, dict]:
    old = {}
    for t in copy.deepcopy(_seed.TEMPLATES):
        if t["name"] == "contract_body":
            for rule in t["rules"]:
                if rule["field"] in _tune.NEW:
                    rule["pattern"] = _tune.NEW[rule["field"]]
        old[t["name"]] = {"match_rules": t["match_rules"], "rules": t["rules"]}
    return old


def _write(templates: dict[str, dict]) -> None:
    conn = op.get_bind()
    for name, t in templates.items():
        conn.execute(
            sa.text(
                "UPDATE extraction_templates SET match_rules = CAST(:match AS jsonb), "
                "field_rules = CAST(:rules AS jsonb), updated_at = now() WHERE name = :name"
            ),
            {
                "name": name,
                "match": json.dumps(t["match_rules"], ensure_ascii=False),
                "rules": json.dumps({"rules": t["rules"]}, ensure_ascii=False),
            },
        )


def upgrade() -> None:
    _write(NEW)
    conn = op.get_bind()
    for key, names in NEW_OPTIONS.items():
        for name in names:
            conn.execute(
                sa.text(
                    "INSERT INTO categories (group_id, name_th, sort) "
                    "SELECT g.id, :name, 100 + (SELECT count(*) FROM categories c "
                    "WHERE c.group_id = g.id) FROM category_groups g WHERE g.key = :key "
                    "ON CONFLICT (group_id, name_th) DO NOTHING"
                ),
                {"key": key, "name": name},
            )


def downgrade() -> None:
    _write(_old())
    conn = op.get_bind()
    for key, names in NEW_OPTIONS.items():
        # Only the options this migration added and nobody has used since.
        conn.execute(
            sa.text(
                "DELETE FROM categories c USING category_groups g WHERE c.group_id = g.id "
                "AND g.key = :key AND c.name_th = ANY(:names) AND c.sort >= 100 "
                "AND NOT EXISTS (SELECT 1 FROM document_categories d WHERE d.category_id = c.id)"
            ),
            {"key": key, "names": names},
        )
