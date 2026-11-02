"""Close a project (ปิดโครงการ): closing papers stored as 'closure' versions + closed fields.

Main versions and closing papers are numbered separately, so the unique key gains `purpose`.
Downgrade drops closing papers' rows (their blobs stay; backups keep everything).

Revision ID: a3d9c2e71b54
Revises: 7c1e5a9d2f40
Create Date: 2026-11-02 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3d9c2e71b54"
down_revision: str | Sequence[str] | None = "7c1e5a9d2f40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURPOSE = postgresql.ENUM("main", "closure", name="version_purpose", create_type=False)


def upgrade() -> None:
    PURPOSE.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "document_versions",
        sa.Column("purpose", PURPOSE, server_default=sa.text("'main'"), nullable=False),
    )
    op.drop_constraint(
        op.f("uq_document_versions_document_id_version_no"), "document_versions", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_document_versions_document_id_purpose_version_no"),
        "document_versions",
        ["document_id", "purpose", "version_no"],
    )
    op.add_column("documents", sa.Column("closed_on", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("closed_by", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("closure_ref", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("closure_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_closed_by_users"), "documents", "users", ["closed_by"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_documents_closed_by_users"), "documents", type_="foreignkey")
    for column in ("closure_note", "closure_ref", "closed_by", "closed_at", "closed_on"):
        op.drop_column("documents", column)
    op.execute("DELETE FROM document_versions WHERE purpose = 'closure'")
    op.drop_constraint(
        op.f("uq_document_versions_document_id_purpose_version_no"),
        "document_versions",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_document_versions_document_id_version_no"),
        "document_versions",
        ["document_id", "version_no"],
    )
    op.drop_column("document_versions", "purpose")
    PURPOSE.drop(op.get_bind(), checkfirst=False)
