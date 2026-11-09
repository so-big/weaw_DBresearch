"""Save reviewed metadata: fields, categories, tags, people and budget lines → status 'ready'."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from dbresearch import audit, search_text
from dbresearch.autofill.thai import fiscal_year_of
from dbresearch.models import (
    BudgetLine,
    Category,
    CategoryGroup,
    DocKind,
    DocStatus,
    Document,
    DocumentCategory,
    DocumentPerson,
    DocumentTag,
    Person,
    Tag,
    User,
)
from dbresearch.projects import ProjectError, apply_proposal, set_funding
from dbresearch.schemas import MetadataIn, ProposalIn
from dbresearch.textnorm import normalize


class MetadataError(ValueError):
    """Rejected input; the message is safe to show."""


class ReferenceTaken(MetadataError):
    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__("Another document already has this contract number")
        self.document_id = document_id


def normalize_reference(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", normalize(value)).upper() or None


def normalize_tag(name: str) -> str:
    return re.sub(r"\s+", " ", normalize(name)).strip().lower()


def _categories(db: Session, data: MetadataIn) -> list[tuple[uuid.UUID, str]]:
    ids = [c.category_id for c in data.categories]
    rows = db.execute(
        select(Category.id, CategoryGroup.key, CategoryGroup.multi)
        .join(CategoryGroup, Category.group_id == CategoryGroup.id)
        .where(Category.id.in_(ids))
    ).all()
    if len(rows) != len(set(ids)):
        raise MetadataError("Unknown category")
    per_group: dict[str, int] = {}
    for _, key, multi in rows:
        per_group[key] = per_group.get(key, 0) + 1
        if not multi and per_group[key] > 1:
            raise MetadataError(f"Only one category can be chosen in group '{key}'")
    return [(c.category_id, c.source) for c in data.categories]


def _person(db: Session, entry) -> Person:
    if entry.person_id is not None:
        person = db.get(Person, entry.person_id)
        if person is None:
            raise MetadataError("Unknown person")
        return person
    name_th = normalize(entry.name_th).strip() if entry.name_th else None
    name_en = normalize(entry.name_en).strip() if entry.name_en else None
    if not name_th and not name_en:
        raise MetadataError("A person needs a Thai or English name")
    query = select(Person)
    query = (
        query.where(Person.name_th == name_th)
        if name_th
        else query.where(Person.name_en == name_en)
    )
    person = db.scalars(query.limit(1)).first()
    if person is None:
        person = Person(prefix_th=entry.prefix_th, name_th=name_th, name_en=name_en)
        db.add(person)
        db.flush()
    return person


def apply_metadata(
    db: Session, user: User, document: Document, data: MetadataIn, ip: str | None
) -> Document:
    """Replace the document's reviewed metadata and mark it ready. The caller commits."""
    reference = normalize_reference(data.reference_no)
    if reference:
        taken = db.scalar(
            select(Document.id).where(
                Document.reference_no == reference,
                Document.deleted_at.is_(None),
                Document.id != document.id,
            )
        )
        if taken is not None:
            raise ReferenceTaken(taken)

    before = {
        name: getattr(document, name)
        for name in (
            "title",
            "title_en",
            "kind",
            "funding_type",
            "reference_no",
            "document_date",
            "effective_from",
            "effective_to",
            "fiscal_year",
            "budget_total",
        )
    }
    document.title = normalize(data.title).strip()
    document.title_en = normalize(data.title_en).strip() if data.title_en else None
    document.kind = data.kind
    document.funding_type = data.funding_type
    set_funding(document, data.funding_source, data.funder_name)
    if document.funding_type is None and data.kind != DocKind.OTHER:
        raise MetadataError("Choose the funding source or internal/external funding")
    document.reference_no = reference
    document.document_date = data.document_date
    document.effective_from = data.effective_from
    document.effective_to = data.effective_to
    document.fiscal_year = data.fiscal_year or (
        fiscal_year_of(data.document_date) if data.document_date else None
    )
    document.budget_total = data.budget_total
    changed = sorted(k for k, v in before.items() if getattr(document, k) != v)

    categories = _categories(db, data)
    db.execute(delete(DocumentCategory).where(DocumentCategory.document_id == document.id))
    for category_id, source in categories:
        db.add(DocumentCategory(document_id=document.id, category_id=category_id, source=source))

    db.execute(delete(DocumentTag).where(DocumentTag.document_id == document.id))
    tag_ids: set[uuid.UUID] = set()
    for entry in data.tags:
        key = normalize_tag(entry.name)
        if not key:
            continue
        tag = db.scalar(select(Tag).where(Tag.normalized == key))
        if tag is None:
            tag = Tag(name=normalize(entry.name).strip(), normalized=key, created_by=user.id)
            db.add(tag)
            db.flush()
        if tag.id not in tag_ids:
            tag_ids.add(tag.id)
            db.add(DocumentTag(document_id=document.id, tag_id=tag.id, source=entry.source))

    db.execute(delete(DocumentPerson).where(DocumentPerson.document_id == document.id))
    seen: set[tuple[uuid.UUID, str]] = set()
    for entry in data.people:
        person = _person(db, entry)
        if (person.id, entry.role) in seen:
            continue
        seen.add((person.id, entry.role))
        db.add(
            DocumentPerson(
                document_id=document.id,
                person_id=person.id,
                role=entry.role,
                share_pct=entry.share_pct,
                unit=entry.unit,
            )
        )

    if data.proposal is not None or document.kind == DocKind.PROPOSAL_DEV:
        if document.kind != DocKind.PROPOSAL_DEV:
            raise MetadataError("Proposal fields only apply to proposal-development grants")
        try:
            apply_proposal(db, document, data.proposal or ProposalIn())
        except ProjectError as exc:
            raise MetadataError(str(exc)) from exc

    if data.budget_lines is not None:
        db.execute(delete(BudgetLine).where(BudgetLine.document_id == document.id))
        for sort, line in enumerate(data.budget_lines):
            db.add(BudgetLine(document_id=document.id, sort=sort, **line.model_dump()))

    first_review = document.status != DocStatus.READY
    document.status = DocStatus.READY
    document.updated_at = datetime.now(UTC)
    db.flush()
    document.search_text = search_text.build(db, document)
    audit.record(
        db,
        "document.confirm" if first_review else "document.update",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        fields=changed,
        categories=len(categories),
        tags=len(tag_ids),
        people=len(seen),
    )
    return document


def budget_sum(db: Session, document_id: uuid.UUID):
    return db.scalar(
        select(func.coalesce(func.sum(BudgetLine.amount), 0)).where(
            BudgetLine.document_id == document_id
        )
    )
