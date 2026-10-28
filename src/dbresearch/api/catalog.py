"""Search and the read-only pickers the UI needs (categories, people)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from dbresearch import search
from dbresearch.auth import DB, CurrentUser
from dbresearch.models import Category, CategoryGroup, DocKind, DocStatus, FundingType
from dbresearch.schemas import (
    CategoryGroupOut,
    CategoryOption,
    DocumentSummary,
    PersonBrief,
    SearchOut,
)

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
    )
    documents, total = search.search(db, filters, sort, page, page_size)
    owners = search.owners(db, [d.id for d in documents])
    items = []
    for document in documents:
        item = DocumentSummary.model_validate(document)
        item.owners = owners.get(document.id, [])
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


@router.get("/people", response_model=list[PersonBrief])
def find_people(db: DB, user: CurrentUser, q: Annotated[str, Query(min_length=1, max_length=100)]):
    return search.search_people(db, q)
