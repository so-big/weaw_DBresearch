import pytest
from sqlalchemy import select

from dbresearch.config import get_settings
from dbresearch.db import new_session
from dbresearch.models import AuditEvent, DocumentVersion, Job, UserRole
from tests.conftest import make_pdf, needs_db

pytestmark = needs_db
THAI_NAME = "สัญญารับทุน R2568A001.pdf"


def upload(client, data: bytes, name: str = THAI_NAME, **form):
    return client.post("/documents", files={"file": (name, data, "application/pdf")}, data=form)


def blob_files():
    return [p for p in get_settings().blob_dir.rglob("*") if p.is_file()]


def test_upload_encrypts_stores_and_queues_ocr(client, login):
    login()
    pdf = make_pdf(pages=3)
    response = upload(client, pdf, funding_type="external")
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["status"] == "processing" and doc["funding_type"] == "external"
    assert doc["kind"] is None and doc["can_edit"] is True
    assert doc["versions"][0]["page_count"] == 3
    assert doc["versions"][0]["size_bytes"] == len(pdf)

    with new_session() as db:
        version = db.scalar(select(DocumentVersion))
        job = db.scalar(select(Job))
        actions = db.scalars(select(AuditEvent.action)).all()
    assert job.kind == "ocr" and job.payload == {"version_id": str(version.id)}
    assert "document.upload" in actions

    # The blob on disk is ciphertext: no PDF header, no plaintext slice.
    (blob,) = [p for p in blob_files() if p.name == version.storage_key]
    stored = blob.read_bytes()
    assert not stored.startswith(b"%PDF") and pdf[100:164] not in stored


def test_download_roundtrip_with_thai_filename(client, login):
    login()
    pdf = make_pdf()
    doc_id = upload(client, pdf).json()["id"]
    response = client.get(f"/documents/{doc_id}/file")
    assert response.status_code == 200
    assert response.content == pdf
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;") and "filename*=UTF-8''" in disposition
    assert response.headers["cache-control"] == "no-store"
    inline = client.get(f"/documents/{doc_id}/file?inline=true")
    assert inline.headers["content-disposition"].startswith("inline;")
    assert inline.headers["content-security-policy"] == "sandbox"
    with new_session() as db:
        actions = db.scalars(select(AuditEvent.action)).all()
    assert {"document.download", "document.view"} <= set(actions)


def test_non_pdf_is_rejected_without_leaving_a_blob(client, login):
    login()
    before = len(blob_files())
    response = upload(client, b"MZ\x90\x00 not a pdf", name="virus.exe")
    assert response.status_code == 400
    assert len(blob_files()) == before


def test_duplicate_upload_points_to_existing_document(client, login):
    login()
    pdf = make_pdf()
    first = upload(client, pdf).json()["id"]
    before = len(blob_files())
    response = upload(client, pdf)
    assert response.status_code == 409 and response.json()["document_id"] == first
    assert len(blob_files()) == before


def test_upload_size_limit(client, login, monkeypatch):
    login()
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    before = len(blob_files())
    response = upload(client, make_pdf())
    assert response.status_code in (400, 413)
    assert len(blob_files()) == before


def test_versions_need_edit_rights_and_old_versions_stay_readable(client, login, make_user):
    login()
    v1, v2 = make_pdf(), make_pdf()
    doc_id = upload(client, v1).json()["id"]

    response = client.post(
        f"/documents/{doc_id}/versions", files={"file": ("v2.pdf", v2, "application/pdf")}
    )
    assert response.status_code == 201
    assert [v["version_no"] for v in response.json()["versions"]] == [2, 1]
    assert client.get(f"/documents/{doc_id}/file").content == v2
    assert client.get(f"/documents/{doc_id}/file?version=1").content == v1

    login(UserRole.USER)  # someone else: can read, can't add versions
    assert client.get(f"/documents/{doc_id}").json()["can_edit"] is False
    response = client.post(
        f"/documents/{doc_id}/versions", files={"file": ("v3.pdf", make_pdf(), "application/pdf")}
    )
    assert response.status_code == 403

    login(UserRole.ADMIN)
    response = client.post(
        f"/documents/{doc_id}/versions", files={"file": ("v3.pdf", make_pdf(), "application/pdf")}
    )
    assert response.status_code == 201


def test_ciphertext_is_bound_to_its_version_row(client, login):
    from tink import TinkError

    from dbresearch.documents import read_version

    login()
    doc_a = upload(client, make_pdf()).json()["id"]
    doc_b = upload(client, make_pdf()).json()["id"]
    with new_session() as db:
        a = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc_a))
        b = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc_b))
        a.wrapped_dek = b.wrapped_dek  # an attacker swaps keys between rows
    with pytest.raises(TinkError):
        b"".join(read_version(a))


def test_kek_init_refuses_to_overwrite(tmp_path):
    from dbresearch.cli import main

    out = tmp_path / "kek.json"
    main(["kek-init", "--out", str(out)])
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(SystemExit):
        main(["kek-init", "--out", str(out)])
