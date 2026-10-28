"""Allow empty kind / funding_type until a document is reviewed.

Auto-fill finds both after upload, so they can't be required at insert time. A document
can only become 'ready' once both are set (ck_documents_ready_is_complete).

Downgrade fails if any document still has them empty, which is intended.

Revision ID: b3bfb163b94e
Revises: 154ab4ea7816
Create Date: 2026-10-28 11:16:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3bfb163b94e"
down_revision: str | Sequence[str] | None = "154ab4ea7816"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("documents", "kind", nullable=True)
    op.alter_column("documents", "funding_type", nullable=True)
    op.create_check_constraint(
        op.f("ck_documents_ready_is_complete"),
        "documents",
        "status <> 'ready' OR (kind IS NOT NULL AND funding_type IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_documents_ready_is_complete"), "documents", type_="check")
    op.alter_column("documents", "funding_type", nullable=False)
    op.alter_column("documents", "kind", nullable=False)
