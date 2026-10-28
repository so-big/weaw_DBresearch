"""Select mode: several documents as one zip, move several to the trash, my bin + restore."""

import io
import types
import zipfile

import pytest
from sqlalchemy import select

from dbresearch import documents
from dbresearch.db import new_session
from dbresearch.documents import bundle_names, zip_versions
from dbresearch.models import AuditEvent, UserRole
from tests.conftest import HAS_DB, make_pdf
from tests.test_review import metadata

db_test = pytest.mark.skipif(not HAS_DB, reason="needs the compose stack (DATABASE_URL)")


# ───────────── pure helpers (run anywhere) ─────────────
def test_bundle_names_lead_with_contract_number_and_never_clash():
    names = bundle_names(
        [
            ("R2568E001", "scan.pdf"),
            ("R2568E002", "scan.pdf"),
            (None, "scan.pdf"),
            (None, "Scan.PDF"),
            ("R2568A001", "R2568A001 สัญญา.pdf"),
            (None, "..\\evil.pdf"),
        ]
    )
    assert names == [
        "R2568E001_scan.pdf",
        "R2568E002_scan.pdf",
        "scan.pdf",
        "Scan (2).PDF",
        "R2568A001 สัญญา.pdf",
        "evil.pdf",
    ]


def test_zip_stream_round_trips_in_chunks(monkeypatch):
    files = {"a": b"%PDF-" + bytes(range(256)) * 9000, "b": b"%PDF- small"}
    monkeypatch.setattr(
        documents,
        "read_version",
        lambda v: (files[v.k][i : i + 65536] for i in range(0, len(files[v.k]), 65536)),
    )
    versions = [types.SimpleNamespace(k=k, size_bytes=len(files[k])) for k in files]
    parts = list(zip_versions([("ก.pdf", versions[0]), ("b.pdf", versions[1])]))
    assert len(parts) > 2  # streamed, not built in one piece
    archive = zipfile.ZipFile(io.BytesIO(b"".join(parts)))
    assert archive.testzip() is None
    assert archive.read("ก.pdf") == files["a"] and archive.read("b.pdf") == files["b"]
    assert archive.getinfo("ก.pdf").compress_type == zipfile.ZIP_DEFLATED


# ───────────── API ─────────────
def upload(client, ref: str | None = None, name: str = "scan.pdf") -> tuple[str, bytes]:
    pdf = make_pdf()
    doc_id = client.post("/documents", files={"file": (name, pdf, "application/pdf")}).json()["id"]
    if ref:
        body = metadata(reference_no=ref, categories=[], people=[], tags=[])
        assert client.put(f"/documents/{doc_id}/metadata", json=body).status_code == 200
    return doc_id, pdf


@db_test
def test_zip_download_of_several_documents(client, login):
    login()
    a, pdf_a = upload(client, "R2568E001")
    b, pdf_b = upload(client, "R2568E002")
    c, _ = upload(client)
    client.delete(f"/documents/{c}")  # deleted meanwhile: left out, not an error

    response = client.get("/documents/zip", params={"id": [a, b, c, a]})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.namelist() == ["R2568E001_scan.pdf", "R2568E002_scan.pdf"]
    assert archive.read("R2568E001_scan.pdf") == pdf_a
    assert archive.read("R2568E002_scan.pdf") == pdf_b

    with new_session() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.action == "document.download"))
        logged = {(str(e.entity_id), e.details["bundle"]) for e in rows}
    assert logged == {(a, 2), (b, 2)}

    assert client.get("/documents/zip", params={"id": [c]}).status_code == 404
    assert client.get("/documents/zip").status_code == 422
    too_many = [a] * 101
    assert client.get("/documents/zip", params={"id": too_many}).status_code == 422


@db_test
def test_trash_many_is_all_or_nothing(client, login):
    login()
    mine, _ = upload(client)
    login()  # another user
    theirs, _ = upload(client)
    other, _ = upload(client)

    # One of them isn't mine: nothing moves.
    assert client.post("/documents/trash", json={"ids": [mine, theirs]}).status_code == 403
    assert client.get(f"/documents/{theirs}").status_code == 200

    link = client.post(f"/documents/{theirs}/shares", json={}).json()
    response = client.post("/documents/trash", json={"ids": [theirs, other]})
    assert response.status_code == 200
    assert response.json() == {"deleted": 2, "revoked_links": 1}
    assert client.get(f"/documents/{theirs}").status_code == 404
    assert client.get(link["path"]).status_code == 404
    # Already in the trash: refused as a whole.
    assert client.post("/documents/trash", json={"ids": [theirs]}).status_code == 404
    assert client.post("/documents/trash", json={"ids": []}).status_code == 422


@db_test
def test_my_bin_and_restore(client, login, make_user):
    _, user, user_pw = make_user()
    _, admin, admin_pw = make_user(UserRole.ADMIN)

    def log_in(name, password):
        response = client.post("/auth/login", json={"username": name, "password": password})
        assert response.status_code == 200, response.text

    log_in(user, user_pw)
    kept, _ = upload(client, "R2568E005")
    by_admin, _ = upload(client)
    client.post("/documents/trash", json={"ids": [kept]})

    log_in(admin, admin_pw)
    client.delete(f"/documents/{by_admin}")
    assert client.get("/documents/trash").json() == []  # the admin uploaded nothing
    assert {d["id"] for d in client.get("/admin/trash").json()} == {kept, by_admin}

    # Back as the uploader: both are in my bin, but only my own delete can be undone.
    log_in(user, user_pw)
    bin_ = {d["id"]: d for d in client.get("/documents/trash").json()}
    assert set(bin_) == {kept, by_admin}
    assert bin_[kept]["can_restore"] and not bin_[by_admin]["can_restore"]
    assert bin_[by_admin]["deleted_by_name"] == admin
    assert client.post("/documents/trash/restore", json={"ids": [by_admin]}).status_code == 403
    both = {"ids": [kept, by_admin]}
    assert client.post("/documents/trash/restore", json=both).status_code == 403
    assert client.get(f"/documents/{kept}").status_code == 404  # all or nothing

    assert client.post("/documents/trash/restore", json={"ids": [kept]}).json() == {"restored": 1}
    assert client.get(f"/documents/{kept}").status_code == 200
    assert client.post("/documents/trash/restore", json={"ids": [kept]}).status_code == 404

    login()  # another user neither sees nor restores it
    assert client.get("/documents/trash").json() == []
    assert client.post("/documents/trash/restore", json={"ids": [by_admin]}).status_code == 403


@db_test
def test_restore_stops_at_a_contract_number_clash(client, login):
    login()
    first, _ = upload(client, "R2568E007")
    client.post("/documents/trash", json={"ids": [first]})
    upload(client, "R2568E007")
    response = client.post("/documents/trash/restore", json={"ids": [first]})
    assert response.status_code == 409 and "R2568E007" in response.json()["detail"]
