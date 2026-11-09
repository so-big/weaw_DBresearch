"""FF (Fundamental Fund) counts as internal funding, not external (decided 2026-11-11).

Existing documents with funding_source = 'ff' switch to funding_type = 'internal', and the
check that keeps funding_type in step with funding_source now lists 'ff' as internal.
Downgrade puts both back (FF rows become external again).

Revision ID: d5a7c3e9f1b2
Revises: b8e3f6a2c4d1
Create Date: 2026-11-11 11:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d5a7c3e9f1b2"
down_revision: str | Sequence[str] | None = "b8e3f6a2c4d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_documents_funding_type_matches_source"


def _switch(internal_sources: str, ff_type: str) -> None:
    op.drop_constraint(op.f(CHECK), "documents", type_="check")
    op.execute(f"UPDATE documents SET funding_type = '{ff_type}' WHERE funding_source = 'ff'")
    op.create_check_constraint(
        op.f(CHECK),
        "documents",
        "funding_source IS NULL OR (funding_type IS NOT NULL AND "
        f"(funding_source IN ({internal_sources})) = (funding_type = 'internal'))",
    )


def upgrade() -> None:
    _switch("'ff', 'nu_income', 'faculty_income'", "internal")


def downgrade() -> None:
    _switch("'nu_income', 'faculty_income'", "external")
