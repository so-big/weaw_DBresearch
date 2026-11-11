"""Job queue + worker, end to end with real Tesseract (runs in the server's containers)."""

import io
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from dbresearch import jobs
from dbresearch.config import get_settings
from dbresearch.db import new_session
from dbresearch.models import (
    DocStatus,
    Document,
    DocumentPage,
    DocumentVersion,
    Job,
    JobState,
    OcrStatus,
)
from tests.conftest import needs_db

pytestmark = needs_db
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="no tesseract")


def scanned_pdf(lines: list[tuple[int, str]], footer: str) -> bytes:
    """An image-only A4 'scan' (like the real uploads), rendered with Pillow's own font."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=56)
    for y, text in lines:
        draw.text((300, y), text, fill=0, font=font)
    draw.text((300, 3300), footer, fill=0, font=font)
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=300)
    return buffer.getvalue()


@needs_tesseract
def test_upload_then_worker_suggests_contract_number_and_funding(client, login):
    from dbresearch.worker.__main__ import run_once

    login()
    pdf = scanned_pdf(
        [(300, "Research grant contract"), (400, "Example project")],
        footer=f"R2568A{uuid.uuid4().int % 900 + 100} page 1",
    )
    doc_id = client.post("/documents", files={"file": ("scan.pdf", pdf, "application/pdf")}).json()[
        "id"
    ]

    assert run_once() is True
    assert run_once() is False  # queue empty

    with new_session() as db:
        document = db.get(Document, uuid.UUID(doc_id))
        version = db.get(DocumentVersion, document.current_version_id)
        pages = db.scalars(select(DocumentPage)).all()
        job = db.scalar(select(Job))
    assert job.state == JobState.DONE
    assert version.ocr_status == OcrStatus.DONE and document.status == DocStatus.NEEDS_REVIEW
    assert len(pages) == 1 and "Research grant contract" in pages[0].text
    suggestions = version.extracted_fields
    assert suggestions["fields"]["reference_no"]["value"].startswith("R2568A")
    # The series letter is the faculty, not the funding type; this page has no Thai title block.
    assert suggestions["inferred"]["funding_type"] is None
    assert "researchgrantcontract" in document.search_text
    # The decrypted copy was removed from the worker's scratch space.
    assert not list(get_settings().work_dir.glob("*.pdf"))

    review = client.get(f"/documents/{doc_id}/autofill").json()
    assert review["ocr_status"] == "done" and review["suggestions"]["fields"]


def test_claim_hands_out_each_job_once_and_retries_with_backoff(db_clean):
    with new_session() as db:
        jobs.enqueue(db, "noop", n=1)
        jobs.enqueue(db, "noop", n=2)
        db.commit()
    with new_session() as a, new_session() as b:
        first, second = jobs.claim(a), jobs.claim(b)
        assert {first.payload["n"], second.payload["n"]} == {"1", "2"}
        assert jobs.claim(a) is None
        assert jobs.fail(a, first, "boom") is True  # attempt 1 of 3 → retry later
        assert jobs.claim(a) is None  # backoff: not due yet
        a.execute(update(Job).where(Job.id == first.id).values(run_after=datetime.now(UTC)))
        a.commit()
        again = jobs.claim(a)
        assert again.id == first.id and again.attempts == 2


def test_stale_running_job_is_reclaimed(db_clean):
    with new_session() as db:
        job = jobs.enqueue(db, "noop")
        db.commit()
        jobs.claim(db)
        db.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
        )
        db.commit()
        assert jobs.claim(db).id == job.id  # its worker crashed: hand it out again


def test_ocr_that_keeps_failing_falls_back_to_manual_review(client, login):
    from dbresearch.blobstore import get_blobstore
    from dbresearch.worker.__main__ import run_once
    from tests.conftest import make_pdf

    login()
    doc_id = client.post(
        "/documents", files={"file": ("x.pdf", make_pdf(), "application/pdf")}
    ).json()["id"]
    with new_session() as db:
        version = db.scalar(select(DocumentVersion))
        get_blobstore().delete(version.storage_key)  # simulate a lost blob
        db.execute(update(Job).values(attempts=jobs.MAX_ATTEMPTS - 1))
        db.commit()
    assert run_once() is True
    with new_session() as db:
        document = db.get(Document, uuid.UUID(doc_id))
        version = db.get(DocumentVersion, document.current_version_id)
        job = db.scalar(select(Job))
    assert job.state == JobState.FAILED and "FileNotFoundError" in job.last_error
    assert version.ocr_status == OcrStatus.FAILED
    assert document.status == DocStatus.NEEDS_REVIEW
    assert version.extracted_fields["warnings"][0]["code"] == "ocr_failed"
    assert "x.pdf" in document.search_text  # findable by file name even without OCR


@needs_tesseract
def test_closing_paper_is_read_without_touching_the_review(client, login):
    from dbresearch.worker.__main__ import run_once

    login()
    contract = scanned_pdf([(300, "Research grant contract")], footer="page 1")
    doc_id = client.post(
        "/documents", files={"file": ("c.pdf", contract, "application/pdf")}
    ).json()["id"]
    assert run_once() is True  # the contract itself → needs_review
    paper = scanned_pdf([(300, "Closing memo zebracorn"), (400, "Contract R2567E101")], footer="1")
    response = client.post(
        f"/documents/{doc_id}/closure-files",
        files={"file": ("close.pdf", paper, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert run_once() is True

    detail = client.get(f"/documents/{doc_id}").json()
    (closing,) = detail["closure_files"]
    assert closing["ocr_status"] == "done"
    assert closing["readings"].get("reference_no") == "R2567E101"
    assert detail["status"] == "needs_review" and len(detail["versions"]) == 1
    # The closing paper's text is searchable through the contract.
    found = client.get("/documents", params={"q": "zebracorn"}).json()["items"]
    assert [d["id"] for d in found] == [doc_id]


@needs_tesseract
def test_proposal_grant_papers_go_to_the_memo_reader(client, login):
    """kind proposal_dev → `autofill.proposal` (memo reader), not the contract templates."""
    from dbresearch.models import DocKind
    from dbresearch.worker.__main__ import run_once

    login()
    paper = scanned_pdf([(300, "Memo zebracorn")], footer="1")
    doc_id = client.post("/documents", files={"file": ("p.pdf", paper, "application/pdf")}).json()[
        "id"
    ]
    with new_session() as db:
        db.execute(update(Document).where(Document.id == doc_id).values(kind=DocKind.PROPOSAL_DEV))
        db.commit()
    assert run_once() is True
    with new_session() as db:
        version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc_id))
        document = db.get(Document, uuid.UUID(doc_id))
    payload = version.extracted_fields
    assert "sections" not in payload  # not the contract pipeline
    assert payload["kind"] is None and payload["warnings"] == [{"code": "unknown_paper_type"}]
    assert document.status == DocStatus.NEEDS_REVIEW
