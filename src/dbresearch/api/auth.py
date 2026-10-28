from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from dbresearch import audit
from dbresearch.auth import (
    DB,
    AuthProvider,
    Credentials,
    CurrentUser,
    client_ip,
    create_session,
    get_provider,
    revoke_session,
)
from dbresearch.config import get_settings
from dbresearch.models import AuditEvent
from dbresearch.schemas import LoginIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def too_many_failures(db, username: str, ip: str | None) -> bool:
    """Brute-force guard for the public demo: recent failures per username, and per IP."""
    settings = get_settings()
    failed = (
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "auth.login_failed",
            AuditEvent.at >= func.now() - timedelta(minutes=settings.login_window_minutes),
        )
    )
    limit = settings.login_max_failures
    name = func.lower(func.btrim(AuditEvent.details["username"].astext))
    if db.scalar(failed.where(name == username[:100].strip().lower())) >= limit:
        return True
    return bool(ip) and db.scalar(failed.where(AuditEvent.ip == ip)) >= 4 * limit


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DB,
    provider: Annotated[AuthProvider, Depends(get_provider)],
):
    ip = client_ip(request)
    if too_many_failures(db, body.username, ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed logins. Try again later.",
            headers={"Retry-After": str(get_settings().login_window_minutes * 60)},
        )
    user = provider.authenticate(db, Credentials(body.username, body.password))
    if user is None:
        audit.record(db, "auth.login_failed", "user", ip=ip, username=body.username[:100])
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    token = create_session(db, user, ip, request.headers.get("user-agent"))
    audit.record(db, "auth.login", "user", user.id, actor_id=user.id, ip=ip)
    db.commit()
    settings = get_settings()
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


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
