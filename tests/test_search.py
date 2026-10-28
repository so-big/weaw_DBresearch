"""Search: space-insensitive Thai text, filters, facets, sorting, snippets. Fake values only."""

from datetime import UTC, datetime

from sqlalchemy import update

from dbresearch import search_text
from dbresearch.db import new_session
from dbresearch.models import Document, DocumentPage
from tests.conftest import make_pdf, needs_db
from tests.test_review import category, metadata

pytestmark = needs_db


def create(client, **fields) -> str:
    doc_id = client.post(
        "/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}
    ).json()["id"]
    response = client.put(f"/documents/{doc_id}/metadata", json=metadata(**fields))
    assert response.status_code == 200, response.text
    return doc_id


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_text_search_ignores_spaces_case_and_finds_ocr_text(client, login):
    login()
    a = create(
        client,
        title="การพัฒนาระบบจัดการข้อมูลนิสิต",
        reference_no="R2568E002",
        categories=[],
        people=[],
        tags=[],
    )
    b = create(
        client,
        title="Climate Change Study",
        reference_no="R2568A010",
        kind="grant",
        funding_type="external",
        categories=[],
        people=[],
        tags=[],
    )
    with new_session() as db:  # OCR text on the current version of b
        document = db.get(Document, b)
        db.add(
            DocumentPage(
                version_id=document.current_version_id,
                page_no=1,
                text="ผู้ให้ทุนตกลงให้ทุนอุดหนุนการวิจัย ในวงเงิน 290,000 บาท",
            )
        )
        db.flush()
        document.search_text = search_text.build(db, document)
        db.commit()

    assert ids(client.get("/documents", params={"q": "การพัฒนา ระบบ"})) == [a]
    assert ids(client.get("/documents", params={"q": "r2568e002"})) == [a]
    assert ids(client.get("/documents", params={"q": "climate  change"})) == [b]
    found = client.get("/documents", params={"q": "ทุนอุดหนุน การวิจัย"}).json()["items"]
    assert [i["id"] for i in found] == [b]
    assert "[[ทุนอุดหนุนการวิจัย]]" in found[0]["snippet"]
    assert ids(client.get("/documents", params={"q": "%"})) == []  # LIKE wildcards are literal


def test_filters_and_category_logic(client, login):
    me = login()
    plan = category("research_type", "เพื่อการวางแผนพัฒนา")
    fix = category("research_type", "เพื่อแก้ปัญหา")
    staff = category("research_group", "บุคลากร")
    a = create(
        client,
        title="A",
        reference_no="R2568E001",
        tags=[{"name": "exchange"}],
        categories=[{"category_id": plan}, {"category_id": staff}],
    )
    b = create(
        client,
        title="B",
        reference_no="R2567A003",
        kind="grant",
        funding_type="external",
        document_date="2024-03-01",
        categories=[{"category_id": fix}],
        tags=[],
        people=[{"name_th": "สมปอง ทดสอบ", "role": "owner"}],
    )

    get = lambda **p: set(ids(client.get("/documents", params=p)))  # noqa: E731
    assert get(funding_type="external") == {b}
    assert get(fiscal_year=2024) == {b} and get(fiscal_year=2025) == {a}
    assert get(fiscal_year=[2024, 2025]) == {a, b}  # several values = any of them
    assert get(kind=["grant", "contract"], funding_type=["external"]) == {b}
    assert get(category=[plan, fix]) == {a, b}  # OR within one group
    assert get(category=[plan, staff]) == {a}  # AND across groups
    assert get(category=[fix, staff]) == set()
    assert get(tag="Exchange") == {a}
    assert get(person="สมปอง") == {b}
    assert get(ref_series="A") == {b} and get(ref_year_be=2568) == {a}
    assert get(mine=True) == {a, b} and me

    with new_session() as db:  # deleted documents never show up
        db.execute(update(Document).where(Document.id == a).values(deleted_at=datetime.now(UTC)))
        db.commit()
    assert get() == {b}


def test_reference_sort_pagination_and_facets(client, login):
    login()
    for ref in ("R2568E010", "R2568E002", "R2567E005"):
        create(client, title=ref, reference_no=ref, categories=[], people=[], tags=[])
    page = client.get("/documents", params={"sort": "reference", "page_size": 2}).json()
    assert [i["reference_no"] for i in page["items"]] == ["R2568E002", "R2568E010"]
    assert page["total"] == 3
    second = client.get("/documents", params={"sort": "reference", "page_size": 2, "page": 2})
    assert [i["reference_no"] for i in second.json()["items"]] == ["R2567E005"]

    facets = client.get("/documents", params={"with_facets": True}).json()["facets"]
    assert facets["status"] == [{"value": "ready", "count": 3}]
    assert {f["value"]: f["count"] for f in facets["fiscal_year"]} == {2025: 3}


def test_facets_leave_out_their_own_filter(client, login):
    """Ticking one year must still show the other years (and their counts) to add."""
    login()
    plan = category("research_type", "เพื่อการวางแผนพัฒนา")
    fix = category("research_type", "เพื่อแก้ปัญหา")
    for ref, day, cat, kind in (
        ("R2567E001", "2024-03-01", plan, "contract"),
        ("R2568E001", "2025-03-01", fix, "contract"),
        ("R2568E002", "2025-04-01", fix, "grant"),
    ):
        create(
            client,
            reference_no=ref,
            document_date=day,
            kind=kind,
            categories=[{"category_id": cat}],
            people=[],
            tags=[],
        )

    params = {"with_facets": True, "fiscal_year": 2025, "category": fix}
    body = client.get("/documents", params=params).json()
    assert body["total"] == 2
    years = {f["value"]: f["count"] for f in body["facets"]["fiscal_year"]}
    assert years == {2025: 2}  # the 2024 document isn't `fix`, so the category filter drops it
    kinds = {f["value"]: f["count"] for f in body["facets"]["kind"]}
    assert kinds == {"contract": 1, "grant": 1}  # other groups' filters still apply
    by_name = {f["name"]: f["count"] for f in body["facets"]["categories"]}
    assert by_name == {"เพื่อแก้ปัญหา": 2}  # own group ignores `fix`, but 2024 is filtered out

    body = client.get("/documents", params={"with_facets": True, "fiscal_year": 2025}).json()
    years = {f["value"]: f["count"] for f in body["facets"]["fiscal_year"]}
    assert years == {2024: 1, 2025: 2}


def test_pickers(client, login):
    login()
    create(
        client,
        people=[{"prefix_th": "ดร.", "name_th": "สมใจ ทดลอง", "role": "owner"}],
        categories=[],
        tags=[],
    )
    groups = {g["key"]: g for g in client.get("/categories").json()}
    assert len(groups["research_group"]["options"]) == 7 and not groups["research_type"]["multi"]
    people = client.get("/people", params={"q": "สมใจทดลอง"}).json()
    assert [(p["prefix_th"], p["name_th"]) for p in people] == [("ดร.", "สมใจ ทดลอง")]
