"""Close a project (ปิดโครงการ): closing papers, archive filter, reopen; and user-added options."""

from sqlalchemy import select

from dbresearch.db import new_session
from dbresearch.models import AuditEvent, DocumentVersion, Job, VersionPurpose
from tests.conftest import make_pdf, needs_db
from tests.test_documents import upload

pytestmark = needs_db


def closing_paper(client, doc_id, data=None):
    files = {"file": ("ขออนุมัติปิดโครงการ.pdf", data or make_pdf(2), "application/pdf")}
    return client.post(f"/documents/{doc_id}/closure-files", files=files)


def test_closing_papers_are_separate_from_versions(client, login):
    login()
    doc = upload(client, make_pdf()).json()
    response = closing_paper(client, doc["id"])
    assert response.status_code == 201, response.text
    detail = response.json()
    # The contract keeps its current version; the paper is listed apart and queued for OCR.
    assert [v["version_no"] for v in detail["versions"]] == [1]
    assert [(f["version_no"], f["page_count"]) for f in detail["closure_files"]] == [(1, 2)]
    assert detail["status"] == "processing"  # unchanged by the paper (still the first upload)
    with new_session() as db:
        papers = db.scalars(
            select(DocumentVersion).where(DocumentVersion.purpose == VersionPurpose.CLOSURE)
        ).all()
        jobs = db.scalars(select(Job)).all()
    assert len(papers) == 1 and len(jobs) == 2
    # A new main version is still number 2, not 3.
    second = client.post(
        f"/documents/{doc['id']}/versions",
        files={"file": ("v2.pdf", make_pdf(), "application/pdf")},
    ).json()
    assert [v["version_no"] for v in second["versions"]] == [2, 1]
    paper = client.get(f"/documents/{doc['id']}/file?closure=1")
    assert paper.status_code == 200 and paper.content.startswith(b"%PDF")
    assert client.get(f"/documents/{doc['id']}/file?version=3").status_code == 404


def test_close_archive_and_reopen(client, login):
    login()
    open_id = upload(client, make_pdf()).json()["id"]
    closed_id = upload(client, make_pdf()).json()["id"]
    response = client.post(
        f"/documents/{closed_id}/close",
        json={"closed_on": "2025-08-07", "closure_ref": " อว 0000.00/123 ", "closure_note": ""},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["closed_on"] == "2025-08-07" and body["closed_at"]
    assert body["closure_ref"] == "อว 0000.00/123" and body["closure_note"] is None
    assert body["closed_by_name"]

    def ids(**params):
        return {d["id"] for d in client.get("/documents", params=params).json()["items"]}

    assert ids(project="open") == {open_id}
    assert ids(project="closed") == {closed_id}
    assert ids() == {open_id, closed_id}
    facets = client.get("/documents", params={"with_facets": True}).json()["facets"]
    assert {f["value"]: f["count"] for f in facets["project"]} == {"open": 1, "closed": 1}

    reopened = client.post(f"/documents/{closed_id}/reopen").json()
    assert reopened["closed_at"] is None and reopened["closure_ref"] == "อว 0000.00/123"
    assert client.post(f"/documents/{closed_id}/reopen").status_code == 409
    with new_session() as db:
        actions = db.scalars(select(AuditEvent.action)).all()
    assert {"document.close", "document.reopen"} <= set(actions)


def test_only_uploader_or_admin_closes(client, login):
    login()
    doc_id = upload(client, make_pdf()).json()["id"]
    login()  # someone else
    assert client.post(f"/documents/{doc_id}/close", json={}).status_code == 403
    assert closing_paper(client, doc_id).status_code == 403


def test_any_user_adds_a_category_option(client, login):
    login()
    groups = client.get("/categories").json()
    group = next(g for g in groups if g["key"] == "research_type")
    response = client.post(
        "/categories", json={"group_id": group["id"], "name_th": "  วิจัย  เชิงทดลองใหม่ "}
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name_th"] == "วิจัย เชิงทดลองใหม่"
    # Same name with other spacing: the existing option comes back, no duplicate.
    again = client.post("/categories", json={"group_id": group["id"], "name_th": "วิจัยเชิงทดลองใหม่"})
    assert again.status_code == 200 and again.json()["id"] == created["id"]
    names = [o["name_th"] for g in client.get("/categories").json() for o in g["options"]]
    assert names.count("วิจัย เชิงทดลองใหม่") == 1
    with new_session() as db:
        assert "category.create" in db.scalars(select(AuditEvent.action)).all()
