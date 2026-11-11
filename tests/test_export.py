"""Excel / CSV export of search results and the proposal report. Invented values."""

import csv
import io

from openpyxl import load_workbook
from sqlalchemy import select

from dbresearch import export
from dbresearch.db import new_session
from dbresearch.models import AuditEvent
from tests.conftest import make_pdf, needs_db
from tests.test_documents import upload
from tests.test_proposals_api import new_grant, review

BOM = b"\xef\xbb\xbf"


def xlsx_rows(content: bytes) -> list[tuple]:
    sheet = load_workbook(io.BytesIO(content)).active
    return list(sheet.iter_rows(values_only=True))


def csv_rows(content: bytes) -> list[list[str]]:
    assert content.startswith(BOM)
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


def make_contract(client, title: str, ref: str, **fields) -> str:
    doc_id = upload(client, make_pdf()).json()["id"]
    body = {
        "title": title,
        "kind": "contract",
        "funding_type": "internal",
        "reference_no": ref,
        "fiscal_year": 2026,
        "document_date": "2025-12-03",
        "budget_total": "150000",
    } | fields
    response = client.put(f"/documents/{doc_id}/metadata", json=body)
    assert response.status_code == 200, response.text
    return doc_id


def test_formula_injection_guard():
    for text in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert export.safe(text) == "'" + text
    assert export.safe("สัญญา") == "สัญญา"
    assert export.safe(-5) == -5 and export.safe(None) is None
    for build in (
        lambda rows: export.build_xlsx("s", ["h"], rows),
        lambda rows: export.build_csv(["h"], rows),
    ):
        data = build([["=cmd|' /C calc'!A0"], ["ปกติ"]])
        cells = xlsx_rows(data) if data[:2] == b"PK" else csv_rows(data)
        assert [c[0] for c in cells[1:]] == ["'=cmd|' /C calc'!A0", "ปกติ"]


def test_thai_date_and_filename():
    from datetime import date

    assert export.th_date(date(2025, 12, 3)) == "03/12/2568"
    assert export.th_date(None) is None
    disposition = export.content_disposition("dbresearch-contracts-2026-11-12.xlsx")
    assert disposition.startswith('attachment; filename="dbresearch-contracts-')
    assert "filename*=UTF-8''" in disposition


@needs_db
def test_requires_login(client):
    assert client.get("/documents/export").status_code == 401
    assert client.get("/reports/proposals/export").status_code == 401


@needs_db
def test_contract_export_respects_filters(client, login):
    login()
    keep = make_contract(client, "งานวิจัยตัวอย่างหนึ่ง", "R2569E001")
    make_contract(client, "งานวิจัยตัวอย่างสอง", "R2569E002", funding_type="external")
    assert keep

    everything = client.get("/documents/export", params={"format": "csv"})
    assert everything.status_code == 200, everything.text
    assert everything.headers["cache-control"] == "no-store"
    assert everything.headers["content-disposition"].startswith("attachment;")
    assert len(csv_rows(everything.content)) == 3  # header + 2

    only = client.get("/documents/export", params={"format": "csv", "funding_type": "internal"})
    rows = csv_rows(only.content)
    assert rows[0] == export.CONTRACT_HEADERS
    assert len(rows) == 2
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["เลขที่สัญญา"] == "R2569E001"
    assert row["ชื่อเรื่อง (ไทย)"] == "งานวิจัยตัวอย่างหนึ่ง"
    assert row["ปีงบประมาณ (พ.ศ.)"] == "2569"
    assert row["วันที่เอกสาร (พ.ศ.)"] == "03/12/2568"
    assert row["ประเภททุน"] == "ทุนภายใน"

    sheet = xlsx_rows(client.get("/documents/export", params={"funding_type": "internal"}).content)
    assert len(sheet) == 2
    assert sheet[1][8] == 150000  # budget stays a number

    nothing = client.get("/documents/export", params={"format": "csv", "q": "ไม่มีคำนี้แน่นอน"})
    assert len(csv_rows(nothing.content)) == 1


@needs_db
def test_export_leaves_out_ocr_text_and_ids(client, login):
    login()
    doc_id = make_contract(client, "งานวิจัยตัวอย่าง", "R2569E001")
    text = client.get("/documents/export", params={"format": "csv"}).content.decode("utf-8-sig")
    assert doc_id not in text
    assert not {"snippet", "sha256", "search_text"} & set(text.split(","))


@needs_db
def test_proposal_section_export(client, login):
    login()
    grant = new_grant(client)
    body = review(proposal={"research_area": "เทคโนโลยีสมมติ", "kpi_due": "2099-09-01"})
    assert client.put(f"/documents/{grant}/metadata", json=body).status_code == 200
    response = client.get("/documents/export", params={"section": "proposals", "format": "csv"})
    rows = csv_rows(response.content)
    assert rows[0] == export.PROPOSAL_HEADERS
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["หน่วยงาน"] == "ภาควิชาสมมติ"
    assert row["กรอบงานวิจัย"] == "เทคโนโลยีสมมติ"
    assert row["สถานะ"] == "ดำเนินการอยู่"
    assert row["กำหนดส่งผลงาน (พ.ศ.)"] == "01/09/2642"
    assert "สมมติ ทดสอบดี" in row["ผู้วิจัย"]
    # contracts export does not include the grant
    assert len(csv_rows(client.get("/documents/export", params={"format": "csv"}).content)) == 1


@needs_db
def test_report_export(client, login):
    login()
    grant = new_grant(client)
    assert client.put(f"/documents/{grant}/metadata", json=review()).status_code == 200
    for fmt, parse in (("csv", csv_rows), ("xlsx", xlsx_rows)):
        response = client.get("/reports/proposals/export", params={"format": fmt})
        assert response.status_code == 200, response.text
        rows = parse(response.content)
        assert list(rows[0]) == export.REPORT_HEADERS
        assert str(rows[1][0]) == "2569" and str(rows[1][1]) == "1"


@needs_db
def test_export_is_audited(client, login):
    user_id = login()
    make_contract(client, "งานวิจัยตัวอย่าง", "R2569E001")
    client.get("/documents/export", params={"format": "csv", "funding_type": "internal"})
    client.get("/reports/proposals/export", params={"format": "xlsx"})
    with new_session() as db:
        events = {
            e.action: e
            for e in db.scalars(select(AuditEvent).where(AuditEvent.action.like("export.%")))
        }
    docs = events["export.documents"]
    assert docs.actor_id == user_id
    assert docs.details["format"] == "csv" and docs.details["rows"] == 1
    assert docs.details["filters"]["funding_type"] == ["internal"]
    report = events["export.proposals"]
    assert report.details["format"] == "xlsx" and report.details["rows"] == 0


@needs_db
def test_export_cap(client, login, monkeypatch):
    login()
    make_contract(client, "งานวิจัยตัวอย่างหนึ่ง", "R2569E001")
    make_contract(client, "งานวิจัยตัวอย่างสอง", "R2569E002")
    monkeypatch.setattr(export, "MAX_ROWS", 1)
    response = client.get("/documents/export", params={"format": "csv"})
    assert response.status_code == 400
    assert "Too many results" in response.json()["detail"]
    monkeypatch.setattr(export, "MAX_ROWS", 2)
    assert client.get("/documents/export", params={"format": "csv"}).status_code == 200
