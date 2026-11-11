"""Document search: space-insensitive text match, filters, facets, snippets (DESIGN §5)."""

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy import Select, case, exists, func, or_, select
from sqlalchemy.orm import Session

from dbresearch.models import (
    Category,
    CategoryGroup,
    DocKind,
    DocStatus,
    Document,
    DocumentCategory,
    DocumentPage,
    DocumentPerson,
    DocumentTag,
    DocumentVersion,
    FundingSource,
    FundingType,
    Person,
    PersonRole,
    ProposalProject,
    Tag,
    VersionPurpose,
)
from dbresearch.search_text import compact
from dbresearch.textnorm import normalize

SORTS = ("relevance", "newest", "oldest", "title", "reference")
# The web app's sections (DESIGN §11): research contracts, proposal-development grants, and
# programme papers. 'all' = every document (review queue, counts).
SECTIONS = ("contracts", "proposals", "other", "all")
PROJECT_STATES = ("active", "overdue", "closed", "cancelled")
SNIPPET_RADIUS = 60


@dataclass
class Filters:
    q: str | None = None
    # Several values in one filter mean "any of these".
    kind: list[DocKind] = field(default_factory=list)
    funding_type: list[FundingType] = field(default_factory=list)
    fiscal_year: list[int] = field(default_factory=list)  # Gregorian
    status: list[DocStatus] = field(default_factory=list)
    categories: list[uuid.UUID] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    person: str | None = None
    ref_year_be: int | None = None
    ref_series: str | None = None
    uploaded_by: uuid.UUID | None = None
    project: list[str] = field(default_factory=list)  # 'open' / 'closed' (ปิดโครงการ = archive)
    section: str = "contracts"
    funding_source: list[FundingSource] = field(default_factory=list)
    state: list[str] = field(default_factory=list)  # PROJECT_STATES (proposal grants)
    department: list[str] = field(default_factory=list)  # the owner's unit
    research_area: list[str] = field(default_factory=list)


def section_condition(section: str):
    """Contracts include uploads whose kind isn't set yet (they are reviewed as contracts);
    proposal grants and programme papers get their kind at upload."""
    if section == "proposals":
        return Document.kind == DocKind.PROPOSAL_DEV
    if section == "other":
        return Document.kind == DocKind.OTHER
    if section == "contracts":
        return or_(Document.kind.is_(None), Document.kind.in_((DocKind.CONTRACT, DocKind.GRANT)))
    return None


def _kpi_due():
    return (
        select(ProposalProject.kpi_due)
        .where(ProposalProject.document_id == Document.id)
        .correlate(Document)  # stays valid inside queries that join proposal_projects
        .scalar_subquery()
    )


def state_expression():
    """cancelled / closed (success) / overdue (past the KPI due date) / active."""
    return case(
        (Document.cancelled_at.is_not(None), "cancelled"),
        (Document.closed_at.is_not(None), "closed"),
        (_kpi_due() < date.today(), "overdue"),
        else_="active",
    )


def _owner_unit():
    return (
        select(DocumentPerson.unit)
        .where(DocumentPerson.document_id == Document.id, DocumentPerson.role == PersonRole.OWNER)
        .correlate(Document)
        .limit(1)
        .scalar_subquery()
    )


def _like(text: str) -> str:
    """ILIKE pattern for a literal substring."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _conditions(db: Session, f: Filters) -> list:
    conds = [Document.deleted_at.is_(None)]
    if (section := section_condition(f.section)) is not None:
        conds.append(section)
    if f.q and (needle := compact(f.q)):
        conds.append(Document.search_text.ilike(_like(needle)))
    if f.kind:
        conds.append(Document.kind.in_(f.kind))
    if f.funding_type:
        conds.append(Document.funding_type.in_(f.funding_type))
    if f.funding_source:
        conds.append(Document.funding_source.in_(f.funding_source))
    if f.state:
        # 'active' includes overdue projects; 'overdue' alone narrows to them.
        wanted = set(f.state)
        state = state_expression()
        if "active" in wanted:
            wanted |= {"active", "overdue"}
        conds.append(state.in_(sorted(wanted)))
    if f.department:
        conds.append(_owner_unit().in_(f.department))
    if f.research_area:
        conds.append(
            exists().where(
                ProposalProject.document_id == Document.id,
                ProposalProject.research_area.in_(f.research_area),
            )
        )
    if f.fiscal_year:
        conds.append(Document.fiscal_year.in_(f.fiscal_year))
    if f.status:
        conds.append(Document.status.in_(f.status))
    if f.ref_year_be:
        conds.append(Document.ref_year_be == f.ref_year_be)
    if f.ref_series:
        conds.append(Document.ref_series == f.ref_series.upper())
    if f.uploaded_by:
        conds.append(Document.uploaded_by == f.uploaded_by)
    if set(f.project) == {"open"}:
        conds.append(Document.closed_at.is_(None))
    elif set(f.project) == {"closed"}:
        conds.append(Document.closed_at.is_not(None))
    if f.categories:
        # OR within a group (either research type), AND across groups (type and group).
        by_group: dict[uuid.UUID, list[uuid.UUID]] = {}
        for category_id, group_id in db.execute(
            select(Category.id, Category.group_id).where(Category.id.in_(f.categories))
        ):
            by_group.setdefault(group_id, []).append(category_id)
        for ids in by_group.values():
            conds.append(
                exists().where(
                    DocumentCategory.document_id == Document.id,
                    DocumentCategory.category_id.in_(ids),
                )
            )
    for tag in f.tags:
        conds.append(
            exists().where(
                DocumentTag.document_id == Document.id,
                DocumentTag.tag_id == Tag.id,
                Tag.normalized == re.sub(r"\s+", " ", normalize(tag)).strip().lower(),
            )
        )
    if f.person and (needle := compact(f.person)):
        name = func.lower(func.replace(func.concat(Person.name_th, Person.name_en), " ", ""))
        conds.append(
            exists().where(
                DocumentPerson.document_id == Document.id,
                DocumentPerson.person_id == Person.id,
                name.ilike(_like(needle)),
            )
        )
    return conds


def _order(query: Select, f: Filters, sort: str) -> Select:
    if sort == "relevance" and f.q and (needle := compact(f.q)):
        title_hit = case(
            (func.lower(func.replace(Document.title, " ", "")).ilike(_like(needle)), 1), else_=0
        )
        return query.order_by(
            title_hit.desc(),
            func.word_similarity(needle, Document.search_text).desc(),
            Document.updated_at.desc(),
        )
    if sort == "oldest":
        return query.order_by(Document.created_at.asc())
    if sort == "title":
        return query.order_by(Document.title.asc())
    if sort == "reference":
        return query.order_by(
            Document.ref_year_be.desc().nulls_last(),
            Document.ref_series.asc(),
            Document.ref_seq.asc(),
            Document.reference_no.asc(),
        )
    return query.order_by(Document.updated_at.desc())


def search(
    db: Session, f: Filters, sort: str = "relevance", page: int = 1, page_size: int = 20
) -> tuple[list[Document], int]:
    conds = _conditions(db, f)
    total = db.scalar(select(func.count()).select_from(Document).where(*conds)) or 0
    query = _order(select(Document).where(*conds), f, sort)
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def facets(db: Session, f: Filters) -> dict[str, list[dict]]:
    """Counts for the filter sidebar.

    Each group is counted with every filter except its own, so ticking 2568 still shows how
    many documents 2567 would add (the UI combines values within a group with OR)."""

    def ids_without(**cleared) -> Select:
        return select(Document.id).where(*_conditions(db, replace(f, **cleared)))

    def counts(column, name: str) -> list[dict]:
        rows = db.execute(
            select(column, func.count())
            .where(Document.id.in_(ids_without(**{name: []})), column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc())
        ).all()
        return [{"value": value, "count": count} for value, count in rows]

    group_of = dict(
        db.execute(
            select(Category.id, Category.group_id).where(Category.id.in_(f.categories))
        ).all()
    )
    category_rows = []
    for group_id in db.scalars(select(CategoryGroup.id)):
        others = [c for c in f.categories if group_of.get(c) != group_id]
        category_rows += db.execute(
            select(Category.id, Category.name_th, CategoryGroup.key, func.count())
            .join(DocumentCategory, DocumentCategory.category_id == Category.id)
            .join(CategoryGroup, CategoryGroup.id == Category.group_id)
            .where(
                Category.group_id == group_id,
                DocumentCategory.document_id.in_(ids_without(categories=others)),
            )
            .group_by(Category.id, Category.name_th, CategoryGroup.key)
            .order_by(func.count().desc())
        ).all()
    project = case((Document.closed_at.is_(None), "open"), else_="closed")
    project_rows = db.execute(
        select(project, func.count())
        .where(Document.id.in_(ids_without(project=[])))
        .group_by(project)
    ).all()
    out = {
        "project": [{"value": value, "count": count} for value, count in project_rows],
        "kind": counts(Document.kind, "kind"),
        "funding_type": counts(Document.funding_type, "funding_type"),
        "funding_source": counts(Document.funding_source, "funding_source"),
        "fiscal_year": counts(Document.fiscal_year, "fiscal_year"),
        "status": counts(Document.status, "status"),
        "categories": [
            {"value": str(cid), "name": name, "group_key": key, "count": count}
            for cid, name, key, count in category_rows
        ],
    }
    if f.section == "proposals":
        state = state_expression()
        out["state"] = [
            {"value": value, "count": count}
            for value, count in db.execute(
                select(state, func.count())
                .where(Document.id.in_(ids_without(state=[])))
                .group_by(state)
            ).all()
        ]
        out["department"] = counts(_owner_unit(), "department")
        out["research_area"] = [
            {"value": value, "count": count}
            for value, count in db.execute(
                select(ProposalProject.research_area, func.count())
                .where(
                    ProposalProject.document_id.in_(ids_without(research_area=[])),
                    ProposalProject.research_area.is_not(None),
                )
                .group_by(ProposalProject.research_area)
                .order_by(func.count().desc())
            ).all()
        ]
    return out


def proposal_rows(db: Session, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """List-row extras for proposal grants: state, KPI due date, department, request memo no."""
    request_ref = (
        select(ProposalProject.request_ref)
        .where(ProposalProject.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Document.id, state_expression(), _kpi_due(), _owner_unit(), request_ref).where(
            Document.id.in_(document_ids), Document.kind == DocKind.PROPOSAL_DEV
        )
    ).all()
    return {
        doc_id: {"state": st, "kpi_due": due, "department": unit, "request_ref": ref}
        for doc_id, st, due, unit, ref in rows
    }


def owners(db: Session, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    rows = db.execute(
        select(DocumentPerson.document_id, Person.prefix_th, Person.name_th, Person.name_en)
        .join(Person, Person.id == DocumentPerson.person_id)
        .where(
            DocumentPerson.document_id.in_(document_ids), DocumentPerson.role == PersonRole.OWNER
        )
    ).all()
    result: dict[uuid.UUID, list[str]] = {}
    for doc_id, prefix, name_th, name_en in rows:
        result.setdefault(doc_id, []).append(f"{prefix or ''}{name_th or name_en}")
    return result


def snippets(db: Session, documents: list[Document], q: str | None) -> dict[uuid.UUID, str]:
    """Text around the first match in each document's current version and closing papers
    (spaces ignored). One query for the whole result page loads only each document's first
    matching page; documents with no page hit (e.g. a metadata-only hit) are left out."""
    needle = compact(q) if q else ""
    ids = [d.id for d in documents if d.current_version_id is not None]
    if len(needle) < 2 or not ids:
        return {}
    current = DocumentVersion.id == Document.current_version_id
    squashed = func.regexp_replace(DocumentPage.text, r"\s+", "", "g")
    rows = db.execute(
        select(Document.id, DocumentPage.text)
        .select_from(Document)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(DocumentPage, DocumentPage.version_id == DocumentVersion.id)
        .where(
            Document.id.in_(ids),
            or_(
                current, DocumentVersion.purpose.in_((VersionPurpose.CLOSURE, VersionPurpose.PAPER))
            ),
            squashed.ilike(_like(needle)),
        )
        .distinct(Document.id)  # DISTINCT ON: first matching page per document
        .order_by(Document.id, case((current, 0), else_=1), DocumentPage.page_no)
    ).all()
    found = {}
    for doc_id, text in rows:
        if hit := _snippet_in(text, needle):
            found[doc_id] = hit
    return found


def _snippet_in(text: str, needle: str) -> str | None:
    positions = [i for i, ch in enumerate(text) if not ch.isspace()]
    squashed = "".join(text[i] for i in positions).lower()
    at = squashed.find(needle)
    if at < 0:
        return None
    start, end = positions[at], positions[at + len(needle) - 1] + 1
    before = text[max(0, start - SNIPPET_RADIUS) : start].replace("\n", " ")
    after = text[end : end + SNIPPET_RADIUS].replace("\n", " ")
    return f"{'…' if start > SNIPPET_RADIUS else ''}{before}[[{text[start:end]}]]{after}…"


def search_people(db: Session, q: str, limit: int = 10) -> list[Person]:
    needle = compact(q)
    if not needle:
        return []
    th = func.lower(func.replace(func.coalesce(Person.name_th, ""), " ", ""))
    en = func.lower(func.replace(func.coalesce(Person.name_en, ""), " ", ""))
    return list(
        db.scalars(
            select(Person)
            .where(or_(th.ilike(_like(needle)), en.ilike(_like(needle))))
            .order_by(Person.name_th)
            .limit(limit)
        )
    )
