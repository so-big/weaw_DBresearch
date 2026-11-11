"""Login hardening: idle timeout, session caps, log-out-everywhere, login audit detail,
the append-only audit log, security headers, and the university login provider."""

import uuid
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
    for _ in range(3):  # one row per lock, not one per request
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


@pytest.fixture
def from_ip(monkeypatch) -> Iterator:
    """Requests carry a Cloudflare client IP: `client.post(..., headers=from_ip("…"))`."""
    from dbresearch.config import get_settings

    monkeypatch.setenv("TRUSTED_IP_HEADER", "CF-Connecting-IP")
    get_settings.cache_clear()
    yield lambda ip: {"CF-Connecting-IP": ip}
    monkeypatch.delenv("TRUSTED_IP_HEADER")
    get_settings.cache_clear()


def sign_in_from(client, ip: dict, username: str, password: str):
    body = {"username": username, "password": password}
    return client.post("/auth/login", json=body, headers=ip)


def test_a_stranger_elsewhere_cannot_lock_a_user_out(client, make_user, from_ip):
    _, username, password = make_user()
    stranger, office = from_ip("198.51.100.7"), from_ip("203.0.113.5")
    for _ in range(5):
        assert sign_in_from(client, stranger, username, "wrong").status_code == 401
    assert sign_in_from(client, stranger, username, password).status_code == 429
    assert sign_in_from(new_client(), office, username, password).status_code == 200
    (blocked,) = audit_rows("auth.login_blocked")
    assert (blocked.details["locked"], str(blocked.ip)) == ("username", "198.51.100.7")


def test_admin_unlocks_a_username(client, login, make_user):
    _, username, password = make_user()
    for _ in range(5):
        sign_in(client, username, "wrong")
    assert sign_in(new_client(), username, password).status_code == 429

    admin_id = login(UserRole.ADMIN)
    (row,) = client.get("/admin/security").json()["by_username"]
    assert row["locked"] is True
    unlock = {"kind": "username", "key": f" {username.upper()} "}
    assert client.post("/admin/security/unlock", json=unlock).status_code == 204
    (row,) = client.get("/admin/security").json()["by_username"]
    assert row == {"key": username, "failures": 5, "locked": False}  # history stays
    (unlocked,) = audit_rows("auth.login_unlocked")
    assert unlocked.details == {"username": username} and unlocked.actor_id == admin_id

    assert sign_in(new_client(), username, password).status_code == 200
    for _ in range(5):  # failures after the unlock count again
        sign_in(new_client(), username, "wrong")
    assert sign_in(new_client(), username, password).status_code == 429
    assert sign_in(new_client(), username, password).status_code == 429
    assert len(audit_rows("auth.login_blocked")) == 2  # one per lock
    assert client.get("/admin/security").json()["blocked"] == 2


def test_admin_unlocks_an_ip(client, login, make_user, from_ip):
    _, username, password = make_user()
    shared = from_ip("192.0.2.44")
    for i in range(20):  # 4 tries at each of 5 names: no name is locked, the IP is
        sign_in_from(client, shared, f"guess{i % 5}", "wrong")
    assert sign_in_from(new_client(), shared, username, password).status_code == 429
    assert audit_rows("auth.login_blocked")[0].details["locked"] == "ip"

    login(UserRole.ADMIN)
    summary = client.get("/admin/security").json()
    assert summary["by_ip"] == [{"key": "192.0.2.44", "failures": 20, "locked": True}]
    assert not any(r["locked"] for r in summary["by_username"])
    bad = client.post("/admin/security/unlock", json={"kind": "ip", "key": "not-an-ip"})
    assert bad.status_code == 422
    unlock = {"kind": "ip", "key": "192.0.2.44"}
    assert client.post("/admin/security/unlock", json=unlock).status_code == 204
    assert client.get("/admin/security").json()["by_ip"][0]["locked"] is False
    assert audit_rows("auth.login_unlocked")[0].details == {"ip": "192.0.2.44"}
    assert sign_in_from(new_client(), shared, username, password).status_code == 200


def test_only_admins_unlock(client, login):
    login()
    unlock = {"kind": "username", "key": "someone"}
    assert client.post("/admin/security/unlock", json=unlock).status_code == 403
    assert audit_rows("auth.login_unlocked") == []


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
            "t1001": ("teach-pass", "staff"),
            "t1002": ("teach-pass", "staff"),
            "p2001": ("prof-pass", "teacher"),
            "s6501": ("study-pass", "student"),
        }
        self.calls = 0
        self.department: str | None = None

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
            department=self.department,
        )


@pytest.fixture
def university(client) -> Iterator[dict]:
    from dbresearch.main import app

    fake = FakeUniversity()
    options = {"departments": set(), "fake": fake}

    def provider():
        uni = UniversityApiProvider(fake, {"staff"}, options["departments"])
        return ChainProvider([LocalPasswordProvider(), uni])

    app.dependency_overrides[get_provider] = provider
    yield options
    app.dependency_overrides.pop(get_provider, None)


def request_id(username: str) -> str:
    with new_session() as db:
        return str(
            db.scalar(
                select(AuthIdentity.user_id).where(
                    AuthIdentity.provider == "university", AuthIdentity.subject == username.upper()
                )
            )
        )


def test_first_login_waits_for_admin_approval(client, university, login):
    response = sign_in(client, "t1001", "teach-pass")
    assert response.status_code == 403
    assert response.json()["detail"] == "pending_approval"
    assert client.get("/auth/me").status_code == 401  # no session
    assert sign_in(new_client(), "T1001 ", "teach-pass").status_code == 403  # same request
    with new_session() as db:
        identities = db.scalars(select(AuthIdentity).where(AuthIdentity.provider == "university"))
        assert [i.subject for i in identities] == ["T1001"]
        assert db.scalar(select(AuthIdentity.password_hash)) is None
    (asked,) = audit_rows("user.request")
    assert asked.details["via"] == "university"
    assert len(audit_rows("auth.login_pending")) == 2
    assert audit_rows("auth.login_failed") == []

    login(UserRole.ADMIN)
    (req,) = client.get("/admin/users/requests").json()
    assert (req["university_id"], req["account_type"]) == ("T1001", "staff")
    assert req["id"] not in [u["id"] for u in client.get("/admin/users").json()]
    assert client.patch(f"/admin/users/{req['id']}", json={"status": "active"}).status_code == 409
    assert client.post(f"/admin/users/{req['id']}/approve").status_code == 204
    assert client.post(f"/admin/users/{req['id']}/approve").status_code == 409  # decided
    assert client.get("/admin/users/requests").json() == []
    assert audit_rows("user.approve")[0].entity_id == uuid.UUID(req["id"])

    me = sign_in(new_client(), "t1001", "teach-pass")
    assert me.status_code == 200 and me.json()["role"] == "user"


def test_rejected_request_stays_out(client, university, login):
    assert sign_in(client, "t1001", "teach-pass").status_code == 403
    login(UserRole.ADMIN)
    assert client.post(f"/admin/users/{request_id('t1001')}/reject").status_code == 204
    assert sign_in(new_client(), "t1001", "teach-pass").status_code == 401
    assert audit_rows("auth.login_failed")[0].details["reason"] == "disabled"
    assert len(audit_rows("user.reject")) == 1


def test_own_department_is_approved_automatically(client, university):
    university["departments"] = {"ภาควิชาวิศวกรรมคอมพิวเตอร์"}
    university["fake"].department = "ภาควิชาวิศวกรรมไฟฟ้า"
    assert sign_in(client, "t1001", "teach-pass").status_code == 403  # other department
    university["fake"].department = " ภาควิชาวิศวกรรม  คอมพิวเตอร์"  # spacing differs
    assert sign_in(new_client(), "t1002", "teach-pass").status_code == 200
    (created,) = audit_rows("user.create")
    assert created.details["auto_approved"] is True


def test_student_usernames_are_refused_before_the_university_is_asked(client, university):
    for username in ("68369999", "somchaij68@nu.ac.th"):
        assert sign_in(client, username, "any-pass").status_code == 401
    assert university["fake"].calls == 0  # the password went nowhere
    reasons = {r.details["reason"] for r in audit_rows("auth.login_failed")}
    assert reasons == {"type_not_allowed:student"}


def test_teachers_students_and_wrong_passwords_are_refused(client, university):
    # Teachers get share links instead of accounts; students never get in.
    assert sign_in(client, "p2001", "prof-pass").status_code == 401
    assert sign_in(client, "s6501", "study-pass").status_code == 401
    assert sign_in(client, "t1001", "nope").status_code == 401
    reasons = sorted(r.details["reason"] for r in audit_rows("auth.login_failed"))
    assert reasons == ["type_not_allowed:student", "type_not_allowed:teacher", "wrong_password"]
    assert audit_rows("user.request") == []
    with new_session() as db:
        assert db.scalar(select(User).where(User.email == "s6501@uni.example")) is None
        assert db.scalar(select(User).where(User.email == "t1001@uni.example")) is None


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


def test_teacher_admin_added_by_id_skips_the_queue(client, university, login):
    login(UserRole.ADMIN)
    response = client.post(
        "/admin/users",
        json={"email": "x@dept.example", "display_name": "อ.ทดสอบ", "university_id": "T1001"},
    )
    assert response.status_code == 201
    assert sign_in(new_client(), "t1001", "teach-pass").status_code == 200
    assert audit_rows("user.request") == []


def test_first_login_links_to_a_user_admin_added_by_email(client, university, login):
    login(UserRole.ADMIN)
    client.post("/admin/users", json={"email": "t1001@uni.example", "display_name": "Pre"})
    me = sign_in(new_client(), "t1001", "teach-pass").json()
    assert me["display_name"] == "Pre"


def test_disabled_teacher_cannot_log_in(client, university, login):
    login(UserRole.ADMIN)
    client.post("/admin/users", json={"email": "t1001@uni.example", "display_name": "Pre"})
    user_id = sign_in(new_client(), "t1001", "teach-pass").json()["id"]
    with new_session() as db:
        db.execute(update(User).where(User.id == user_id).values(status=UserStatus.DISABLED))
        db.commit()
    assert sign_in(new_client(), "t1001", "teach-pass").status_code == 401
    assert audit_rows("auth.login_failed")[0].details["reason"] == "disabled"
