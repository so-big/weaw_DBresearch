from fastapi.testclient import TestClient
from sqlalchemy import select

from dbresearch.db import new_session
from dbresearch.models import AuditEvent, User, UserRole, UserStatus
from tests.conftest import needs_db

pytestmark = needs_db


def test_login_me_logout(client, make_user):
    _, username, password = make_user()
    assert client.get("/auth/me").status_code == 401

    response = client.post("/auth/login", json={"username": username.upper(), "password": password})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    me = client.get("/auth/me").json()
    assert me["display_name"] == username and me["role"] == "user"

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_are_rejected_and_audited(client, make_user):
    _, username, _ = make_user()
    for name, pw in ((username, "wrong password"), ("nobody", "whatever")):
        response = client.post("/auth/login", json={"username": name, "password": pw})
        assert response.status_code == 401
    with new_session() as db:
        actions = db.scalars(select(AuditEvent.action)).all()
    assert actions.count("auth.login_failed") == 2


def test_disabled_user_cannot_log_in_or_use_old_session(client, make_user):
    user_id, username, password = make_user()
    client.post("/auth/login", json={"username": username, "password": password})
    with new_session() as db:
        db.get(User, user_id).status = UserStatus.DISABLED
        db.commit()
    assert client.get("/auth/me").status_code == 401
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401


def test_session_token_is_stored_only_as_hash(client, make_user):
    from dbresearch.models import Session

    _, username, password = make_user()
    client.post("/auth/login", json={"username": username, "password": password})
    token = client.cookies.get("dbr_session")
    with new_session() as db:
        stored = db.scalars(select(Session.token_hash)).all()
    assert token and all(token.encode() not in digest for digest in stored)


def test_state_changing_request_needs_csrf_header(app_db, make_user):
    from dbresearch.main import app

    _, username, password = make_user()
    with TestClient(app) as bare:  # no X-Requested-With header
        response = bare.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 403


def test_require_admin_rejects_normal_users(client, login):
    import pytest
    from fastapi import HTTPException

    from dbresearch.auth import require_admin

    login(UserRole.USER)
    with new_session() as db:
        user = db.scalar(select(User))
    with pytest.raises(HTTPException) as err:
        require_admin(user)
    assert err.value.status_code == 403


def test_cli_creates_admin(app_db, db_clean, monkeypatch, capsys):
    from dbresearch.cli import main

    monkeypatch.setenv("DBR_PASSWORD", "a long admin password")
    main(["create-admin", "--email", "boss@example.test", "--name", "Boss", "--username", "Boss"])
    assert "Created admin boss" in capsys.readouterr().out
    with new_session() as db:
        user = db.scalar(select(User).where(User.email == "boss@example.test"))
    assert user.role == UserRole.ADMIN
