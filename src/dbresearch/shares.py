"""Temporary share links (DESIGN §4): one document per link, tokens/passwords hashed.

A guest is anyone holding a valid link; there is no guest account (CLAUDE.md).
"""

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dbresearch import audit
from dbresearch.config import get_settings
from dbresearch.models import (
    Document,
    DocumentVersion,
    Setting,
    ShareAccess,
    ShareAccessLog,
    ShareEvent,
    ShareLink,
    User,
    UserRole,
    VersionPurpose,
)
from dbresearch.security import (
    generate_share_password,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)

GRANT_MINUTES = 30
DEFAULTS = {
    "share.default_ttl_hours": 24,
    "share.max_ttl_user_hours": 168,
    "share.max_ttl_admin_hours": 720,
    "share.max_failed_attempts": 10,
}


class LinkState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    EXHAUSTED = "exhausted"  # download limit reached
    LOCKED = "locked"  # too many wrong passwords
    DELETED = "deleted"  # the document went to the trash


class ShareError(ValueError):
    pass


def setting(db: Session, key: str) -> int:
    value = db.scalar(select(Setting.value).where(Setting.key == key))
    return int(value) if value is not None else DEFAULTS[key]


def state(db: Session, link: ShareLink, document: Document | None = None) -> LinkState:
    document = document or db.get(Document, link.document_id)
    if link.revoked_at is not None:
        return LinkState.REVOKED
    if document is None or document.deleted_at is not None:
        return LinkState.DELETED
    if link.expires_at <= datetime.now(UTC):
        return LinkState.EXPIRED
    if link.failed_attempts >= setting(db, "share.max_failed_attempts"):
        return LinkState.LOCKED
    if link.max_downloads is not None and link.download_count >= link.max_downloads:
        return LinkState.EXHAUSTED
    return LinkState.ACTIVE


def create(
    db: Session,
    user: User,
    document: Document,
    *,
    access: ShareAccess,
    ttl_hours: int | None,
    allow_download: bool,
    max_downloads: int | None,
    version_no: int | None,
    note: str | None,
    ip: str | None,
) -> tuple[ShareLink, str, str | None]:
    """Create a link. Returns (link, token, password) — token and password are shown once."""
    default = setting(db, "share.default_ttl_hours")
    cap_key = (
        "share.max_ttl_admin_hours" if user.role == UserRole.ADMIN else "share.max_ttl_user_hours"
    )
    cap = setting(db, cap_key)
    hours = ttl_hours or default
    if hours > cap:
        raise ShareError(f"Links can last at most {cap} hours")
    version_id = None
    if version_no is not None:
        version_id = db.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.purpose == VersionPurpose.MAIN,
                DocumentVersion.version_no == version_no,
            )
        )
        if version_id is None:
            raise ShareError("No such version")
    token, digest = new_token()
    password = generate_share_password() if access == ShareAccess.PASSWORD else None
    now = datetime.now(UTC)
    link = ShareLink(
        document_id=document.id,
        version_id=version_id,
        token_hash=digest,
        access=access,
        password_hash=hash_password(password) if password else None,
        allow_download=allow_download,
        max_downloads=max_downloads,
        expires_at=now + timedelta(hours=hours),
        created_by=user.id,
        created_at=now,
        note=note,
    )
    db.add(link)
    db.flush()
    audit.record(
        db,
        "share.create",
        "share_link",
        link.id,
        actor_id=user.id,
        ip=ip,
        document_id=document.id,
        access=access.value,
        hours=hours,
        allow_download=allow_download,
        max_downloads=max_downloads,
    )
    return link, token, password


def by_token(db: Session, token: str) -> ShareLink | None:
    return db.scalar(select(ShareLink).where(ShareLink.token_hash == token_hash(token)))


def log(
    db: Session,
    link: ShareLink,
    event: ShareEvent,
    ip: str | None,
    user_agent: str | None,
    reason: str | None = None,
    user: User | None = None,
) -> None:
    db.add(
        ShareAccessLog(
            share_link_id=link.id,
            event=event,
            reason=reason,
            ip=ip,
            user_agent=(user_agent or "")[:300],
            user_id=user.id if user else None,
        )
    )


def check_password(db: Session, link: ShareLink, password: str) -> bool:
    if link.password_hash and verify_password(link.password_hash, password):
        return True
    db.execute(
        update(ShareLink)
        .where(ShareLink.id == link.id)
        .values(failed_attempts=ShareLink.failed_attempts + 1)
    )
    return False


def take_download(db: Session, link: ShareLink) -> bool:
    """Count one file open (view or download) atomically; False if the limit was already
    reached (race-safe). `max_downloads` / `download_count` count opens of either kind."""
    result = db.execute(
        update(ShareLink)
        .where(
            ShareLink.id == link.id,
            (ShareLink.max_downloads.is_(None))
            | (ShareLink.download_count < ShareLink.max_downloads),
        )
        .values(download_count=ShareLink.download_count + 1)
        .returning(ShareLink.download_count)
    ).first()
    return result is not None


def regenerate_password(db: Session, user: User, link: ShareLink, ip: str | None) -> str:
    if link.access != ShareAccess.PASSWORD:
        raise ShareError("This link has no password")
    password = generate_share_password()
    link.password_hash = hash_password(password)
    link.failed_attempts = 0
    audit.record(db, "share.new_password", "share_link", link.id, actor_id=user.id, ip=ip)
    return password


def revoke(db: Session, user: User, link: ShareLink, ip: str | None) -> None:
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        link.revoked_by = user.id
        audit.record(db, "share.revoke", "share_link", link.id, actor_id=user.id, ip=ip)


def revoke_for_document(db: Session, document_id: uuid.UUID, user_id: uuid.UUID | None) -> int:
    """Used when a document is deleted: its live links die in the same transaction."""
    result = db.execute(
        update(ShareLink)
        .where(ShareLink.document_id == document_id, ShareLink.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_by=user_id)
    )
    return result.rowcount or 0


# ───────────── Guest grant (after a correct password) ─────────────
def _sign(payload: str) -> str:
    key = get_settings().secret_key.encode()
    mac = hmac.new(key, payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def _password_tag(link: ShareLink) -> str:
    """Ties a grant to the current password: issuing a new one ends every open grant."""
    return hashlib.sha256((link.password_hash or "").encode()).hexdigest()[:16]


def make_grant(link: ShareLink) -> str:
    expires = min(datetime.now(UTC) + timedelta(minutes=GRANT_MINUTES), link.expires_at)
    payload = f"{link.id}.{int(expires.timestamp())}"
    return f"{payload}.{_sign(f'{payload}.{_password_tag(link)}')}"


def grant_valid(link: ShareLink, grant: str | None) -> bool:
    if not grant or grant.count(".") != 2:
        return False
    link_id, expires, signature = grant.split(".")
    payload = f"{link_id}.{expires}.{_password_tag(link)}"
    return (
        hmac.compare_digest(signature, _sign(payload))
        and link_id == str(link.id)
        and expires.isdigit()
        and int(expires) > datetime.now(UTC).timestamp()
    )
