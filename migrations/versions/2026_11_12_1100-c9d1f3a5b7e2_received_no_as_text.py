"""received_no columns are `text`, like the other reference numbers (a7c4e2b9f6d3 made
them varchar, which the models don't match).

Revision ID: c9d1f3a5b7e2
Revises: a7c4e2b9f6d3
Create Date: 2026-11-12 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d1f3a5b7e2"
down_revision: str | Sequence[str] | None = "a7c4e2b9f6d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("proposal_projects", "project_events")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "received_no", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "received_no", type_=sa.String(), existing_nullable=True)
