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
    Person,
    Tag,
)
from dbresearch.textnorm import normalize

_SPACE = re.compile(r"\s+")


def compact(text: str) -> str:
    """The form both stored text and queries take before ILIKE: normalised, no whitespace."""
    return _SPACE.sub("", normalize(text)).lower()


def build(db: Session, document: Document) -> str:
    """Metadata + people + labels + OCR text of the current version."""
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
    if document.current_version_id is not None:
        parts += db.scalars(
            select(DocumentPage.text)
            .where(DocumentPage.version_id == document.current_version_id)
            .order_by(DocumentPage.page_no)
        ).all()
    return compact(" ".join(p for p in parts if p))
