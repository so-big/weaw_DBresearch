"""Space-insensitive search text (DESIGN §5): normalise, then drop ALL whitespace."""

import re

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
    Tag,
    VersionPurpose,
)
from dbresearch.textnorm import normalize

_SPACE = re.compile(r"\s+")


def compact(text: str) -> str:
    """The form both stored text and queries take before ILIKE: normalised, no whitespace."""
    return _SPACE.sub("", normalize(text)).lower()


def build(db: Session, document: Document) -> str:
    """Metadata + people + labels + OCR text of the current version and closing papers."""
    parts = [document.title, document.title_en or "", document.reference_no or ""]
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
