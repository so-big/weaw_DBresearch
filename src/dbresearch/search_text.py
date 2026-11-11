"""Space-insensitive search text (DESIGN §5): normalise, then drop ALL whitespace."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch.models import (
    Category,
    Document,
    DocumentCategory,
    DocumentPage,
    DocumentPerson,
    DocumentTag,
    DocumentVersion,
    Person,
    ProjectEvent,
    ProposalProject,
    Tag,
    VersionPurpose,
)
from dbresearch.textnorm import normalize

_SPACE = re.compile(r"\s+")


def compact(text: str) -> str:
    """The form both stored text and queries take before ILIKE: normalised, no whitespace."""
    return _SPACE.sub("", normalize(text)).lower()


def build(db: Session, document: Document, extra: str = "") -> str:
    """Metadata + people + labels + OCR text of the current version and closing papers."""
    parts = [document.title, document.title_en or "", document.reference_no or "", extra]
    parts += db.scalars(
        select(Person.name_th).join(DocumentPerson).where(DocumentPerson.document_id == document.id)
    ).all()
    parts += db.scalars(
        select(Person.name_en).join(DocumentPerson).where(DocumentPerson.document_id == document.id)
    ).all()
    parts += db.scalars(
        select(Category.name_th)
        .join(DocumentCategory)
        .where(DocumentCategory.document_id == document.id)
    ).all()
    parts += db.scalars(
        select(Tag.name).join(DocumentTag).where(DocumentTag.document_id == document.id)
    ).all()
    # Memo numbers (ที่ อว 0603.09.05/108): the request, each timeline paper, closing, cancelling.
    # Often handwritten, so OCR text alone rarely carries them.
    parts += [document.closure_ref or "", document.cancel_ref or ""]
    parts += db.scalars(
        select(ProposalProject.request_ref).where(
            ProposalProject.document_id == document.id, ProposalProject.request_ref.is_not(None)
        )
    ).all()
    # Received numbers (เลขรับ) of the request and of each paper.
    parts += db.scalars(
        select(ProposalProject.received_no).where(
            ProposalProject.document_id == document.id, ProposalProject.received_no.is_not(None)
        )
    ).all()
    parts += db.scalars(
        select(ProjectEvent.received_no).where(
            ProjectEvent.document_id == document.id, ProjectEvent.received_no.is_not(None)
        )
    ).all()
    parts += db.scalars(
        select(ProjectEvent.memo_ref).where(
            ProjectEvent.document_id == document.id, ProjectEvent.memo_ref.is_not(None)
        )
    ).all()
    # Earlier titles of a project (title changes keep the old one findable).
    parts += db.scalars(
        select(ProjectEvent.details["old_title"].astext).where(
            ProjectEvent.document_id == document.id, ProjectEvent.details.has_key("old_title")
        )
    ).all()
    # OCR text of the current version, then of the other papers (closing, cancel, change).
    closing = select(DocumentVersion.id).where(
        DocumentVersion.document_id == document.id,
        DocumentVersion.purpose.in_((VersionPurpose.CLOSURE, VersionPurpose.PAPER)),
    )
    parts += db.scalars(
        select(DocumentPage.text)
        .where(
            (DocumentPage.version_id == document.current_version_id)
            | DocumentPage.version_id.in_(closing)
        )
        .order_by(DocumentPage.version_id != document.current_version_id, DocumentPage.page_no)
    ).all()
    return compact(" ".join(p for p in parts if p))


def rebuild_for_category(db: Session, category_id: uuid.UUID, batch: int = 200) -> int:
    """Rebuild search_text of every document tagged with the category, a batch per commit."""
    done, last = 0, None
    while True:
        query = (
            select(Document)
            .join(DocumentCategory, DocumentCategory.document_id == Document.id)
            .where(DocumentCategory.category_id == category_id)
            .order_by(Document.id)
            .limit(batch)
        )
        if last is not None:
            query = query.where(Document.id > last)
        documents = db.scalars(query).all()
        if not documents:
            return done
        for document in documents:
            document.search_text = build(db, document)
        last = documents[-1].id
        done += len(documents)
        db.commit()
