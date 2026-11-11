"""Deleting accounts: user_status gains 'deleted'.

An account that was ever used (uploads, shares, audit rows) can't be removed, because the
append-only audit log points at it. Deleting it hides it from the user list and blocks
login instead; the name stays on its history and ADMIN can restore it. Never-used
accounts are removed for real (no schema change needed for that).

Downgrade swaps the enum type back and refuses while deleted users exist.

Revision ID: e1f3a5c7d9b2
Revises: c9d1f3a5b7e2
Create Date: 2026-11-12 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f3a5c7d9b2"
down_revision: str | Sequence[str] | None = "c9d1f3a5b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'deleted'")


def downgrade() -> None:
    deleted = op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE status = 'deleted'"))
    if deleted:
        raise RuntimeError(f"{deleted} deleted users: restore them before downgrading")
    op.execute("ALTER TABLE users ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE user_status RENAME TO user_status_old")
    op.execute("CREATE TYPE user_status AS ENUM ('active', 'disabled', 'pending')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN status TYPE user_status USING status::text::user_status"
    )
    op.execute("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'active'")
    op.execute("DROP TYPE user_status_old")
