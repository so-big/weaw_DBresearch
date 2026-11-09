"""Proposal-development grants in the API (DESIGN §11): their own section, review fields,
timeline papers, cancel / close / reopen, filters and the yearly report. Invented values."""

from datetime import date

from sqlalchemy import update

from dbresearch.db import new_session
from dbresearch.models import Document, ProposalProject
from tests.conftest import make_pdf, needs_db
from tests.test_documents import upload

pytestmark = needs_db

TITLE = "ระบบตัวอย่างสำหรับทดสอบทุนพัฒนา"


def new_grant(client) -> str:
    response = upload(client, make_pdf(), name="คำขอ.pdf", kind="proposal_dev")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def review(**overrides) -> dict:
    body = {
        "title": TITLE,
        "kind": "proposal_dev",
        "funding_source": "faculty_income",
        "fiscal_year": 2026,
        "document_date": "2025-12-03",
        "budget_total": "20000",
        "people": [
            {
                "prefix_th": "ผศ.ดร.",
                "name_th": "สมมติ ทดสอบดี",
                "role": "owner",
                "unit": "ภาควิชาสมมติ",
            }
        ],
        "proposal": {
            "request_ref": "อว 0000.00/1",
            "research_area": "เทคโนโลยีสมมติ",
            "kpi_target": "ข้อเสนอโครงการสำหรับทุนภายนอก",
            "kpi_due": "2099-09-01",  # not overdue
        },
    }
    return body | overrides


def paper(client, doc_id, paper_type, **form):
    files = {"file": (f"{paper_type}.pdf", make_pdf(), "application/pdf")}
    response = client.post(
        f"/documents/{doc_id}/papers", files=files, data={"paper_type": paper_type, **form}
    )
    assert response.status_code == 201, response.text
    return response.json()


def ids(client, **params) -> set[str]:
    return {d["id"] for d in client.get("/documents", params=params).json()["items"]}


def test_grants_have_their_own_section(client, login):
    login()
    grant = new_grant(client)
    contract = upload(client, make_pdf()).json()["id"]
    assert ids(client) == {contract}  # the contracts list stays as it was
    assert ids(client, section="proposals") == {grant}
    assert ids(client, section="all") == {grant, contract}
    detail = client.get(f"/documents/{grant}").json()
    assert detail["state"] == "active" and detail["proposal"]["kpi_due"] is None


def test_review_saves_funding_source_and_project_fields(client, login):
    login()
    grant = new_grant(client)
    response = client.put(f"/documents/{grant}/metadata", json=review())
    assert response.status_code == 200, response.text
    doc = response.json()
    assert (doc["funding_source"], doc["funding_type"]) == ("faculty_income", "internal")
    assert doc["proposal"]["research_area"] == "เทคโนโลยีสมมติ"
    assert [e["event_type"] for e in doc["events"]] == ["approved"]
    assert doc["events"][0]["memo_ref"] == "อว 0000.00/1"
    # FF counts as internal; an outside funder is external.
    ff = client.put(f"/documents/{grant}/metadata", json=review(funding_source="ff")).json()
    assert ff["funding_type"] == "internal" and len(ff["events"]) == 1
    outside = review(funding_source="external", funder_name="สกสว.")
    outside = client.put(f"/documents/{grant}/metadata", json=outside).json()
    assert outside["funding_type"] == "external"
    # Neither a source nor a type: refused. Proposal fields on a contract: refused.
    missing = review(funding_source=None)
    assert client.put(f"/documents/{grant}/metadata", json=missing).status_code == 422
    contract = upload(client, make_pdf()).json()["id"]
    wrong = review(kind="contract", funding_type="internal")
    assert client.put(f"/documents/{contract}/metadata", json=wrong).status_code == 422


def test_timeline_title_change_cancel_and_close(client, login):
    login()
    grant = new_grant(client)
    client.put(f"/documents/{grant}/metadata", json=review())

    renamed = paper(client, grant, "title_change", new_title="หัวข้อใหม่หลังเปลี่ยนชื่อ")
    assert renamed["title"] == "หัวข้อใหม่หลังเปลี่ยนชื่อ"
    change = renamed["events"][-1]
    assert change["details"]["old_title"] == TITLE and change["paper_purpose"] == "paper"
    assert ids(client, section="proposals", q="ทดสอบทุนพัฒนา") == {grant}  # old title found
    assert client.get(f"/documents/{grant}/file", params={"paper": 1}).status_code == 200

    event_id = change["id"]
    patched = client.patch(
        f"/documents/{grant}/events/{event_id}",
        json={"event_on": "2026-03-01", "memo_ref": "อว 0000.00/9", "note": "ตามมติ"},
    ).json()
    edited = next(e for e in patched["events"] if e["id"] == event_id)
    assert edited["event_on"] == "2026-03-01" and edited["details"]["note"] == "ตามมติ"

    cancelled = client.post(
        f"/documents/{grant}/cancel",
        json={"cancelled_on": "2026-04-01", "cancel_reason": "ไม่ทันปีงบประมาณ"},
    ).json()
    assert cancelled["state"] == "cancelled" and cancelled["events"][-1]["event_type"] == "cancel"
    assert client.post(f"/documents/{grant}/close", json={}).status_code == 409
    assert ids(client, section="proposals", state=["cancelled"]) == {grant}

    reopened = client.post(f"/documents/{grant}/reopen").json()
    assert reopened["state"] == "active" and reopened["cancelled_at"] is None
    closed = client.post(
        f"/documents/{grant}/close",
        json={"closed_on": "2026-08-04", "kpi_result": "ส่งข้อเสนอแล้ว", "spent_total": "19900"},
    ).json()
    assert closed["state"] == "closed" and closed["proposal"]["kpi_result"] == "ส่งข้อเสนอแล้ว"
    # Ordered by the memos' dates: the close (dated August) comes before today's reopen.
    kinds = [e["event_type"] for e in closed["events"]]
    assert kinds == ["approved", "title_change", "cancel", "close", "reopen"]
    # Contracts have no timeline.
    contract = upload(client, make_pdf()).json()["id"]
    files = {"file": ("x.pdf", make_pdf(), "application/pdf")}
    no = client.post(f"/documents/{contract}/papers", files=files, data={"paper_type": "close"})
    assert no.status_code == 409


def test_filters_facets_and_report(client, login):
    login()
    late, fresh = new_grant(client), new_grant(client)
    client.put(f"/documents/{late}/metadata", json=review())
    later = review(title="อีกโครงการหนึ่ง", funding_source="nu_income")
    later["people"][0]["unit"] = "ภาควิชาอื่น"
    client.put(f"/documents/{fresh}/metadata", json=later)
    with new_session() as db:  # the first one: an older grant, past its KPI due date
        db.execute(update(Document).where(Document.id == late).values(fiscal_year=2025))
        db.execute(
            update(ProposalProject)
            .where(ProposalProject.document_id == late)
            .values(kpi_due=date(2025, 9, 1))
        )
        db.commit()

    assert ids(client, section="proposals", state=["overdue"]) == {late}
    assert ids(client, section="proposals", state=["active"]) == {late, fresh}
    assert ids(client, section="proposals", funding_source=["nu_income"]) == {fresh}
    assert ids(client, section="proposals", department=["ภาควิชาสมมติ"]) == {late}
    page = client.get("/documents", params={"section": "proposals", "with_facets": True}).json()
    states = {f["value"]: f["count"] for f in page["facets"]["state"]}
    assert states == {"overdue": 1, "active": 1}
    row = next(i for i in page["items"] if i["id"] == late)
    assert row["state"] == "overdue" and row["department"] == "ภาควิชาสมมติ"

    report = client.get("/reports/proposals").json()
    years = {r["fiscal_year"]: r for r in report["by_year"]}
    assert years[2025]["overdue"] == 1 and years[2026]["active"] == 1
    assert years[2026]["budget"] == 20000.0
    assert {d["department"] for d in report["by_department"]} == {"ภาควิชาสมมติ", "ภาควิชาอื่น"}


def test_closing_with_its_memo_is_one_timeline_entry(client, login):
    login()
    grant = new_grant(client)
    client.put(f"/documents/{grant}/metadata", json=review())
    paper(client, grant, "close")  # the memo first, as the close form uploads it
    closed = client.post(
        f"/documents/{grant}/close", json={"closed_on": "2026-08-04", "closure_ref": "อว 1/2"}
    ).json()
    closes = [e for e in closed["events"] if e["event_type"] == "close"]
    assert len(closes) == 1
    assert closes[0]["event_on"] == "2026-08-04" and closes[0]["paper_purpose"] == "closure"
