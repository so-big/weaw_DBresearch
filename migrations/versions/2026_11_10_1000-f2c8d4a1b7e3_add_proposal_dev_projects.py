"""Proposal-development grants (ทุนพัฒนาข้อเสนอ) and funding sources.

- doc_kind gains 'proposal_dev' and 'other' (programme papers, no funding type needed);
  version_purpose gains 'paper' (cancellation / change memos).
- documents: funding_source (+ funder_name), with funding_type kept consistent by a check;
  cancelled_* (never both closed and cancelled).
- proposal_projects: fields only these grants have; project_events: each project's timeline.
- budget_lines.actual_amount: what was really spent (closing report).

Enum values are added in an autocommit block: PostgreSQL won't let the checks below use a
new value inside the transaction that created it. Downgrade swaps the enum types back and
refuses while rows still use the new values.

Revision ID: f2c8d4a1b7e3
Revises: e4b7a1c9d025
Create Date: 2026-11-10 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2c8d4a1b7e3"
down_revision: str | Sequence[str] | None = "e4b7a1c9d025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = postgresql.ENUM(
    "ff", "nu_income", "faculty_income", "external", name="funding_source", create_type=False
)
EVENT = postgresql.ENUM(
    "approved",
    "title_change",
    "budget_change",
    "close",
    "cancel",
    "reopen",
    "other",
    name="project_event_type",
    create_type=False,
)
OUTCOME = postgresql.ENUM("submitted", "won", "not_won", name="proposal_outcome", create_type=False)

READY_OLD = "status <> 'ready' OR (kind IS NOT NULL AND funding_type IS NOT NULL)"
READY_NEW = (
    "status <> 'ready' OR (kind IS NOT NULL AND (funding_type IS NOT NULL OR kind = 'other'))"
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE doc_kind ADD VALUE IF NOT EXISTS 'proposal_dev'")
        op.execute("ALTER TYPE doc_kind ADD VALUE IF NOT EXISTS 'other'")
        op.execute("ALTER TYPE version_purpose ADD VALUE IF NOT EXISTS 'paper'")
    bind = op.get_bind()
    for enum in (SOURCE, EVENT, OUTCOME):
        enum.create(bind, checkfirst=False)

    # documents: funding source + cancellation
    op.add_column("documents", sa.Column("funding_source", SOURCE, nullable=True))
    op.add_column("documents", sa.Column("funder_name", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("cancelled_on", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("cancelled_by", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("cancel_ref", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_cancelled_by_users"), "documents", "users", ["cancelled_by"], ["id"]
    )
    op.drop_constraint(op.f("ck_documents_ready_is_complete"), "documents", type_="check")
    op.create_check_constraint(op.f("ck_documents_ready_is_complete"), "documents", READY_NEW)
    op.create_check_constraint(
        op.f("ck_documents_funding_type_matches_source"),
        "documents",
        "funding_source IS NULL OR (funding_type IS NOT NULL AND "
        "(funding_source IN ('nu_income', 'faculty_income')) = (funding_type = 'internal'))",
    )
    op.create_check_constraint(
        op.f("ck_documents_closed_or_cancelled"),
        "documents",
        "closed_at IS NULL OR cancelled_at IS NULL",
    )

    op.add_column("budget_lines", sa.Column("actual_amount", sa.Numeric(14, 2), nullable=True))
    op.create_check_constraint(
        op.f("ck_budget_lines_actual_non_negative"), "budget_lines", "actual_amount >= 0"
    )

    op.create_table(
        "proposal_projects",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("request_ref", sa.Text(), nullable=True),
        sa.Column("research_area", sa.Text(), nullable=True),
        sa.Column("kpi_target", sa.Text(), nullable=True),
        sa.Column("kpi_due", sa.Date(), nullable=True),
        sa.Column("kpi_result", sa.Text(), nullable=True),
        sa.Column("spent_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("outcome", OUTCOME, nullable=True),
        sa.Column("outcome_funder", sa.Text(), nullable=True),
        sa.Column("outcome_document_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "spent_total >= 0", name=op.f("ck_proposal_projects_spent_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_proposal_projects_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outcome_document_id"],
            ["documents.id"],
            name=op.f("fk_proposal_projects_outcome_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_proposal_projects")),
    )
    op.create_table(
        "project_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", EVENT, nullable=False),
        sa.Column("event_on", sa.Date(), nullable=True),
        sa.Column("memo_ref", sa.Text(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_project_events_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            name=op.f("fk_project_events_version_id_document_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_project_events_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_events")),
    )
    op.create_index(
        "project_events_doc_idx", "project_events", ["document_id", "event_on"], unique=False
    )


def _swap_enum(name: str, values: tuple[str, ...], columns: list[tuple[str, str]]) -> None:
    """Recreate enum `name` with only `values` (PostgreSQL can't drop enum values)."""
    op.execute(f"ALTER TYPE {name} RENAME TO {name}_old")
    quoted = ", ".join(f"'{v}'" for v in values)
    op.execute(f"CREATE TYPE {name} AS ENUM ({quoted})")
    for table, column in columns:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {name} USING {column}::text::{name}"
        )
    op.execute(f"DROP TYPE {name}_old")


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM documents WHERE kind IN ('proposal_dev', 'other')) + "
            "(SELECT count(*) FROM extraction_templates WHERE kind IN ('proposal_dev', 'other')) + "
            "(SELECT count(*) FROM document_versions WHERE purpose = 'paper')"
        )
    )
    if in_use:
        raise RuntimeError(
            f"{in_use} rows use proposal_dev / other / paper: remove them before downgrading"
        )
    op.drop_index("project_events_doc_idx", table_name="project_events")
    op.drop_table("project_events")
    op.drop_table("proposal_projects")
    op.drop_constraint(op.f("ck_budget_lines_actual_non_negative"), "budget_lines", type_="check")
    op.drop_column("budget_lines", "actual_amount")

    op.drop_constraint(op.f("ck_documents_closed_or_cancelled"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_funding_type_matches_source"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_ready_is_complete"), "documents", type_="check")
    op.drop_constraint(op.f("fk_documents_cancelled_by_users"), "documents", type_="foreignkey")
    for column in (
        "cancel_reason",
        "cancel_ref",
        "cancelled_by",
        "cancelled_at",
        "cancelled_on",
        "funder_name",
        "funding_source",
    ):
        op.drop_column("documents", column)
    for enum in (OUTCOME, EVENT, SOURCE):
        enum.drop(bind, checkfirst=False)

    # documents_live_idx covers `kind`; ALTER COLUMN TYPE rebuilds it.
    _swap_enum(
        "doc_kind", ("contract", "grant"), [("documents", "kind"), ("extraction_templates", "kind")]
    )
    _swap_enum("version_purpose", ("main", "closure"), [("document_versions", "purpose")])
    op.execute("ALTER TABLE document_versions ALTER COLUMN purpose SET DEFAULT 'main'")
    op.create_check_constraint(op.f("ck_documents_ready_is_complete"), "documents", READY_OLD)
