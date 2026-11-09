"""Session idle timeout, and an append-only audit log.

- `sessions.last_seen_at`: a session ends after `session_idle_minutes` without a request.
- `audit_events` rejects UPDATE, DELETE and TRUNCATE. This guards against bugs and stray
  SQL; a superuser can still disable the trigger on purpose.

Revision ID: e4b7a1c9d025
Revises: c5e1f0a7d392
Create Date: 2026-11-09 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b7a1c9d025"
down_revision: str | Sequence[str] | None = "c5e1f0a7d392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        """
        CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit_events is append-only (% blocked)', TG_OP;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_change BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER audit_events_no_change ON audit_events")
    op.execute("DROP FUNCTION audit_events_append_only()")
    op.drop_column("sessions", "last_seen_at")
