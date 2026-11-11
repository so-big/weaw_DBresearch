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


def test_trashed_duplicate_is_refused_with_restore_hint(client, login):
    login()
    pdf = make_pdf()
    first = upload(client, pdf).json()["id"]
    assert client.delete(f"/documents/{first}").status_code == 204
    before = len(blob_files())

    response = upload(client, pdf)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "This exact file is in the trash",
        "document_id": first,
        "trashed": True,
        "can_restore": True,
    }
    assert len(blob_files()) == before

    # Restoring brings the one document back; the same file is then a plain live duplicate.
    assert client.post("/documents/trash/restore", json={"ids": [first]}).status_code == 200
    again = upload(client, pdf)
    assert again.status_code == 409 and "trashed" not in again.json()


def test_trashed_duplicate_restore_hint_follows_restore_rule(client, login):
    login()
    pdf = make_pdf()
    first = upload(client, pdf).json()["id"]
    client.delete(f"/documents/{first}")
    login(UserRole.USER)  # a different user: may not restore it
    body = upload(client, pdf).json()
    assert body["trashed"] is True and body["can_restore"] is False
    login(UserRole.ADMIN)
    assert upload(client, pdf).json()["can_restore"] is True


def test_same_file_uploaded_at_once_is_stored_once(make_user):
    import io
    import threading
    import time

    from dbresearch.documents import DuplicateUpload, store_version
    from dbresearch.models import User

    user_id, _, _ = make_user()
    pdf = make_pdf()
    before = len(blob_files())
    outcome: dict = {}

    def second_upload():
        with new_session() as db:
            try:
                store_version(db, db.get(User, user_id), io.BytesIO(pdf), "b.pdf")
                db.commit()
                outcome["result"] = "stored"
            except DuplicateUpload:
                db.rollback()
                outcome["result"] = "duplicate"

    with new_session() as first:
        store_version(first, first.get(User, user_id), io.BytesIO(pdf), "a.pdf")
        # Flushed but not committed: the second upload must wait for it.
        thread = threading.Thread(target=second_upload)
        thread.start()
        time.sleep(1)
        assert thread.is_alive() and not outcome
        first.commit()
    thread.join(timeout=20)

    assert outcome == {"result": "duplicate"}
    assert len(blob_files()) == before + 1  # the loser's ciphertext was removed
    with new_session() as db:
        assert len(db.scalars(select(DocumentVersion)).all()) == 1


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
