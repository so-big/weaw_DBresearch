"""Record who opened a share link when they were logged in.

NULL for guests (and for every row logged before this change).

Revision ID: 7c1e5a9d2f40
Revises: 29040f1da640
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e5a9d2f40"
down_revision: str | Sequence[str] | None = "29040f1da640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("share_access_log", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_share_access_log_user_id_users"),
        "share_access_log",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_share_access_log_user_id_users"), "share_access_log", type_="foreignkey"
    )
    op.drop_column("share_access_log", "user_id")
