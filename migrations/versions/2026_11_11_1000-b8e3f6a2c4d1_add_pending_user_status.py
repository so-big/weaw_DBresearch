"""Approval queue: user_status gains 'pending'.

A first university login that matches nobody ADMIN added creates a pending user; ADMIN
approves (active) or rejects (disabled) it. Downgrade swaps the enum type back and refuses
while pending users exist.

Revision ID: b8e3f6a2c4d1
Revises: f2c8d4a1b7e3
Create Date: 2026-11-11 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e3f6a2c4d1"
down_revision: str | Sequence[str] | None = "f2c8d4a1b7e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'pending'")


def downgrade() -> None:
    pending = op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE status = 'pending'"))
    if pending:
        raise RuntimeError(f"{pending} pending users: approve or reject them before downgrading")
    op.execute("ALTER TABLE users ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE user_status RENAME TO user_status_old")
    op.execute("CREATE TYPE user_status AS ENUM ('active', 'disabled')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN status TYPE user_status USING status::text::user_status"
    )
    op.execute("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'active'")
    op.execute("DROP TYPE user_status_old")
