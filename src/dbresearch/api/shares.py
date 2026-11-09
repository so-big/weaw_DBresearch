"""Share links: logged-in management (/documents/{id}/shares, /shares) and guest access (/s)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import select

from dbresearch import audit, shares
from dbresearch.api.documents import live_document, stream_version
from dbresearch.auth import DB, CurrentUser, MaybeUser, client_ip
from dbresearch.config import get_settings
from dbresearch.models import (
    Document,
    DocumentVersion,
    ShareAccess,
    ShareAccessLog,
    ShareEvent,
    ShareLink,
    User,
    UserRole,
)
from dbresearch.schemas import (
    GuestInfo,
    PasswordOut,
    ShareCreate,
    ShareCreated,
    ShareLogOut,
    ShareOut,
    UnlockIn,
)

router = APIRouter(tags=["shares"])
guest = APIRouter(prefix="/s", tags=["guest"])
GRANT_COOKIE = "dbr_grant"


def share_out(db, link: ShareLink, document: Document | None = None) -> ShareOut:
    document = document or db.get(Document, link.document_id)
    return ShareOut(
        id=link.id,
        document_id=link.document_id,
        document_title=document.title,
        access=link.access,
        allow_download=link.allow_download,
        max_downloads=link.max_downloads,
        download_count=link.download_count,
        failed_attempts=link.failed_attempts,
        expires_at=link.expires_at,
        created_at=link.created_at,
        created_by=link.created_by,
        revoked_at=link.revoked_at,
        note=link.note,
        state=shares.state(db, link, document).value,
    )


def managed_link(db, link_id: uuid.UUID, user: User) -> ShareLink:
    link = db.get(ShareLink, link_id)
    if link is None or (link.created_by != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link


@router.post("/documents/{document_id}/shares", status_code=201, response_model=ShareCreated)
def create_share(
    document_id: uuid.UUID, body: ShareCreate, request: Request, db: DB, user: CurrentUser
):
    document = live_document(db, document_id)
    try:
        link, token, password = shares.create(
            db,
            user,
            document,
            access=body.access,
            ttl_hours=body.ttl_hours,
            allow_download=body.allow_download,
            max_downloads=body.max_downloads,
            version_no=body.version_no,
            note=body.note,
            ip=client_ip(request),
        )
    except shares.ShareError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    return ShareCreated(
        **share_out(db, link, document).model_dump(),
        token=token,
        path=f"/s/{token}",  # the web page; its API lives under /api/s/
        password=password,
    )


@router.get("/shares", response_model=list[ShareOut])
def my_shares(db: DB, user: CurrentUser, active_only: bool = False):
    links = db.scalars(
        select(ShareLink)
        .where(ShareLink.created_by == user.id)
        .order_by(ShareLink.created_at.desc())
    ).all()
    out = [share_out(db, link) for link in links]
    return [s for s in out if s.state == "active"] if active_only else out


@router.get("/shares/{link_id}/log", response_model=list[ShareLogOut])
def share_log(link_id: uuid.UUID, db: DB, user: CurrentUser):
    link = managed_link(db, link_id, user)
    rows = db.execute(
        select(ShareAccessLog, User.display_name)
        .outerjoin(User, User.id == ShareAccessLog.user_id)
        .where(ShareAccessLog.share_link_id == link.id)
        .order_by(ShareAccessLog.at.desc())
    ).all()
    return [
        ShareLogOut.model_validate(entry).model_copy(update={"user_name": name})
        for entry, name in rows
    ]


@router.delete("/shares/{link_id}", status_code=204)
def revoke_share(link_id: uuid.UUID, request: Request, db: DB, user: CurrentUser) -> None:
    shares.revoke(db, user, managed_link(db, link_id, user), client_ip(request))
    db.commit()


@router.post("/shares/{link_id}/password", response_model=PasswordOut)
def new_password(link_id: uuid.UUID, request: Request, db: DB, user: CurrentUser):
    """Issue a new password (the old one stops working; wrong-attempt counter resets)."""
    link = managed_link(db, link_id, user)
    try:
        password = shares.regenerate_password(db, user, link, client_ip(request))
    except shares.ShareError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    return PasswordOut(password=password)


# ───────────── Guest side (no login) ─────────────
def _guest_link(
    db, token: str, request: Request, viewer: User | None
) -> tuple[ShareLink, Document]:
    """The link if usable; otherwise 404 (the reason is logged, not shown).

    `viewer` is whoever is logged in on this browser, so the link's owner can tell a
    colleague's visit from an outsider's. Guests stay anonymous (IP only)."""
    link = shares.by_token(db, token)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has expired")
    document = db.get(Document, link.document_id)
    current = shares.state(db, link, document)
    if current != shares.LinkState.ACTIVE:
        shares.log(
            db,
            link,
            ShareEvent.DENIED,
            client_ip(request),
            request.headers.get("user-agent"),
            reason=current.value,
            user=viewer,
        )
        db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has expired")
    return link, document


def _version(db, link: ShareLink, document: Document) -> DocumentVersion:
    return db.get(DocumentVersion, link.version_id or document.current_version_id)


def _unlocked(link: ShareLink, grant: str | None) -> bool:
    return link.access == ShareAccess.PUBLIC or shares.grant_valid(link, grant)


@guest.get("/{token}", response_model=GuestInfo)
def guest_info(
    token: str,
    request: Request,
    db: DB,
    viewer: MaybeUser,
    dbr_grant: Annotated[str | None, Cookie()] = None,
):
    link, document = _guest_link(db, token, request, viewer)
    version = _version(db, link, document)
    agent = request.headers.get("user-agent")
    shares.log(db, link, ShareEvent.OPEN, client_ip(request), agent, user=viewer)
    db.commit()
    left = None if link.max_downloads is None else link.max_downloads - link.download_count
    return GuestInfo(
        title=document.title,
        filename=version.original_filename,
        pages=version.page_count,
        size_bytes=version.size_bytes,
        expires_at=link.expires_at,
        requires_password=link.access == ShareAccess.PASSWORD,
        unlocked=_unlocked(link, dbr_grant),
        allow_download=link.allow_download,
        downloads_left=left,
    )


@guest.post("/{token}/unlock", status_code=204)
def guest_unlock(
    token: str, body: UnlockIn, request: Request, response: Response, db: DB, viewer: MaybeUser
):
    link, _ = _guest_link(db, token, request, viewer)
    ip, agent = client_ip(request), request.headers.get("user-agent")
    if link.access != ShareAccess.PASSWORD:
        return
    if not shares.check_password(db, link, body.password):
        shares.log(db, link, ShareEvent.BAD_PASSWORD, ip, agent, user=viewer)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wrong password")
    response.set_cookie(
        GRANT_COOKIE,
        shares.make_grant(link),
        max_age=shares.GRANT_MINUTES * 60,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        path=f"/api/s/{token}",
    )


@guest.get("/{token}/file")
def guest_file(
    token: str,
    request: Request,
    db: DB,
    viewer: MaybeUser,
    download: bool = False,
    dbr_grant: Annotated[str | None, Cookie()] = None,
):
    link, document = _guest_link(db, token, request, viewer)
    ip, agent = client_ip(request), request.headers.get("user-agent")
    if not _unlocked(link, dbr_grant):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password required")
    if download and not link.allow_download:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This link is view-only")
    if download and not shares.take_download(db, link):
        shares.log(db, link, ShareEvent.DENIED, ip, agent, reason="exhausted", user=viewer)
        db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has expired")
    version = _version(db, link, document)
    event = ShareEvent.DOWNLOAD if download else ShareEvent.VIEW
    shares.log(db, link, event, ip, agent, user=viewer)
    audit.record(
        db,
        "document.download" if download else "document.view",
        "document",
        document.id,
        actor_id=viewer.id if viewer else None,
        ip=ip,
        via="share",
        share_link_id=link.id,
        version=version.version_no,
    )
    db.commit()
    return stream_version(version, inline=not download)
