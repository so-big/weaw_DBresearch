"""Proposal-development grants: project fields, timeline events, cancel (DESIGN §11).

Every change writes an audit row; the caller commits. Closing reuses `documents.close_project`
(the archive works the same for contracts and grants).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch import audit
from dbresearch.models import (
    FUNDING_TYPE_OF,
    DocKind,
    Document,
    DocumentVersion,
    FundingSource,
    ProjectEvent,
    ProjectEventType,
    ProposalProject,
    User,
)

PAPER_EVENTS = {
    "title_change": ProjectEventType.TITLE_CHANGE,
    "budget_change": ProjectEventType.BUDGET_CHANGE,
    "close": ProjectEventType.CLOSE,
    "cancel": ProjectEventType.CANCEL,
    "other": ProjectEventType.OTHER,
}


class ProjectError(ValueError):
    """A request the project's state doesn't allow; the message is safe to show."""


def is_proposal(document: Document) -> bool:
    return document.kind == DocKind.PROPOSAL_DEV


def ensure_proposal(db: Session, document: Document) -> ProposalProject:
    details = db.get(ProposalProject, document.id)
    if details is None:
        details = ProposalProject(document_id=document.id)
        db.add(details)
        db.flush()
    return details


def set_funding(document: Document, source: FundingSource | None, funder: str | None) -> None:
    """funding_type follows the source (FF counts as external); the DB checks it too."""
    document.funding_source = source
    document.funder_name = (funder or "").strip() or None
    if source is not None:
        document.funding_type = FUNDING_TYPE_OF[source]


def apply_proposal(db: Session, document: Document, data: Any) -> None:
    """Review form → proposal fields. A linked contract must be a live contract."""
    details = ensure_proposal(db, document)
    values = data.model_dump()
    linked = values.get("outcome_document_id")
    if linked is not None:
        target = db.get(Document, linked)
        if target is None or target.deleted_at is not None or target.id == document.id:
            raise ProjectError("The linked contract doesn't exist")
    for name, value in values.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(details, name, value)
    has_approval = db.scalar(
        select(ProjectEvent.id).where(
            ProjectEvent.document_id == document.id,
            ProjectEvent.event_type == ProjectEventType.APPROVED,
        )
    )
    if has_approval is None:
        # The request memo itself is the approval (the main file).
        db.add(
            ProjectEvent(
                document_id=document.id,
                event_type=ProjectEventType.APPROVED,
                event_on=document.document_date,
                memo_ref=details.request_ref,
                version_id=document.current_version_id,
            )
        )


def add_event(
    db: Session,
    user: User,
    document: Document,
    event_type: ProjectEventType,
    *,
    version: DocumentVersion | None = None,
    event_on: date | None = None,
    memo_ref: str | None = None,
    details: dict | None = None,
) -> ProjectEvent:
    event = ProjectEvent(
        document_id=document.id,
        event_type=event_type,
        event_on=event_on,
        memo_ref=(memo_ref or "").strip() or None,
        version_id=version.id if version else None,
        details=details or {},
        created_by=user.id,
    )
    db.add(event)
    db.flush()
    return event


def change_title(db: Session, user: User, document: Document, new_title: str, ip: str | None):
    """A title-change memo was approved: the project goes by its new title; the old one
    stays findable in the event (search_text indexes it)."""
    old = document.title
    document.title = new_title.strip()
    audit.record(db, "document.title_change", "document", document.id, actor_id=user.id, ip=ip)
    return {"old_title": old, "new_title": document.title}


def cancel_project(
    db: Session,
    user: User,
    document: Document,
    *,
    cancelled_on: date | None,
    cancel_ref: str | None,
    cancel_reason: str | None,
    ip: str | None,
) -> None:
    """Mark the project cancelled (or edit the details). Never both closed and cancelled."""
    if document.closed_at is not None:
        raise ProjectError("A closed project can't be cancelled; reopen it first")
    first = document.cancelled_at is None
    if first:
        document.cancelled_at = datetime.now(UTC)
        document.cancelled_by = user.id
    document.cancelled_on = cancelled_on
    document.cancel_ref = (cancel_ref or "").strip() or None
    document.cancel_reason = (cancel_reason or "").strip() or None
    audit.record(
        db,
        "document.cancel" if first else "document.cancel_update",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        cancelled_on=cancelled_on.isoformat() if cancelled_on else None,
    )


def clear_cancel(document: Document) -> None:
    document.cancelled_at = None
    document.cancelled_by = None
    document.cancelled_on = None
    document.cancel_ref = None
    document.cancel_reason = None


def update_event(
    db: Session, user: User, document: Document, event_id: uuid.UUID, data: Any, ip: str | None
) -> ProjectEvent:
    event = db.get(ProjectEvent, event_id)
    if event is None or event.document_id != document.id:
        raise ProjectError("Event not found")
    event.event_on = data.event_on
    event.memo_ref = (data.memo_ref or "").strip() or None
    note = (data.note or "").strip()
    details = dict(event.details or {})
    if note:
        details["note"] = note
    else:
        details.pop("note", None)
    event.details = details
    audit.record(
        db,
        "document.event_update",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        event=event.event_type.value,
    )
    return event
