"""The researcher page: everything one person has in the system (live documents only)."""

import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from dbresearch.models import (
    DocKind,
    Document,
    DocumentPerson,
    Person,
    PersonRole,
    ProposalProject,
)
from dbresearch.schemas import BE_OFFSET
from dbresearch.search import state_expression
from dbresearch.search_text import compact

SIMILAR_NAME = 0.8  # pg_trgm similarity of the spacing-free names
ROLE_ORDER = {PersonRole.OWNER: 0, PersonRole.CO_INVESTIGATOR: 1}


def _be(year: int | None) -> int | None:
    return year + BE_OFFSET if year else None


def _newest_first(item: dict):
    return (item["fiscal_year"] is None, -(item["fiscal_year"] or 0), item["title"])


def similar_people(db: Session, person: Person) -> list[Person]:
    """Other rows whose name, spaces ignored, is equal or very close (possible duplicates)."""
    conds = []
    for column, name in ((Person.name_th, person.name_th), (Person.name_en, person.name_en)):
        needle = compact(name or "")
        if needle:
            squashed = func.lower(func.replace(func.coalesce(column, ""), " ", ""))
            conds.append(func.similarity(squashed, needle) >= SIMILAR_NAME)
    if not conds:
        return []
    return list(
        db.scalars(
            select(Person)
            .where(Person.id != person.id, or_(*conds))
            .order_by(Person.name_th, Person.name_en)
            .limit(10)
        )
    )


def person_page(db: Session, person: Person) -> dict:
    rows = db.execute(
        select(
            Document,
            DocumentPerson.role,
            DocumentPerson.share_pct,
            DocumentPerson.unit,
            state_expression(),
            ProposalProject.request_ref,
        )
        .join(DocumentPerson, DocumentPerson.document_id == Document.id)
        .outerjoin(ProposalProject, ProposalProject.document_id == Document.id)
        .where(
            DocumentPerson.person_id == person.id,
            Document.deleted_at.is_(None),
            Document.kind.is_distinct_from(DocKind.OTHER),
        )
    ).all()

    docs: dict[uuid.UUID, dict] = {}
    units: set[str] = set()
    for document, role, share_pct, unit, state, request_ref in rows:
        if unit:
            units.add(unit)
        item = docs.get(document.id)
        if item is not None and ROLE_ORDER.get(item["role"], 9) <= ROLE_ORDER.get(role, 9):
            continue  # one entry per document: the main role wins
        proposal = document.kind == DocKind.PROPOSAL_DEV
        docs[document.id] = {
            "id": document.id,
            "kind": document.kind,
            "title": document.title,
            "reference_no": document.reference_no,
            "request_ref": request_ref if proposal else None,
            "fiscal_year": document.fiscal_year,
            "fiscal_year_be": _be(document.fiscal_year),
            "funding_source": document.funding_source,
            "funding_type": document.funding_type,
            "budget_total": document.budget_total,
            "role": role,
            "share_pct": share_pct,
            "status": document.status,
            "project": None if proposal else ("closed" if document.closed_at else "open"),
            "state": state if proposal else None,
        }

    items = sorted(docs.values(), key=_newest_first)
    by_year: dict[int | None, dict] = {}
    by_source: dict = {}
    for item in items:  # each document once
        budget = item["budget_total"] or Decimal(0)
        for bucket, key, extra in (
            (by_year, item["fiscal_year"], {"fiscal_year_be": item["fiscal_year_be"]}),
            (by_source, item["funding_source"], {}),
        ):
            entry = bucket.setdefault(key, {"count": 0, "budget": Decimal(0), **extra})
            entry["count"] += 1
            entry["budget"] += budget
    owner_count = sum(1 for i in items if i["role"] == PersonRole.OWNER)
    return {
        "person": person,
        "units": sorted(units),
        "contracts": [i for i in items if i["kind"] != DocKind.PROPOSAL_DEV],
        "proposals": [i for i in items if i["kind"] == DocKind.PROPOSAL_DEV],
        "total": {
            "count": len(items),
            "budget": sum((i["budget_total"] or Decimal(0) for i in items), Decimal(0)),
        },
        "as_owner": owner_count,
        "as_member": len(items) - owner_count,
        "by_year": [
            {"fiscal_year": k, **v}
            for k, v in sorted(by_year.items(), key=lambda kv: (kv[0] is None, -(kv[0] or 0)))
        ],
        "by_source": [
            {"funding_source": k, **v}
            for k, v in sorted(by_source.items(), key=lambda kv: -kv[1]["count"])
        ],
        "similar": similar_people(db, person),
    }
