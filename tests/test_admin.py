"""Admin: users, trash/restore/purge, settings, categories, templates, reports, audit."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from dbresearch.config import get_settings
from dbresearch.db import new_session
from dbresearch.main import app
from dbresearch.models import AuditEvent, Document, DocumentVersion, UserRole
from tests.conftest import API, CSRF, make_pdf, needs_db
from tests.test_review import category, metadata

pytestmark = needs_db


def upload(client, **meta) -> str:
    doc_id = client.post(
        "/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}
    ).json()["id"]
    if meta:
        assert client.put(f"/documents/{doc_id}/metadata", json=metadata(**meta)).status_code == 200
    return doc_id


def test_admin_routes_need_admin(client, login):
    login(UserRole.USER)
    for path in ("/admin/users", "/admin/trash", "/admin/audit", "/admin/reports/overview"):
        assert client.get(path).status_code == 403


def test_user_lifecycle(client, login):
    admin_id = login(UserRole.ADMIN)
    body = {
        "email": "new@example.test",
        "display_name": "New",
        "username": "newbie",
        "password": "a long enough password",
    }
    created = client.post("/admin/users", json=body)
    assert created.status_code == 201
    assert client.post("/admin/users", json=body).status_code == 409
    user_id = created.json()["id"]

    with TestClient(app, headers=CSRF, base_url=API) as other:
        assert (
            other.post(
                "/auth/login", json={"username": "newbie", "password": body["password"]}
            ).status_code
            == 200
        )
        client.patch(f"/admin/users/{user_id}", json={"status": "disabled"})
        assert other.get("/auth/me").status_code == 401  # sessions die with the account

    assert client.patch(f"/admin/users/{admin_id}", json={"role": "user"}).status_code == 422
    sso = client.post("/admin/users", json={"email": "sso@example.test", "display_name": "SSO"})
    assert sso.status_code == 201  # no local login: the college SSO will authenticate them


def test_trash_restore_and_purge(client, login, make_user):
    login()
    doc_id = upload(client)
    link = client.post(f"/documents/{doc_id}/shares", json={}).json()

    login(UserRole.USER)  # not the uploader
    assert client.delete(f"/documents/{doc_id}").status_code == 403

    login(UserRole.ADMIN)
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404
    with TestClient(app, headers=CSRF, base_url=API) as guest:
        assert guest.get(link["path"]).status_code == 404  # its link died with it
    assert [d["id"] for d in client.get("/admin/trash").json()] == [doc_id]

    assert client.post(f"/admin/trash/{doc_id}/restore").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 200
    with TestClient(app, headers=CSRF, base_url=API) as guest:
        assert guest.get(link["path"]).status_code == 404  # restoring doesn't revive links
    assert client.get("/admin/shares").json() == []  # default: active links only
    states = [s["state"] for s in client.get("/admin/shares", params={"state": "all"}).json()]
    assert states == ["revoked"]

    with new_session() as db:
        key = db.scalar(select(DocumentVersion.storage_key))
    blob = next(p for p in get_settings().blob_dir.rglob(key))
    assert client.delete(f"/admin/trash/{doc_id}").status_code == 404  # not in the trash
    client.delete(f"/documents/{doc_id}")
    assert client.delete(f"/admin/trash/{doc_id}").status_code == 204
    assert not blob.exists()
    with new_session() as db:
        assert db.get(Document, doc_id) is None
        assert db.scalar(select(DocumentVersion)) is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "document.purge"))


def test_restore_refuses_duplicate_contract_number(client, login):
    login(UserRole.ADMIN)
    first = upload(client, reference_no="R2568E001", categories=[], people=[], tags=[])
    client.delete(f"/documents/{first}")
    upload(client, reference_no="R2568E001", categories=[], people=[], tags=[])
    assert client.post(f"/admin/trash/{first}/restore").status_code == 409


def test_settings_change_share_caps(client, login):
    login(UserRole.ADMIN)
    assert client.get("/admin/settings").json()["share.max_ttl_user_hours"] == 168
    assert (
        client.put("/admin/settings/share.max_ttl_user_hours", json={"value": 0}).status_code == 422
    )
    assert (
        client.put("/admin/settings/share.max_ttl_user_hours", json={"value": 48}).status_code
        == 200
    )
    assert client.put("/admin/settings/nope", json={"value": 1}).status_code == 404
    login(UserRole.USER)
    doc_id = upload(client)
    assert client.post(f"/documents/{doc_id}/shares", json={"ttl_hours": 49}).status_code == 422
    login(UserRole.ADMIN)  # restore the default for other tests
    client.put("/admin/settings/share.max_ttl_user_hours", json={"value": 168})


def test_categories_admin(client, login):
    login(UserRole.ADMIN)
    group = client.post(
        "/admin/category-groups", json={"key": "test_group", "name_th": "กลุ่มทดสอบ", "multi": True}
    )
    assert group.status_code == 201
    group_id = group.json()["id"]
    created = client.post("/admin/categories", json={"group_id": group_id, "name_th": "ตัวเลือก"})
    assert created.status_code == 201
    assert (
        client.post(
            "/admin/categories", json={"group_id": group_id, "name_th": "ตัวเลือก"}
        ).status_code
        == 409
    )
    assert client.delete(f"/admin/categories/{created.json()['id']}").status_code == 204

    used = category("research_group", "บุคลากร")
    upload(client, categories=[{"category_id": used}], people=[], tags=[])
    assert client.delete(f"/admin/categories/{used}").status_code == 409
    assert client.patch(f"/admin/categories/{used}", json={"active": False}).status_code == 200
    groups = {g["key"]: g for g in client.get("/categories").json()}
    assert "บุคลากร" not in [o["name_th"] for o in groups["research_group"]["options"]]
    client.patch(f"/admin/categories/{used}", json={"active": True})


def test_template_rules_are_validated(client, login):
    login(UserRole.ADMIN)
    templates = {t["name"]: t for t in client.get("/admin/templates").json()}
    assert set(templates) == {"contract_body", "att_budget", "att_proposal_form"}
    body = templates["att_budget"]
    bad_regex = {"rules": [{"field": "title", "layout": "sentence", "pattern": "("}]}
    bad_post = {"rules": [{"field": "title", "layout": "label", "labels": ["x"], "post": ["nope"]}]}
    bad_field = {"rules": [{"field": "salary", "layout": "label", "labels": ["x"]}]}
    for rules in (bad_regex, bad_post, bad_field):
        response = client.patch(f"/admin/templates/{body['id']}", json={"field_rules": rules})
        assert response.status_code == 422
    ok = client.patch(f"/admin/templates/{body['id']}", json={"priority": 6})
    assert ok.status_code == 200


def test_reports_and_audit(client, login):
    login(UserRole.ADMIN)
    for ref in ("R2568E001", "R2568E004", "R2568A002"):
        upload(client, reference_no=ref, categories=[], people=[], tags=[])
    report = {
        (r["year_be"], r["series"]): r for r in client.get("/admin/reports/missing-numbers").json()
    }
    assert report[(2568, "E")]["missing"] == ["R2568E002", "R2568E003"]
    assert report[(2568, "A")]["missing"] == ["R2568A001"]
    overview = client.get("/admin/reports/overview").json()
    assert overview["documents"]["ready"] == 3 and overview["stored_bytes"] > 0
    entries = client.get("/admin/audit", params={"action": "document."}).json()
    assert {e["action"] for e in entries} >= {"document.upload", "document.confirm"}
    assert all(e["actor_name"] for e in entries)

    with new_session() as db:  # INET values must come back as text, not crash the endpoint
        db.add(AuditEvent(action="auth.login", entity_type="user", ip="203.0.113.7"))
        db.commit()
    entries = client.get("/admin/audit", params={"action": "auth.login"}).json()
    assert "203.0.113.7" in {e["ip"] for e in entries}
