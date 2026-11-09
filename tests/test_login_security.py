"""Login hardening: idle timeout, session caps, log-out-everywhere, login audit detail,
the append-only audit log, security headers, and the university login provider."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from dbresearch.auth import (
    ChainProvider,
    LocalPasswordProvider,
    ProviderUnavailable,
    get_provider,
)
from dbresearch.db import new_session
from dbresearch.models import AuditEvent, AuthIdentity, User, UserRole, UserStatus
from dbresearch.models import Session as UserSession
from dbresearch.university import UniversityAccount, UniversityApiProvider
from tests.conftest import API, CSRF, needs_db

pytestmark = needs_db


def new_client() -> TestClient:
    from dbresearch.main import app

    return TestClient(app, headers=CSRF, base_url=API)


def sign_in(client, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def audit_rows(action: str) -> list[AuditEvent]:
    with new_session() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.action == action)))


def age_sessions(user_id, minutes: int) -> None:
    with new_session() as db:
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=minutes))
        )
        db.commit()


# ───────────── Sessions ─────────────
def test_idle_session_ends(client, make_user):
    user_id, username, password = make_user()
    assert sign_in(client, username, password).status_code == 200
    age_sessions(user_id, 61)
    assert client.get("/auth/me").status_code == 401


def test_activity_keeps_the_session_alive(client, make_user):
    user_id, username, password = make_user()
    sign_in(client, username, password)
    age_sessions(user_id, 30)
    assert client.get("/auth/me").status_code == 200
    with new_session() as db:
        seen = db.scalar(select(UserSession.last_seen_at).where(UserSession.user_id == user_id))
    assert datetime.now(UTC) - seen < timedelta(minutes=1)


def test_sixth_device_logs_out_the_oldest(client, make_user):
    _, username, password = make_user()
    devices = [new_client() for _ in range(6)]
    for device in devices:
        assert sign_in(device, username, password).status_code == 200
    assert devices[0].get("/auth/me").status_code == 401
    assert all(d.get("/auth/me").status_code == 200 for d in devices[1:])


def test_logging_in_again_ends_the_old_session(client, make_user):
    user_id, username, password = make_user()
    sign_in(client, username, password)
    sign_in(client, username, password)
    with new_session() as db:
        open_ = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        ).all()
    assert len(open_) == 1


def test_logout_all_ends_every_device(client, make_user):
    _, username, password = make_user()
    other = new_client()
    sign_in(client, username, password)
    sign_in(other, username, password)
    assert client.post("/auth/logout-all").status_code == 204
    assert other.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert audit_rows("auth.logout_all")[0].details["sessions"] == 2


def test_admin_sees_and_ends_a_users_sessions(client, login, make_user):
    user_id, username, password = make_user()
    device = new_client()
    sign_in(device, username, password)
    login(UserRole.ADMIN)

    row = next(u for u in client.get("/admin/users").json() if u["id"] == str(user_id))
    assert row["active_sessions"] == 1 and row["logins"] == ["local"]
    sessions = client.get(f"/admin/users/{user_id}/sessions").json()
    assert len(sessions) == 1 and "testclient" in sessions[0]["user_agent"]

    assert client.post(f"/admin/users/{user_id}/sessions/revoke").status_code == 204
    assert device.get("/auth/me").status_code == 401
    assert audit_rows("user.sessions_revoked")[0].details["sessions"] == 1


# ───────────── Login audit ─────────────
def test_failed_and_blocked_logins_record_why(client, make_user):
    _, username, _ = make_user()
    sign_in(client, username, "wrong")
    sign_in(client, "nobody", "wrong")
    reasons = {r.details["username"]: r.details["reason"] for r in audit_rows("auth.login_failed")}
    assert reasons == {username: "wrong_password", "nobody": "unknown_user"}
    assert all("password" not in r.details for r in audit_rows("auth.login_failed"))

    for _ in range(4):
        sign_in(client, username, "wrong")
    assert sign_in(client, username, "wrong").status_code == 429
    (blocked,) = audit_rows("auth.login_blocked")
    assert blocked.details["locked"] == "username"


def test_security_summary(client, login, make_user):
    _, username, _ = make_user()
    for _ in range(5):
        sign_in(client, username, "wrong")
    login(UserRole.ADMIN)
    summary = client.get("/admin/security").json()
    assert summary["failed"] == 5 and summary["logins"] == 1
    assert summary["by_username"] == [{"key": username, "failures": 5, "locked": True}]
    assert any("COOKIE_SECURE" in w for w in summary["warnings"])


def test_audit_log_is_append_only(client, make_user):
    _, username, _ = make_user()
    sign_in(client, username, "wrong")
    for sql in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"):
        with new_session() as db, pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
    with new_session() as db, pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("TRUNCATE audit_events"))
    assert len(audit_rows("auth.login_failed")) == 1


# ───────────── Headers ─────────────
def test_api_responses_are_not_cached_and_hsts_follows_cookie_secure(client, monkeypatch):
    from dbresearch.config import get_settings

    response = client.get("/auth/me")
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers

    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        hsts = client.get("/auth/me").headers["strict-transport-security"]
    finally:
        monkeypatch.delenv("COOKIE_SECURE")
        get_settings.cache_clear()
    assert hsts == "max-age=31536000"


# ───────────── University login ─────────────
class FakeUniversity:
    """Stand-in for the university API: id -> (password, type)."""

    def __init__(self):
        self.accounts = {
            "t1001": ("teach-pass", "teacher"),
            "s6501": ("study-pass", "student"),
        }
        self.calls = 0

    def verify(self, username: str, password: str) -> UniversityAccount | None:
        self.calls += 1
        if username == "down":
            raise ProviderUnavailable("timeout")
        pw, kind = self.accounts.get(username, (None, None))
        if pw is None or pw != password:
            return None
        return UniversityAccount(
            subject=username.upper(),
            account_type=kind,
            display_name=f"อ.{username}",
            email=f"{username}@uni.example",
        )


@pytest.fixture
def university(client) -> Iterator[dict]:
    from dbresearch.main import app

    fake = FakeUniversity()
    options = {"auto_create": True, "fake": fake}

    def provider():
        uni = UniversityApiProvider(fake, {"teacher"}, options["auto_create"])
        return ChainProvider([LocalPasswordProvider(), uni])

    app.dependency_overrides[get_provider] = provider
    yield options
    app.dependency_overrides.pop(get_provider, None)


def test_teacher_logs_in_and_gets_a_user_account(client, university):
    response = sign_in(client, "t1001", "teach-pass")
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "user"
    assert sign_in(new_client(), "T1001 ", "teach-pass").status_code == 200  # same account
    with new_session() as db:
        identities = db.scalars(select(AuthIdentity).where(AuthIdentity.provider == "university"))
        assert [i.subject for i in identities] == ["T1001"]
        assert db.scalar(select(AuthIdentity.password_hash)) is None
    (created,) = audit_rows("user.create")
    assert created.details["via"] == "university"


def test_students_and_wrong_passwords_are_refused(client, university):
    assert sign_in(client, "s6501", "study-pass").status_code == 401
    assert sign_in(client, "t1001", "nope").status_code == 401
    reasons = sorted(r.details["reason"] for r in audit_rows("auth.login_failed"))
    assert reasons == ["type_not_allowed:student", "wrong_password"]
    with new_session() as db:
        assert db.scalar(select(User).where(User.email == "s6501@uni.example")) is None


def test_local_accounts_never_reach_the_university_api(client, university, make_user):
    _, username, password = make_user()
    assert sign_in(client, username, "wrong").status_code == 401
    assert sign_in(client, username, password).status_code == 200
    assert university["fake"].calls == 0


def test_api_down_is_a_503_and_does_not_lock_accounts(client, university):
    for _ in range(6):
        assert sign_in(client, "down", "x").status_code == 503
    assert len(audit_rows("auth.provider_error")) == 6
    assert audit_rows("auth.login_failed") == []


def test_without_auto_create_admin_must_add_the_teacher(client, university, login):
    university["auto_create"] = False
    assert sign_in(client, "t1001", "teach-pass").status_code == 401
    assert audit_rows("auth.login_failed")[0].details["reason"] == "not_registered"

    login(UserRole.ADMIN)
    response = client.post(
        "/admin/users",
        json={"email": "x@dept.example", "display_name": "อ.ทดสอบ", "university_id": "T1001"},
    )
    assert response.status_code == 201
    assert sign_in(new_client(), "t1001", "teach-pass").status_code == 200


def test_first_login_links_to_a_user_admin_added_by_email(client, university, login):
    login(UserRole.ADMIN)
    client.post("/admin/users", json={"email": "t1001@uni.example", "display_name": "Pre"})
    me = sign_in(new_client(), "t1001", "teach-pass").json()
    assert me["display_name"] == "Pre"


def test_disabled_teacher_cannot_log_in(client, university):
    user_id = sign_in(client, "t1001", "teach-pass").json()["id"]
    with new_session() as db:
        db.execute(update(User).where(User.id == user_id).values(status=UserStatus.DISABLED))
        db.commit()
    assert sign_in(new_client(), "t1001", "teach-pass").status_code == 401
    assert audit_rows("auth.login_failed")[0].details["reason"] == "disabled"
