"""The researcher page: one person's live documents in both sections, with totals.
Invented values only."""

from decimal import Decimal

from tests.conftest import make_pdf, needs_db
from tests.test_proposals_api import new_grant, review
from tests.test_review import metadata

pytestmark = needs_db

NAME = "สมหญิง รักงาน"


def contract(client, ref: str, *, role="owner", share=None, **fields) -> str:
    doc_id = client.post(
        "/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}
    ).json()["id"]
    people = [{"prefix_th": "นางสาว", "name_th": NAME, "role": role, "share_pct": share}]
    if role != "owner":
        people.append({"name_th": "เจ้าของ สมมติ", "role": "owner"})
    body = metadata(reference_no=ref, people=people, categories=[], tags=[], **fields)
    response = client.put(f"/documents/{doc_id}/metadata", json=body)
    assert response.status_code == 200, response.text
    return doc_id


def proposal(client, **fields) -> str:
    doc_id = new_grant(client)
    response = client.put(f"/documents/{doc_id}/metadata", json=review(**fields))
    assert response.status_code == 200, response.text
    return doc_id


def person_id(client, doc_id: str, name: str = NAME) -> str:
    detail = client.get(f"/documents/{doc_id}").json()
    return next(p["id"] for p in detail["people"] if p["name_th"] == name)


def test_page_lists_both_sections_with_totals(client, login):
    login()
    c1 = contract(
        client, "R2568E001", budget_total="10000", document_date="2025-09-01", share=80
    )  # FY 2025
    c2 = contract(
        client,
        "R2568E002",
        role="co_investigator",
        budget_total="5000",
        document_date="2024-01-10",
        funding_type="external",
        funding_source="external",
    )  # FY 2024, as a team member
    pr = proposal(
        client,
        budget_total="20000",
        people=[{"name_th": NAME, "role": "owner", "unit": "ภาควิชาสมมติ"}],
    )  # FY 2026
    pid = person_id(client, c1)

    page = client.get(f"/people/{pid}")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["person"]["name_th"] == NAME
    assert body["units"] == ["ภาควิชาสมมติ"]
    assert [d["id"] for d in body["contracts"]] == [c1, c2]  # newest fiscal year first
    assert [d["id"] for d in body["proposals"]] == [pr]
    first = body["contracts"][0]
    assert first["role"] == "owner" and Decimal(first["share_pct"]) == 80
    assert first["project"] == "open" and first["reference_no"] == "R2568E001"
    assert body["contracts"][1]["role"] == "co_investigator"
    assert body["proposals"][0]["state"] == "active"
    assert body["proposals"][0]["request_ref"] == "อว 0000.00/1"

    assert body["total"]["count"] == 3 and Decimal(body["total"]["budget"]) == 35000
    assert (body["as_owner"], body["as_member"]) == (2, 1)
    years = {y["fiscal_year"]: (y["count"], Decimal(y["budget"])) for y in body["by_year"]}
    assert years == {2026: (1, 20000), 2025: (1, 10000), 2024: (1, 5000)}
    assert [y["fiscal_year"] for y in body["by_year"]] == [2026, 2025, 2024]
    assert body["by_year"][0]["fiscal_year_be"] == 2569
    sources = {s["funding_source"]: (s["count"], Decimal(s["budget"])) for s in body["by_source"]}
    assert sources["external"] == (1, 5000) and sources["faculty_income"] == (1, 20000)


def test_trashed_documents_are_left_out(client, login):
    login()
    keep = contract(client, "R2568E001", budget_total="10000")
    gone = contract(client, "R2568E002", budget_total="7000")
    pid = person_id(client, keep)
    assert client.delete(f"/documents/{gone}").status_code == 204
    body = client.get(f"/people/{pid}").json()
    assert [d["id"] for d in body["contracts"]] == [keep]
    assert body["total"]["count"] == 1 and Decimal(body["total"]["budget"]) == 10000


def test_one_document_counts_once_with_two_roles(client, login):
    login()
    doc_id = contract(client, "R2568E001", budget_total="10000")
    body = metadata(
        reference_no="R2568E001",
        budget_total="10000",
        categories=[],
        tags=[],
        people=[
            {"name_th": NAME, "role": "owner"},
            {"name_th": NAME, "role": "co_investigator", "share_pct": 50},
        ],
    )
    assert client.put(f"/documents/{doc_id}/metadata", json=body).status_code == 200
    pid = person_id(client, doc_id)
    page = client.get(f"/people/{pid}").json()
    assert len(page["contracts"]) == 1 and page["contracts"][0]["role"] == "owner"
    assert page["total"]["count"] == 1 and Decimal(page["total"]["budget"]) == 10000


def test_list_rows_link_owners(client, login):
    login()
    doc_id = contract(client, "R2568E001")
    pid = person_id(client, doc_id)
    row = client.get("/documents").json()["items"][0]
    assert row["owners"] == [f"นางสาว{NAME}"]
    assert row["owner_people"] == [{"id": pid, "name": f"นางสาว{NAME}"}]


def test_unknown_person_is_404_and_login_is_required(client, login):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/people/{missing}").status_code == 401
    login()
    assert client.get(f"/people/{missing}").status_code == 404


def test_other_rows_with_the_same_name_are_suggested(client, login):
    login()
    first = contract(client, "R2568E001")
    second = client.post(
        "/documents", files={"file": ("b.pdf", make_pdf(), "application/pdf")}
    ).json()["id"]
    people = [{"name_th": "สมหญิงรักงาน", "role": "owner"}]  # no space: its own row
    body = metadata(reference_no="R2568E002", people=people, categories=[], tags=[])
    assert client.put(f"/documents/{second}/metadata", json=body).status_code == 200
    a, b = person_id(client, first), person_id(client, second, "สมหญิงรักงาน")
    assert a != b
    assert [p["id"] for p in client.get(f"/people/{a}").json()["similar"]] == [b]
    assert [p["id"] for p in client.get(f"/people/{b}").json()["similar"]] == [a]
