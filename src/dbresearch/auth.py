"""Authentication: swappable providers, server-side sessions, FastAPI dependencies.

The college IT team will plug in SSO by adding another `AuthProvider` (e.g. OIDC or a trusted
proxy header) and returning it from `get_provider`. Everything else (sessions, roles in our
DB, audit) stays the same. Local login exists for dev/demo only: no password reset, MFA, or
self-registration (CLAUDE.md).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dbresearch.config import get_settings
from dbresearch.db import get_db
from dbresearch.models import AuthIdentity, User, UserRole, UserStatus
from dbresearch.models import Session as UserSession
from dbresearch.security import hash_password, new_token, token_hash, verify_password

LOCAL = "local"
# Verifying against a dummy hash keeps "unknown user" as slow as "wrong password".
_DUMMY_HASH = hash_password("timing-equaliser")


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


class AuthProvider(Protocol):
    name: str

    def authenticate(self, db: Session, credentials: Credentials) -> User | None:
        """Return the active user for these credentials, or None."""
        ...


class LocalPasswordProvider:
    """Username + argon2id password from `auth_identities` (provider = 'local')."""

    name = LOCAL

    def authenticate(self, db: Session, credentials: Credentials) -> User | None:
        identity = db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == LOCAL,
                AuthIdentity.subject == normalize_username(credentials.username),
            )
        )
        if identity is None or identity.password_hash is None:
            verify_password(_DUMMY_HASH, credentials.password)
            return None
        if not verify_password(identity.password_hash, credentials.password):
            return None
        user = db.get(User, identity.user_id)
        return user if user is not None and user.status == UserStatus.ACTIVE else None


def get_provider() -> AuthProvider:
    return LocalPasswordProvider()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def add_local_identity(db: Session, user: User, username: str, password: str) -> AuthIdentity:
    identity = AuthIdentity(
        user_id=user.id,
        provider=LOCAL,
        subject=normalize_username(username),
        password_hash=hash_password(password),
    )
    db.add(identity)
    return identity


# ───────────── Sessions ─────────────
def create_session(db: Session, user: User, ip: str | None, user_agent: str | None) -> str:
    token, digest = new_token()
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=digest,
            expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
            ip=ip,
            user_agent=(user_agent or "")[:300],
        )
    )
    user.last_login_at = now
    return token


def resolve_session(db: Session, token: str) -> User | None:
    row = db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    return row


def revoke_session(db: Session, token: str) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


# ───────────── Dependencies ─────────────
def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = request.cookies.get(get_settings().session_cookie)
    user = resolve_session(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
