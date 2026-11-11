"""Uploads from visitors without a live session are refused before the body is read."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from dbresearch.upload_guard import UploadAuthGuard
from tests.conftest import make_pdf, needs_db


def call(method: str, path: str, headers: dict[str, str]) -> tuple[int, bool]:
    """Run the guard alone; returns (status, whether the inner app was reached)."""
    reached = []
    sent = []

    async def inner(scope, receive, send):
        reached.append(True)

    async def receive():
        raise AssertionError("the body must not be read")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    asyncio.run(UploadAuthGuard(inner)(scope, receive, send))
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), 0)
    return status, bool(reached)


MULTIPART = {"content-type": "multipart/form-data; boundary=x"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_form_without_a_cookie_is_refused_unread(method):
    assert call(method, "/api/documents", MULTIPART) == (401, False)
    urlencoded = {"content-type": "application/x-www-form-urlencoded"}
    assert call(method, "/api/documents/x/papers", urlencoded) == (401, False)


def test_other_requests_pass_through():
    assert call("GET", "/api/documents", MULTIPART) == (0, True)
    assert call("POST", "/api/s/token/unlock", {"content-type": "application/json"}) == (0, True)
    assert call("POST", "/api/auth/login", {"content-type": "application/json"}) == (0, True)
    assert call("POST", "/not-api", MULTIPART) == (0, True)


# ───────────── Through the app (needs the DB) ─────────────
def upload(client):
    return client.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")})


@needs_db
def test_upload_needs_a_live_session(client, login):
    assert upload(client).status_code == 401
    client.cookies.set("dbr_session", "made-up")
    assert upload(client).status_code == 401
    client.cookies.clear()

    user_id = login()
    assert upload(client).status_code == 201

    from dbresearch.db import new_session
    from dbresearch.models import Session as UserSession

    with new_session() as db:  # idle past the timeout
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=61))
        )
        db.commit()
    response = upload(client)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"  # outer middleware still ran


@needs_db
def test_upload_with_an_expired_session_is_refused(client, login):
    user_id = login()
    from dbresearch.db import new_session
    from dbresearch.models import Session as UserSession

    with new_session() as db:  # past the hard limit
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        db.commit()
    assert upload(client).status_code == 401
