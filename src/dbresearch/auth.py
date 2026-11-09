"""Authentication: swappable providers, server-side sessions, FastAPI dependencies.

Providers are tried in the order of `auth_providers` (e.g. "local,university"). Local login
exists for dev/demo and bootstrap admins only: no password reset, MFA, or self-registration
(CLAUDE.md). The university login API lives in `dbresearch.university`. Roles stay in our DB.
"""

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from dbresearch.config import get_settings
from dbresearch.db import get_db, get_engine
from dbresearch.models import AuthIdentity, User, UserRole, UserStatus
from dbresearch.models import Session as UserSession
from dbresearch.security import hash_password, new_token, token_hash, verify_password

LOCAL = "local"
# Verifying against a dummy hash keeps "unknown user" as slow as "wrong password".
_DUMMY_HASH = hash_password("timing-equaliser")
# Refresh `sessions.last_seen_at` at most this often (not on every request).
_SEEN_EVERY = timedelta(minutes=1)


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


class LoginRejected(Exception):
    """A definite "no". `reason` goes to the audit log only, never to the visitor."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class LoginPending(Exception):
    """The password was right, but ADMIN has not approved this account yet. The login
    endpoint commits first (so a new request is kept) and tells the visitor to wait."""


class ProviderUnavailable(Exception):
    """The login backend (e.g. the university API) could not answer."""


class AuthProvider(Protocol):
    name: str

    def authenticate(self, db: Session, credentials: Credentials) -> User | None:
        """Return the active user. Return None if this provider has no such account (the
        next provider is tried); raise LoginRejected or ProviderUnavailable otherwise."""
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
            return None
        if not verify_password(identity.password_hash, credentials.password):
            raise LoginRejected("wrong_password")
        return active_user(db, identity.user_id)


class ChainProvider:
    """Ask each provider in turn until one knows the account."""

    name = "chain"

    def __init__(self, providers: list[AuthProvider]):
        self.providers = providers

    def authenticate(self, db: Session, credentials: Credentials) -> User:
        for provider in self.providers:
            user = provider.authenticate(db, credentials)
            if user is not None:
                return user
        verify_password(_DUMMY_HASH, credentials.password)
        raise LoginRejected("unknown_user")


def active_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is not None and user.status == UserStatus.PENDING:
        raise LoginPending()
    if user is None or user.status != UserStatus.ACTIVE:
        raise LoginRejected("disabled")
    return user


def get_provider() -> AuthProvider:
    from dbresearch.university import UniversityApiProvider

    known = {LOCAL: LocalPasswordProvider, "university": UniversityApiProvider.from_settings}
    names = [n.strip() for n in get_settings().auth_providers.split(",") if n.strip()]
    unknown = set(names) - known.keys()
    if unknown or not names:
        raise RuntimeError(f"Unknown AUTH_PROVIDERS entries: {sorted(unknown) or names}")
    return ChainProvider([known[name]() for name in names])


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
def active_session_filter(now: datetime):
    """Not revoked, not past its hard limit, and used within the idle timeout."""
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    return and_(
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
        UserSession.last_seen_at > now - idle,
    )


def create_session(db: Session, user: User, ip: str | None, user_agent: str | None) -> str:
    """Start a session; the user's oldest sessions beyond `session_max_per_user` end."""
    settings = get_settings()
    token, digest = new_token()
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=digest,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            last_seen_at=now,
            ip=ip,
            user_agent=(user_agent or "")[:300],
        )
    )
    db.flush()
    extra = (
        select(UserSession.id)
        .where(UserSession.user_id == user.id, active_session_filter(now))
        .order_by(UserSession.last_seen_at.desc(), UserSession.created_at.desc())
        .offset(settings.session_max_per_user)
    )
    db.execute(
        update(UserSession)
        .where(UserSession.id.in_(extra.scalar_subquery()))
        .values(revoked_at=now)
    )
    user.last_login_at = now
    return token


def resolve_session(db: Session, token: str) -> User | None:
    now = datetime.now(UTC)
    row = db.execute(
        select(User, UserSession.id, UserSession.last_seen_at)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash(token),
            active_session_filter(now),
            User.status == UserStatus.ACTIVE,
        )
    ).one_or_none()
    if row is None:
        return None
    user, session_id, last_seen = row
    if now - last_seen > _SEEN_EVERY:
        # Own short transaction, so the request's session stays untouched.
        with get_engine().begin() as conn:
            conn.execute(
                update(UserSession)
                .where(UserSession.id == session_id)
                .values(last_seen_at=func.now())
            )
    return user


def count_active_sessions(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(UserSession.user_id, func.count())
        .where(active_session_filter(datetime.now(UTC)))
        .group_by(UserSession.user_id)
    ).all()
    return dict(rows)


def list_active_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    return list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id, active_session_filter(datetime.now(UTC)))
            .order_by(UserSession.last_seen_at.desc())
        )
    )


def revoke_session(db: Session, token: str) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> int:
    """End every session of this user; returns how many were still open."""
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return result.rowcount


# ───────────── Dependencies ─────────────
def client_ip(request: Request) -> str | None:
    """The visitor's IP, or None if it isn't a valid address (the `inet` columns need one).

    Behind the Cloudflare Tunnel every request comes from the local tunnel process, so the
    real address is read from `trusted_ip_header` when it is configured and present."""
    header = get_settings().trusted_ip_header
    forwarded = request.headers.get(header) if header else None
    host = forwarded.strip() if forwarded else (request.client.host if request.client else None)
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = request.cookies.get(get_settings().session_cookie)
    user = resolve_session(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


def optional_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    """The logged-in user, or None for a guest (share-link pages work either way)."""
    token = request.cookies.get(get_settings().session_cookie)
    return resolve_session(db, token) if token else None


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
MaybeUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
