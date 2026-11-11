"""Received numbers (เลขรับ): the faculty's stamp on each proposal-development paper.

`proposal_projects.received_no` is the request's; `project_events.received_no` is each
timeline paper's. Both are searchable (search_text). Downgrade drops the columns (the typed
numbers are lost).

Revision ID: a7c4e2b9f6d3
Revises: d5a7c3e9f1b2
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c4e2b9f6d3"
down_revision: str | Sequence[str] | None = "d5a7c3e9f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("proposal_projects", sa.Column("received_no", sa.String(), nullable=True))
    op.add_column("project_events", sa.Column("received_no", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_events", "received_no")
    op.drop_column("proposal_projects", "received_no")
