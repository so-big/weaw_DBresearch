"""ADMIN endpoints: users, all share links, trash, audit, settings, categories, templates,
reports. Every change writes an audit row."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from dbresearch import audit, documents, shares
from dbresearch.api.shares import share_out
from dbresearch.auth import DB, AdminUser, add_local_identity, client_ip, revoke_all_sessions
from dbresearch.autofill.rules import validate_rules
from dbresearch.models import (
    AuditEvent,
    AuthIdentity,
    Category,
    CategoryGroup,
    DocStatus,
    Document,
    DocumentCategory,
    DocumentVersion,
    ExtractionTemplate,
    OcrStatus,
    Setting,
    ShareLink,
    User,
    UserRole,
    UserStatus,
)
from dbresearch.schemas import DocumentSummary, ShareOut, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ───────────── Users ─────────────
class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    role: UserRole = UserRole.USER
    username: str | None = Field(None, max_length=100)  # local login (dev/demo only)
    password: str | None = Field(None, min_length=10, max_length=200)


class UserPatch(BaseModel):
    display_name: str | None = Field(None, max_length=200)
    role: UserRole | None = None
    status: UserStatus | None = None


class PasswordIn(BaseModel):
    password: str = Field(min_length=10, max_length=200)


@router.get("/users", response_model=list[UserOut])
def list_users(db: DB, admin: AdminUser):
    return db.scalars(select(User).order_by(User.display_name)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: DB, admin: AdminUser):
    if (body.username is None) != (body.password is None):
        raise HTTPException(422, "Give both username and password, or neither (SSO users)")
    user = User(email=body.email.strip(), display_name=body.display_name.strip(), role=body.role)
    db.add(user)
    try:
        db.flush()
        if body.username:
            add_local_identity(db, user, body.username, body.password)
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email or username already in use") from exc
    audit.record(
        db,
        "user.create",
        "user",
        user.id,
        actor_id=admin.id,
        ip=client_ip(request),
        role=body.role.value,
        local_login=bool(body.username),
    )
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserPatch, request: Request, db: DB, admin: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id and (
        (body.role and body.role != UserRole.ADMIN) or body.status == UserStatus.DISABLED
    ):
        raise HTTPException(422, "You can't remove your own admin access")
    changes = body.model_dump(exclude_none=True)
    for name, value in changes.items():
        setattr(user, name, value)
    user.updated_at = func.now()
    if body.status == UserStatus.DISABLED:
        revoke_all_sessions(db, user.id)
    audit.record(
        db,
        "user.update",
        "user",
        user.id,
        actor_id=admin.id,
        ip=client_ip(request),
        **{k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()},
    )
    db.commit()
    return user


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(
    user_id: uuid.UUID, body: PasswordIn, request: Request, db: DB, admin: AdminUser
) -> None:
    from dbresearch.security import hash_password

    identity = db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user_id, AuthIdentity.provider == "local"
        )
    )
    if identity is None:
        raise HTTPException(404, "User has no local login")
    identity.password_hash = hash_password(body.password)
    revoke_all_sessions(db, user_id)
    audit.record(
        db, "user.password_reset", "user", user_id, actor_id=admin.id, ip=client_ip(request)
    )
    db.commit()


# ───────────── Share links (all users) ─────────────
@router.get("/shares", response_model=list[ShareOut])
def all_shares(db: DB, admin: AdminUser, state: str | None = "active"):
    links = db.scalars(select(ShareLink).order_by(ShareLink.created_at.desc())).all()
    out = [share_out(db, link) for link in links]
    return [s for s in out if state is None or s.state == state]


# ───────────── Trash ─────────────
@router.get("/trash", response_model=list[DocumentSummary])
def trash(db: DB, admin: AdminUser):
    return db.scalars(
        select(Document)
        .where(Document.deleted_at.is_not(None))
        .order_by(Document.deleted_at.desc())
    ).all()


def _trashed(db, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is None:
        raise HTTPException(404, "Not in the trash")
    return document


@router.post("/trash/{document_id}/restore", status_code=204)
def restore(document_id: uuid.UUID, request: Request, db: DB, admin: AdminUser) -> None:
    try:
        documents.restore(db, admin, _trashed(db, document_id), client_ip(request))
    except documents.TrashError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()


@router.delete("/trash/{document_id}", status_code=204)
def purge(document_id: uuid.UUID, request: Request, db: DB, admin: AdminUser) -> None:
    """Permanent removal from the live system (encrypted files + keys). Backups keep it."""
    keys = documents.purge(db, admin, _trashed(db, document_id), client_ip(request))
    db.commit()
    documents.delete_blobs(keys)


# ───────────── Audit ─────────────
class AuditOut(BaseModel):
    id: int
    at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    details: dict[str, Any]
    ip: str | None


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    db: DB,
    admin: AdminUser,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_id: int | None = None,
):
    query = select(AuditEvent, User.display_name).outerjoin(User, User.id == AuditEvent.actor_id)
    if action:
        query = query.where(AuditEvent.action.like(f"{action}%"))
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    if actor_id:
        query = query.where(AuditEvent.actor_id == actor_id)
    if since:
        query = query.where(AuditEvent.at >= since)
    if before_id:
        query = query.where(AuditEvent.id < before_id)
    rows = db.execute(query.order_by(AuditEvent.id.desc()).limit(limit)).all()
    return [
        AuditOut(
            id=e.id,
            at=e.at,
            actor_id=e.actor_id,
            actor_name=name,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            details=e.details,
            ip=e.ip,
        )
        for e, name in rows
    ]


# ───────────── Settings ─────────────
SETTING_BOUNDS = {
    "share.default_ttl_hours": (1, 24 * 30),
    "share.max_ttl_user_hours": (1, 24 * 90),
    "share.max_ttl_admin_hours": (1, 24 * 365),
    "share.max_failed_attempts": (3, 100),
}


class SettingIn(BaseModel):
    value: int


@router.get("/settings")
def get_settings_(db: DB, admin: AdminUser) -> dict[str, int]:
    return {key: shares.setting(db, key) for key in SETTING_BOUNDS}


@router.put("/settings/{key}")
def put_setting(
    key: str, body: SettingIn, request: Request, db: DB, admin: AdminUser
) -> dict[str, int]:
    if key not in SETTING_BOUNDS:
        raise HTTPException(404, "Unknown setting")
    low, high = SETTING_BOUNDS[key]
    if not low <= body.value <= high:
        raise HTTPException(422, f"Must be between {low} and {high}")
    row = db.get(Setting, key) or Setting(key=key, value=body.value)
    row.value = body.value
    db.add(row)
    audit.record(
        db,
        "settings.update",
        "setting",
        actor_id=admin.id,
        ip=client_ip(request),
        key=key,
        value=body.value,
    )
    db.commit()
    return {key: body.value}


# ───────────── Categories ─────────────
class GroupIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    name_th: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(None, max_length=200)
    aliases: list[str] = []
    multi: bool = False
    sort: int = 0


class GroupPatch(BaseModel):
    name_th: str | None = Field(None, max_length=200)
    name_en: str | None = Field(None, max_length=200)
    aliases: list[str] | None = None
    multi: bool | None = None
    sort: int | None = None


class CategoryIn(BaseModel):
    group_id: uuid.UUID
    name_th: str = Field(min_length=1, max_length=300)
    name_en: str | None = Field(None, max_length=300)
    aliases: list[str] = []
    sort: int = 0


class CategoryPatch(BaseModel):
    name_th: str | None = Field(None, max_length=300)
    name_en: str | None = Field(None, max_length=300)
    aliases: list[str] | None = None
    active: bool | None = None
    sort: int | None = None


def _save(db, request, admin, action: str, entity, entity_type: str, **details) -> dict:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Name or key already exists") from exc
    audit.record(
        db, action, entity_type, entity.id, actor_id=admin.id, ip=client_ip(request), **details
    )
    db.commit()
    return {"id": str(entity.id)}


@router.post("/category-groups", status_code=201)
def create_group(body: GroupIn, request: Request, db: DB, admin: AdminUser) -> dict:
    group = CategoryGroup(**body.model_dump())
    db.add(group)
    return _save(db, request, admin, "category_group.create", group, "category_group", key=body.key)


@router.patch("/category-groups/{group_id}")
def update_group(
    group_id: uuid.UUID, body: GroupPatch, request: Request, db: DB, admin: AdminUser
) -> dict:
    group = db.get(CategoryGroup, group_id) or _missing()
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(group, name, value)
    return _save(
        db,
        request,
        admin,
        "category_group.update",
        group,
        "category_group",
        fields=sorted(body.model_dump(exclude_none=True)),
    )


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, request: Request, db: DB, admin: AdminUser) -> dict:
    db.get(CategoryGroup, body.group_id) or _missing()
    category = Category(**body.model_dump())
    db.add(category)
    return _save(db, request, admin, "category.create", category, "category")


@router.patch("/categories/{category_id}")
def update_category(
    category_id: uuid.UUID, body: CategoryPatch, request: Request, db: DB, admin: AdminUser
) -> dict:
    category = db.get(Category, category_id) or _missing()
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(category, name, value)
    return _save(
        db,
        request,
        admin,
        "category.update",
        category,
        "category",
        fields=sorted(body.model_dump(exclude_none=True)),
    )


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: uuid.UUID, request: Request, db: DB, admin: AdminUser) -> None:
    category = db.get(Category, category_id) or _missing()
    used = db.scalar(
        select(func.count())
        .select_from(DocumentCategory)
        .where(DocumentCategory.category_id == category.id)
    )
    if used:
        raise HTTPException(409, f"Used by {used} document(s): deactivate it instead")
    audit.record(
        db,
        "category.delete",
        "category",
        category.id,
        actor_id=admin.id,
        ip=client_ip(request),
        name=category.name_th,
    )
    db.delete(category)
    db.commit()


def _missing():
    raise HTTPException(404, "Not found")


# ───────────── Extraction templates ─────────────
class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    attachment_no: int | None
    kind: str | None
    funding_type: str | None
    match_rules: dict[str, Any]
    field_rules: dict[str, Any]
    checkbox_groups: bool
    priority: int
    active: bool
    updated_at: datetime


class TemplatePatch(BaseModel):
    match_rules: dict[str, Any] | None = None
    field_rules: dict[str, Any] | None = None
    checkbox_groups: bool | None = None
    priority: int | None = None
    active: bool | None = None


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: DB, admin: AdminUser):
    rows = db.scalars(select(ExtractionTemplate).order_by(ExtractionTemplate.priority.desc()))
    return [
        TemplateOut(
            **{
                c: getattr(t, c)
                for c in TemplateOut.model_fields
                if c not in ("kind", "funding_type")
            },
            kind=t.kind.value if t.kind else None,
            funding_type=t.funding_type.value if t.funding_type else None,
        )
        for t in rows
    ]


@router.patch("/templates/{template_id}")
def update_template(
    template_id: uuid.UUID, body: TemplatePatch, request: Request, db: DB, admin: AdminUser
) -> dict:
    template = db.get(ExtractionTemplate, template_id) or _missing()
    if body.field_rules is not None:
        try:
            validate_rules(body.field_rules.get("rules", []))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if body.match_rules is not None and not body.match_rules.get("keywords"):
        raise HTTPException(422, "match_rules needs a non-empty 'keywords' list")
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(template, name, value)
    template.updated_at = func.now()
    return _save(
        db,
        request,
        admin,
        "template.update",
        template,
        "template",
        fields=sorted(body.model_dump(exclude_none=True)),
    )


# ───────────── Reports ─────────────
@router.get("/reports/missing-numbers")
def missing_numbers(
    db: DB, admin: AdminUser, year_be: int | None = None, series: str | None = None
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


@router.get("/reports/overview")
def overview(db: DB, admin: AdminUser) -> dict:
    live = Document.deleted_at.is_(None)
    by_status = dict(
        db.execute(
            select(Document.status, func.count()).where(live).group_by(Document.status)
        ).all()
    )
    active_links = sum(
        1
        for link in db.scalars(select(ShareLink).where(ShareLink.revoked_at.is_(None)))
        if shares.state(db, link) == shares.LinkState.ACTIVE
    )
    return {
        "documents": {s.value: by_status.get(s, 0) for s in DocStatus},
        "in_trash": db.scalar(
            select(func.count()).select_from(Document).where(Document.deleted_at.is_not(None))
        ),
        "ocr_failed": db.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.ocr_status == OcrStatus.FAILED)
        ),
        "stored_bytes": db.scalar(select(func.coalesce(func.sum(DocumentVersion.size_bytes), 0))),
        "active_share_links": active_links,
        "users": db.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.ACTIVE)
        ),
    }
