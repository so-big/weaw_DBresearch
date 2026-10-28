"""Append-only audit trail (CLAUDE.md: downloads, shares, admin actions, purges)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from dbresearch.models import AuditEvent


def record(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    *,
    actor_id: uuid.UUID | None = None,
    ip: str | None = None,
    **details: Any,
) -> None:
    """Add an audit row to the current transaction (the caller commits).

    `details` must never contain document text, passwords, or tokens.
    """
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in details.items()},
            ip=ip,
        )
    )
