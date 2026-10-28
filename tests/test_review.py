"""Review / metadata endpoint: confirm suggestions, edit later, rights and conflicts."""

from sqlalchemy import select

from dbresearch.db import new_session
from dbresearch.models import AuditEvent, Category, CategoryGroup, Document, Job, UserRole
from tests.conftest import make_pdf, needs_db

pytestmark = needs_db


def upload(client) -> str:
    response = client.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def category(group_key: str, name: str) -> str:
    with new_session() as db:
        return str(
            db.scalar(
                select(Category.id)
                .join(CategoryGroup, Category.group_id == CategoryGroup.id)
                .where(CategoryGroup.key == group_key, Category.name_th == name)
            )
        )


def metadata(**overrides) -> dict:
    body = {
        "title": "การพัฒนาระบบทดสอบ",
        "title_en": "Test System",
        "kind": "grant",
        "funding_type": "internal",
        "reference_no": "r2568 e001",
        "document_date": "2025-09-01",
        "budget_total": "10000.00",
        "categories": [
            {"category_id": category("research_type", "เพื่อการวางแผนพัฒนา"), "source": "auto"},
            {"category_id": category("research_group", "บุคลากร"), "source": "manual"},
        ],
        "tags": [{"name": "Exchange ", "source": "manual"}, {"name": "exchange"}],
        "people": [
            {"prefix_th": "นางสาว", "name_th": "สมหญิง รักงาน", "role": "owner", "share_pct": 80},
            {"name_th": "สมชาย ใจดี", "role": "co_investigator", "share_pct": 20},
        ],
        "budget_lines": [
            {"line_type": "item", "group_label": "หมวด 1", "label": "ค่าตอบแทน", "amount": "1000"},
        ],
    }
    body.update(overrides)
    return body


def test_confirm_makes_document_ready_and_searchable(client, login):
    login()
    doc_id = upload(client)
    response = client.put(f"/documents/{doc_id}/metadata", json=metadata())
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["status"] == "ready" and doc["reference_no"] == "R2568E001"
    assert doc["fiscal_year"] == 2025 and doc["fiscal_year_be"] == 2568  # from document_date
    assert {(c["group_key"], c["source"]) for c in doc["categories"]} == {
        ("research_type", "auto"),
        ("research_group", "manual"),
    }
    assert doc["tags"] == [{"name": "Exchange", "source": "manual"}]  # deduplicated
    assert [(p["name_th"], p["role"]) for p in doc["people"]] == [
        ("สมหญิง รักงาน", "owner"),
        ("สมชาย ใจดี", "co_investigator"),
    ]
    assert doc["budget_lines"][0]["label"] == "ค่าตอบแทน"
    with new_session() as db:
        document = db.get(Document, doc["id"])
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "document.confirm"))
    assert "การพัฒนาระบบทดสอบ" in document.search_text and "สมหญิงรักงาน" in document.search_text
    assert "title" in audit.details["fields"]
    assert "การพัฒนา" not in str(audit.details)  # audit records field names, never values

    # A later edit keeps budget lines when they are not sent, and is audited as an update.
    again = client.put(f"/documents/{doc_id}/metadata", json=metadata(budget_lines=None))
    assert again.json()["budget_lines"] and again.status_code == 200


def test_single_choice_group_and_unknown_category_are_rejected(client, login):
    login()
    doc_id = upload(client)
    two = [{"category_id": category("research_type", n)} for n in ("เพื่อแก้ปัญหา", "เพื่อการวางแผนพัฒนา")]
    assert (
        client.put(f"/documents/{doc_id}/metadata", json=metadata(categories=two)).status_code
        == 422
    )
    bogus = [{"category_id": "00000000-0000-0000-0000-000000000000"}]
    assert (
        client.put(f"/documents/{doc_id}/metadata", json=metadata(categories=bogus)).status_code
        == 422
    )
    assert client.put(f"/documents/{doc_id}/metadata", json=metadata(kind=None)).status_code == 422


def test_contract_number_conflict_points_to_the_existing_document(client, login):
    login()
    first, second = upload(client), upload(client)
    client.put(f"/documents/{first}/metadata", json=metadata())
    response = client.put(f"/documents/{second}/metadata", json=metadata())
    assert response.status_code == 409 and response.json()["document_id"] == first


def test_only_uploader_or_admin_can_edit(client, login):
    login()
    doc_id = upload(client)
    login(UserRole.USER)
    assert client.put(f"/documents/{doc_id}/metadata", json=metadata()).status_code == 403
    assert client.post(f"/documents/{doc_id}/reprocess").status_code == 403
    login(UserRole.ADMIN)
    assert client.put(f"/documents/{doc_id}/metadata", json=metadata()).status_code == 200


def test_reprocess_queues_ocr_again(client, login):
    login()
    doc_id = upload(client)
    assert client.post(f"/documents/{doc_id}/reprocess").status_code == 202
    with new_session() as db:
        assert len(db.scalars(select(Job)).all()) == 2
    review = client.get(f"/documents/{doc_id}/autofill").json()
    assert review["ocr_status"] == "pending" and review["suggestions"] is None
