"""Tune contract_body rules after the first real-scan run.

- document_date: OCR drops tone marks ('เมือวันที' for 'เมื่อวันที่'), so allow them to be missing
- owner (footer): stop before a following 'สัญญาเลขที่' when rows are read in another order

Revision ID: 29040f1da640
Revises: 595587b56f80
Create Date: 2026-10-28 11:29:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "29040f1da640"
down_revision: str | Sequence[str] | None = "595587b56f80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATE = r"\d{1,2}\s*(?:[฀-๿.]{2,12}|/\s*\d{1,2}\s*/)\s*(?:25\d\d|\d{2})"
NEW = {
    "document_date": rf"เม\S{{0,2}}อ\s*วันท\S{{0,2}}\s*({DATE})",
    "owner": r"หน้า\s*\d+\s+(.{3,80}?)\s*(?:สัญญาเลขที่|$)",
}
OLD = {
    "document_date": rf"เมื่อวันที่\s*({DATE})",
    "owner": r"หน้า\s*\d+\s+(.{3,80})$",
}


def _set_patterns(patterns: dict[str, str]) -> None:
    conn = op.get_bind()
    rules = conn.execute(
        sa.text("SELECT field_rules FROM extraction_templates WHERE name = 'contract_body'")
    ).scalar_one_or_none()
    if rules is None:  # ADMIN removed the template: nothing to tune
        return
    for rule in rules["rules"]:
        if rule["field"] in patterns:
            rule["pattern"] = patterns[rule["field"]]
    conn.execute(
        sa.text(
            "UPDATE extraction_templates SET field_rules = CAST(:rules AS jsonb), "
            "updated_at = now() WHERE name = 'contract_body'"
        ),
        {"rules": json.dumps(rules, ensure_ascii=False)},
    )


def upgrade() -> None:
    _set_patterns(NEW)


def downgrade() -> None:
    _set_patterns(OLD)
