from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from dbresearch import audit
from dbresearch.auth import (
    DB,
    AuthProvider,
    Credentials,
    CurrentUser,
    LoginPending,
    LoginRejected,
    ProviderUnavailable,
    client_ip,
    create_session,
    get_provider,
    revoke_all_sessions,
    revoke_session,
)
from dbresearch.config import get_settings
from dbresearch.models import AuditEvent
from dbresearch.schemas import LoginIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


PENDING_DETAIL = "pending_approval"  # the web app shows "waiting for admin approval"
IP_LIMIT_FACTOR = 4  # one IP may fail for several people (shared office NAT)
UNLOCKED = "auth.login_unlocked"  # ADMIN cleared a lock: older failures stop counting


def failed_username():
    """The username of a failed-login row, normalised like `normalize_username`."""
    return func.lower(func.btrim(AuditEvent.details["username"].astext))


def lock_key(username: str) -> str:
    """The username as the brute-force guard counts it (see `failed_username`)."""
    return username[:100].strip().lower()


def lock_start(**target: str):
    """Start of the current lock window for `target` (username=… or ip=…): the window's
    length ago, or the latest ADMIN unlock of that target if it came later."""
    unlock = aliased(AuditEvent)
    latest = (
        select(func.max(unlock.at))
        .where(
            unlock.action == UNLOCKED,
            *(unlock.details[key].astext == value for key, value in target.items()),
        )
        .scalar_subquery()
    )
    window = func.now() - timedelta(minutes=get_settings().login_window_minutes)
    return func.greatest(window, latest)  # GREATEST skips NULL (never unlocked)


def recent_failures(start):
    return (
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "auth.login_failed", AuditEvent.at > start)
    )


def username_failures(username: str):
    """Failures for this username in its lock window, over every IP (add a filter)."""
    key = lock_key(username)
    return recent_failures(lock_start(username=key)).where(failed_username() == key)


def username_locked(db, username: str, ip: str | None) -> bool:
    """Locked per (username, IP): a stranger elsewhere cannot lock a staff member out."""
    query = username_failures(username).where(AuditEvent.ip == ip)  # None: IS NULL
    return db.scalar(query) >= get_settings().login_max_failures


def username_locked_anywhere(db, username: str) -> bool:
    query = (
        username_failures(username)
        .group_by(AuditEvent.ip)
        .having(func.count() >= get_settings().login_max_failures)
    )
    return db.execute(query.limit(1)).first() is not None


def ip_locked(db, ip: str | None) -> bool:
    if not ip:
        return False
    query = recent_failures(lock_start(ip=ip)).where(AuditEvent.ip == ip)
    return db.scalar(query) >= IP_LIMIT_FACTOR * get_settings().login_max_failures


def too_many_failures(db, username: str, ip: str | None) -> str | None:
    """Brute-force guard: recent failures per (username, IP), and per IP. Returns what is
    locked."""
    if username_locked(db, username, ip):
        return "username"
    if ip_locked(db, ip):
        return "ip"
    return None


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DB,
    provider: Annotated[AuthProvider, Depends(get_provider)],
):
    settings = get_settings()
    ip = client_ip(request)
    agent = (request.headers.get("user-agent") or "")[:200]
    username = body.username[:100]
    locked = too_many_failures(db, body.username, ip)
    if locked:
        audit.record(
            db,
            "auth.login_blocked",
            "user",
            ip=ip,
            username=username,
            locked=locked,
            user_agent=agent,
        )
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed logins. Try again later.",
            headers={"Retry-After": str(settings.login_window_minutes * 60)},
        )
    try:
        user = provider.authenticate(db, Credentials(body.username, body.password))
    except LoginRejected as exc:
        db.rollback()
        audit.record(
            db,
            "auth.login_failed",
            "user",
            ip=ip,
            username=username,
            reason=exc.reason,
            user_agent=agent,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password") from None
    except LoginPending:
        db.commit()  # keeps a new request; nothing else was written
        audit.record(db, "auth.login_pending", "user", ip=ip, username=username, user_agent=agent)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, PENDING_DETAIL) from None
    except ProviderUnavailable as exc:
        db.rollback()
        audit.record(
            db, "auth.provider_error", "user", ip=ip, username=username, error=str(exc)[:100]
        )
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Login service unavailable. Try again later."
        ) from None
    # A cookie from an earlier session on this browser ends here (no session reuse).
    old = request.cookies.get(settings.session_cookie)
    if old:
        revoke_session(db, old)
    token = create_session(db, user, ip, agent)
    audit.record(db, "auth.login", "user", user.id, actor_id=user.id, ip=ip, user_agent=agent)
    db.commit()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DB, user: CurrentUser) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie)
    if token:
        revoke_session(db, token)
    audit.record(db, "auth.logout", "user", user.id, actor_id=user.id, ip=client_ip(request))
    db.commit()
    response.delete_cookie(settings.session_cookie, path="/")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(request: Request, response: Response, db: DB, user: CurrentUser) -> None:
    """Log out on every device, this one included."""
    ended = revoke_all_sessions(db, user.id)
    audit.record(
        db,
        "auth.logout_all",
        "user",
        user.id,
        actor_id=user.id,
        ip=client_ip(request),
        sessions=ended,
    )
    db.commit()
    response.delete_cookie(get_settings().session_cookie, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
