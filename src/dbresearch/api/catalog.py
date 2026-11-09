"""Search and the pickers the UI needs (categories, people); users may add category options."""

import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from dbresearch import audit, search
from dbresearch.auth import DB, CurrentUser, client_ip
from dbresearch.models import (
    Category,
    CategoryGroup,
    DocKind,
    DocStatus,
    FundingSource,
    FundingType,
)
from dbresearch.schemas import (
    CategoryGroupOut,
    CategoryNew,
    CategoryOption,
    DocumentSummary,
    PersonBrief,
    SearchOut,
)
from dbresearch.search_text import compact
from dbresearch.textnorm import normalize

router = APIRouter(tags=["search"])


@router.get("/documents", response_model=SearchOut)
def list_documents(
    db: DB,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[list[DocKind], Query()] = [],  # noqa: B006 (FastAPI query list)
    funding_type: Annotated[list[FundingType], Query()] = [],  # noqa: B006
    fiscal_year: Annotated[list[int], Query(description="Gregorian fiscal years")] = [],  # noqa: B006
    status: Annotated[list[DocStatus], Query()] = [],  # noqa: B006 (FastAPI query list)
    category: Annotated[list[uuid.UUID], Query()] = [],  # noqa: B006
    tag: Annotated[list[str], Query()] = [],  # noqa: B006
    person: Annotated[str | None, Query(max_length=100)] = None,
    ref_year_be: int | None = None,
    ref_series: Annotated[str | None, Query(max_length=1)] = None,
    mine: bool = False,
    project: Annotated[list[Literal["open", "closed"]], Query()] = [],  # noqa: B006
    section: Annotated[
        str, Query(pattern="^(" + "|".join(search.SECTIONS) + ")$", description="web app section")
    ] = "contracts",
    funding_source: Annotated[list[FundingSource], Query()] = [],  # noqa: B006
    state: Annotated[list[Literal["active", "overdue", "closed", "cancelled"]], Query()] = [],  # noqa: B006
    department: Annotated[list[str], Query(max_length=300)] = [],  # noqa: B006
    research_area: Annotated[list[str], Query(max_length=300)] = [],  # noqa: B006
    sort: Annotated[str, Query(pattern="^(" + "|".join(search.SORTS) + ")$")] = "relevance",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    with_facets: bool = False,
):
    filters = search.Filters(
        q=q,
        kind=kind,
        funding_type=funding_type,
        fiscal_year=fiscal_year,
        status=status,
        categories=category,
        tags=tag,
        person=person,
        ref_year_be=ref_year_be,
        ref_series=ref_series,
        uploaded_by=user.id if mine else None,
        project=project,
        section=section,
        funding_source=funding_source,
        state=state,
        department=department,
        research_area=research_area,
    )
    documents, total = search.search(db, filters, sort, page, page_size)
    ids = [d.id for d in documents]
    owners = search.owners(db, ids)
    extras = search.proposal_rows(db, ids)
    items = []
    for document in documents:
        item = DocumentSummary.model_validate(document)
        item.owners = owners.get(document.id, [])
        for name, value in extras.get(document.id, {}).items():
            setattr(item, name, value)
        item.snippet = search.snippet(db, document, q)
        items.append(item)
    return SearchOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        facets=search.facets(db, filters) if with_facets else None,
    )


@router.get("/categories", response_model=list[CategoryGroupOut])
def list_categories(db: DB, user: CurrentUser, include_inactive: bool = False):
    groups = db.scalars(select(CategoryGroup).order_by(CategoryGroup.sort)).all()
    query = select(Category).order_by(Category.sort, Category.name_th)
    if not include_inactive:
        query = query.where(Category.active.is_(True))
    options: dict[uuid.UUID, list[CategoryOption]] = {}
    for c in db.scalars(query):
        options.setdefault(c.group_id, []).append(
            CategoryOption(id=c.id, name_th=c.name_th, name_en=c.name_en, active=c.active)
        )
    return [
        CategoryGroupOut(
            id=g.id,
            key=g.key,
            name_th=g.name_th,
            name_en=g.name_en,
            multi=g.multi,
            options=options.get(g.id, []),
        )
        for g in groups
    ]


@router.post("/categories", response_model=CategoryOption)
def add_category(
    body: CategoryNew, request: Request, response: Response, db: DB, user: CurrentUser
):
    """Add an option to a category group while reviewing. Any user may (department decision
    2026-11-02); admins tidy the list later. An option that already exists (same name,
    spacing ignored, or one of its aliases) is returned instead of a duplicate."""
    group = db.get(CategoryGroup, body.group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category group not found")
    name = re.sub(r"\s+", " ", normalize(body.name_th)).strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name is empty")
    for option in db.scalars(select(Category).where(Category.group_id == group.id)):
        if compact(name) in {compact(n) for n in [option.name_th, *option.aliases]}:
            return CategoryOption.model_validate(option, from_attributes=True)
    sort = db.scalar(select(func.max(Category.sort)).where(Category.group_id == group.id))
    category = Category(group_id=group.id, name_th=name, sort=(sort or 0) + 1)
    db.add(category)
    db.flush()
    audit.record(
        db,
        "category.create",
        "category",
        category.id,
        actor_id=user.id,
        ip=client_ip(request),
        group=group.key,
        name=name,
        from_review=True,
    )
    db.commit()
    response.status_code = status.HTTP_201_CREATED
    return CategoryOption.model_validate(category, from_attributes=True)


@router.get("/people", response_model=list[PersonBrief])
def find_people(db: DB, user: CurrentUser, q: Annotated[str, Query(min_length=1, max_length=100)]):
    return search.search_people(db, q)
