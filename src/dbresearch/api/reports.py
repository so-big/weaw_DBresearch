"""Overview reports and chart data. Every user can read them (every user can read every
document anyway); figures about the system itself are for admins only."""

from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from dbresearch import shares
from dbresearch.auth import DB, CurrentUser
from dbresearch.models import (
    AuditEvent,
    Category,
    CategoryGroup,
    DocStatus,
    Document,
    DocumentCategory,
    DocumentVersion,
    OcrStatus,
    ShareLink,
    User,
    UserRole,
    UserStatus,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/missing-numbers")
def missing_numbers(
    db: DB, user: CurrentUser, year_be: int | None = None, series: str | None = None
) -> list[dict]:
    """Gaps in each year + series of contract numbers, e.g. internal 2568: E004, E007."""
    query = (
        select(
            Document.ref_year_be,
            Document.ref_series,
            func.array_agg(Document.ref_seq),
            func.max(Document.ref_seq),
        )
        .where(Document.deleted_at.is_(None), Document.ref_seq.is_not(None))
        .group_by(Document.ref_year_be, Document.ref_series)
        .order_by(Document.ref_year_be.desc(), Document.ref_series)
    )
    if year_be:
        query = query.where(Document.ref_year_be == year_be)
    if series:
        query = query.where(Document.ref_series == series.upper())
    report = []
    for year, letter, seqs, highest in db.execute(query):
        present = set(seqs)
        missing = [n for n in range(1, highest + 1) if n not in present]
        report.append(
            {
                "year_be": year,
                "series": letter,
                "highest": highest,
                "stored": len(present),
                "missing": [f"R{year}{letter}{n:03d}" for n in missing],
            }
        )
    return report


@router.get("/overview")
def overview(db: DB, user: CurrentUser) -> dict:
    """Headline figures. `my_trash` counts the caller's own bin; the system figures
    (whole trash, storage, live share links, users) are only sent to admins."""
    live = Document.deleted_at.is_(None)
    by_status = dict(
        db.execute(
            select(Document.status, func.count()).where(live).group_by(Document.status)
        ).all()
    )
    out = {
        "documents": {s.value: by_status.get(s, 0) for s in DocStatus},
        "ocr_failed": db.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(live, DocumentVersion.ocr_status == OcrStatus.FAILED)
        ),
        "my_trash": db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.deleted_at.is_not(None),
                or_(Document.uploaded_by == user.id, Document.deleted_by == user.id),
            )
        ),
    }
    if user.role != UserRole.ADMIN:
        return out
    active_links = sum(
        1
        for link in db.scalars(select(ShareLink).where(ShareLink.revoked_at.is_(None)))
        if shares.state(db, link) == shares.LinkState.ACTIVE
    )
    return out | {
        "in_trash": db.scalar(
            select(func.count()).select_from(Document).where(Document.deleted_at.is_not(None))
        ),
        "stored_bytes": int(
            db.scalar(select(func.coalesce(func.sum(DocumentVersion.size_bytes), 0)))
        ),
        "active_share_links": active_links,
        "users": db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.ACTIVE)
        ),
    }


# Charts group by the department's local calendar, not UTC.
LOCAL_TZ = "Asia/Bangkok"


def _month_keys(count: int) -> list[str]:
    """The last `count` months as 'YYYY-MM', oldest first, ending with this month (Bangkok)."""
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    year, month = today.year, today.month
    keys = []
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return keys[::-1]


def _day_keys(count: int) -> list[date]:
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    return [today - timedelta(days=n) for n in range(count - 1, -1, -1)]


@router.get("/charts")
def charts(
    db: DB,
    user: CurrentUser,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
    days: Annotated[int, Query(ge=7, le=180)] = 30,
) -> dict:
    """Data for the overview charts. Live documents only; counts, not file contents."""
    live = Document.deleted_at.is_(None)

    years: dict[int, dict] = {}
    for fiscal_year, funding, count, budget in db.execute(
        select(
            Document.fiscal_year,
            Document.funding_type,
            func.count(),
            func.coalesce(func.sum(Document.budget_total), 0),
        )
        .where(live, Document.fiscal_year.is_not(None))
        .group_by(Document.fiscal_year, Document.funding_type)
    ):
        row = years.setdefault(
            fiscal_year,
            {
                "fiscal_year": fiscal_year,
                "fiscal_year_be": fiscal_year + 543,
                "internal": 0,
                "external": 0,
                "unset": 0,
                "budget_internal": 0.0,
                "budget_external": 0.0,
                "budget_unset": 0.0,
            },
        )
        key = funding.value if funding else "unset"
        row[key] += count
        row[f"budget_{key}"] += float(budget)

    month = func.to_char(func.timezone(LOCAL_TZ, DocumentVersion.created_at), "YYYY-MM")
    month_keys = _month_keys(months)
    uploads = dict(
        db.execute(
            select(month, func.count())
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(live, month >= month_keys[0])
            .group_by(month)
        ).all()
    )

    day = func.date(func.timezone(LOCAL_TZ, AuditEvent.at))
    day_keys = _day_keys(days)
    activity: dict[date, dict[str, int]] = {d: {"download": 0, "view": 0} for d in day_keys}
    for when, action, count in db.execute(
        select(day, AuditEvent.action, func.count())
        .where(
            AuditEvent.action.in_(("document.download", "document.view")),
            day >= day_keys[0],
        )
        .group_by(day, AuditEvent.action)
    ):
        if when in activity:
            activity[when][action.split(".")[1]] = count

    groups: dict[str, dict] = {}
    group_cols = (CategoryGroup.key, CategoryGroup.name_th, Category.id, Category.name_th)
    for key, group_name, category_id, name, count in db.execute(
        select(*group_cols, func.count())
        .join(Category, Category.group_id == CategoryGroup.id)
        .join(DocumentCategory, DocumentCategory.category_id == Category.id)
        .join(Document, Document.id == DocumentCategory.document_id)
        .where(live)
        .group_by(*group_cols, CategoryGroup.sort)
        .order_by(CategoryGroup.sort, func.count().desc(), Category.name_th)
    ):
        groups.setdefault(key, {"key": key, "name": group_name, "items": []})["items"].append(
            {"id": str(category_id), "name": name, "count": count}
        )

    return {
        "by_year": [years[y] for y in sorted(years)],
        "no_fiscal_year": db.scalar(
            select(func.count()).select_from(Document).where(live, Document.fiscal_year.is_(None))
        ),
        "uploads_by_month": [{"month": m, "count": uploads.get(m, 0)} for m in month_keys],
        "activity_by_day": [{"day": d.isoformat(), **activity[d]} for d in day_keys],
        "categories": list(groups.values()),
    }
