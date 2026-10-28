"""Share links: limits from settings, public/password, view-only, download cap, lockout, log."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from dbresearch.db import new_session
from dbresearch.main import app
from dbresearch.models import AuditEvent, ShareLink, UserRole
from dbresearch.security import token_hash
from tests.conftest import API, CSRF, make_pdf, needs_db

pytestmark = needs_db


def setup_doc(client) -> tuple[str, bytes]:
    pdf = make_pdf()
    doc_id = client.post(
        "/documents", files={"file": ("ทดสอบ.pdf", pdf, "application/pdf")}
    ).json()["id"]
    return doc_id, pdf


def share(client, doc_id, **body):
    response = client.post(f"/documents/{doc_id}/shares", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def guest() -> TestClient:
    return TestClient(app, headers=CSRF, base_url=API)  # no session cookie: an outsider


def test_public_link_lets_a_guest_download_and_logs_it(client, login):
    login()
    doc_id, pdf = setup_doc(client)
    link = share(client, doc_id)
    assert link["state"] == "active" and link["password"] is None
    expires = datetime.fromisoformat(link["expires_at"])
    assert timedelta(hours=23) < expires - datetime.now(UTC) <= timedelta(hours=24)

    with guest() as g:
        info = g.get(link["path"])
        assert info.status_code == 200 and info.json()["unlocked"] is True
        assert info.headers["referrer-policy"] == "no-referrer"
        assert g.get(f"{link['path']}/file?download=true").content == pdf
    with new_session() as db:
        stored = db.scalar(select(ShareLink))
        actions = db.scalars(select(AuditEvent.action)).all()
    assert stored.token_hash == token_hash(link["token"]) and stored.download_count == 1
    assert "document.download" in actions
    events = [e["event"] for e in client.get(f"/shares/{link['id']}/log").json()]
    assert set(events) == {"open", "download"}


def test_ttl_caps_from_settings(client, login):
    login(UserRole.USER)
    doc_id, _ = setup_doc(client)
    assert client.post(f"/documents/{doc_id}/shares", json={"ttl_hours": 169}).status_code == 422
    assert client.post(f"/documents/{doc_id}/shares", json={"ttl_hours": 168}).status_code == 201
    login(UserRole.ADMIN)
    assert client.post(f"/documents/{doc_id}/shares", json={"ttl_hours": 720}).status_code == 201
    assert client.post(f"/documents/{doc_id}/shares", json={"ttl_hours": 721}).status_code == 422


def test_password_link_unlock_lockout_and_new_password(client, login):
    login()
    doc_id, pdf = setup_doc(client)
    link = share(client, doc_id, access="password")
    password = link["password"]
    assert len(password) == 10
    with guest() as g:
        assert g.get(link["path"]).json()["unlocked"] is False
        assert g.get(f"{link['path']}/file").status_code == 401
        assert g.post(f"{link['path']}/unlock", json={"password": "nope"}).status_code == 403
        assert g.post(f"{link['path']}/unlock", json={"password": password}).status_code == 204
        assert g.get(link["path"]).json()["unlocked"] is True
        assert g.get(f"{link['path']}/file").content == pdf  # inline view

    with new_session() as db:  # nine more wrong guesses → locked (limit 10)
        db.execute(update(ShareLink).values(failed_attempts=9))
        db.commit()
    with guest() as g:
        g.post(f"{link['path']}/unlock", json={"password": "nope"})
        assert g.get(link["path"]).status_code == 404
    assert client.get("/shares").json()[0]["state"] == "locked"

    fresh = client.post(f"/shares/{link['id']}/password").json()["password"]
    assert fresh != password
    with guest() as g:
        assert g.post(f"{link['path']}/unlock", json={"password": password}).status_code == 403
        assert g.post(f"{link['path']}/unlock", json={"password": fresh}).status_code == 204


def test_view_only_and_download_limit(client, login):
    login()
    doc_id, _ = setup_doc(client)
    view_only = share(client, doc_id, allow_download=False)
    limited = share(client, doc_id, max_downloads=1)
    with guest() as g:
        assert g.get(f"{view_only['path']}/file?download=true").status_code == 403
        assert g.get(f"{view_only['path']}/file").status_code == 200  # inline view allowed
        assert g.get(f"{limited['path']}/file?download=true").status_code == 200
        assert g.get(f"{limited['path']}/file?download=true").status_code == 404
    assert {s["id"]: s["state"] for s in client.get("/shares").json()}[limited["id"]] == "exhausted"


def test_revoked_expired_and_unknown_links_look_the_same(client, login):
    login()
    doc_id, _ = setup_doc(client)
    revoked, expired = share(client, doc_id), share(client, doc_id)
    assert client.delete(f"/shares/{revoked['id']}").status_code == 204
    with new_session() as db:
        db.execute(
            update(ShareLink)
            .where(ShareLink.id == expired["id"])
            .values(
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.commit()
    with guest() as g:
        replies = [g.get(path) for path in (revoked["path"], expired["path"], "/s/not-a-token")]
    assert {r.status_code for r in replies} == {404}
    assert len({r.json()["detail"] for r in replies}) == 1  # no hint which case it was


def test_only_creator_or_admin_manage_a_link(client, login):
    login()
    doc_id, _ = setup_doc(client)
    link = share(client, doc_id)
    login(UserRole.USER)
    assert client.delete(f"/shares/{link['id']}").status_code == 404
    assert client.get(f"/shares/{link['id']}/log").status_code == 404
    login(UserRole.ADMIN)
    assert client.delete(f"/shares/{link['id']}").status_code == 204


def test_grant_cookie_is_bound_to_its_link(client, login):
    login()
    doc_id, _ = setup_doc(client)
    a = share(client, doc_id, access="password")
    b = share(client, doc_id, access="password")
    with guest() as g:
        g.post(f"{a['path']}/unlock", json={"password": a["password"]})
        grant = g.cookies.get("dbr_grant")
    with guest() as g:
        g.cookies.set("dbr_grant", grant, path="/api" + b["path"])
        assert g.get(f"{b['path']}/file").status_code == 401
