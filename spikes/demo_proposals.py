"""Seed a few FAKE proposal-development grants on the demo (no real papers on the demo).

    docker compose exec -T worker python - < spikes/demo_proposals.py

Every title starts with "[ตัวอย่าง]"; people and numbers are invented. The "scans" are
blank pages with an English label. Safe to re-run: existing demo grants are skipped.
"""

import io
from datetime import date

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from dbresearch import projects
from dbresearch.db import new_session
from dbresearch.documents import close_project, store_version
from dbresearch.models import (
    DocKind,
    DocStatus,
    Document,
    DocumentPerson,
    FundingSource,
    Person,
    PersonRole,
    ProjectEventType,
    ProposalOutcome,
    ProposalProject,
    User,
    UserRole,
    VersionPurpose,
)

MARK = "[ตัวอย่าง]"


def pdf(label: str) -> io.BytesIO:
    image = Image.new("L", (1240, 1754), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    draw.text((120, 160), "DEMO ONLY - not a real memo", fill=0, font=font)
    draw.text((120, 240), label, fill=0, font=font)
    out = io.BytesIO()
    image.save(out, "PDF", resolution=150)
    out.seek(0)
    return out


GRANTS = [
    {
        "title": f"{MARK} ระบบตรวจวัดคุณภาพอากาศภายในอาคารแบบไร้สาย",
        "owner": ("ผศ.ดร.", "สมมติ ใจดี"),
        "unit": "ภาควิชาวิศวกรรมเครื่องกล",
        "year": 2027,
        "area": "เทคโนโลยีพลังงาน",
        "due": date(2027, 9, 1),
        "state": "active",
    },
    {
        "title": f"{MARK} การผลิตวัสดุชีวภาพจากของเหลือทิ้งทางการเกษตร",
        "owner": ("รศ.ดร.", "ตัวอย่าง ทดลองดี"),
        "unit": "ภาควิชาวิศวกรรมอุตสาหการ",
        "year": 2025,
        "area": "วัสดุและเศรษฐกิจหมุนเวียน",
        "due": date(2025, 9, 1),
        "state": "closed",
    },
    {
        "title": f"{MARK} แบบจำลองปัญญาประดิษฐ์ทำนายความเสียหายของโครงสร้าง",
        "owner": ("ดร.", "สาธิต ระบบงาน"),
        "unit": "ภาควิชาวิศวกรรมโยธา",
        "year": 2025,
        "area": "โครงสร้างพื้นฐาน",
        "due": date(2025, 8, 1),
        "state": "overdue",
    },
    {
        "title": f"{MARK} อุปกรณ์วิเคราะห์การลงน้ำหนักเท้าสำหรับกายภาพบำบัด",
        "owner": ("ดร.", "ทดสอบ ใช้งานได้"),
        "unit": "ภาควิชาวิศวกรรมไฟฟ้าและคอมพิวเตอร์",
        "year": 2024,
        "area": None,
        "due": date(2024, 9, 1),
        "state": "cancelled",
    },
]


with new_session() as db:
    admin = db.scalar(select(User).where(User.role == UserRole.ADMIN).limit(1))
    for g in GRANTS:
        if db.scalar(select(Document.id).where(Document.title == g["title"])):
            print("exists:", g["title"])
            continue
        version = store_version(
            db, admin, pdf(f"request {g['year']}"), "demo-request.pdf", kind=DocKind.PROPOSAL_DEV
        )
        doc = db.get(Document, version.document_id)
        doc.title = g["title"]
        doc.fiscal_year = g["year"]
        doc.budget_total = 20000
        doc.document_date = date(g["year"] - 1, 12, 3)
        doc.effective_from = date(g["year"] - 1, 12, 15)
        doc.effective_to = date(g["year"], 9, 30)
        doc.status = DocStatus.READY
        projects.set_funding(doc, FundingSource.FACULTY_INCOME, None)
        person = Person(prefix_th=g["owner"][0], name_th=g["owner"][1])
        db.add(person)
        db.flush()
        db.add(
            DocumentPerson(
                document_id=doc.id, person_id=person.id, role=PersonRole.OWNER, unit=g["unit"]
            )
        )
        details = ProposalProject(
            document_id=doc.id,
            request_ref="อว 0000.00/0",
            research_area=g["area"],
            kpi_target="ข้อเสนอโครงการสำหรับขอทุนวิจัยภายนอก และ Impact Pathway",
            kpi_due=g["due"],
        )
        db.add(details)
        projects.add_event(
            db,
            admin,
            doc,
            ProjectEventType.APPROVED,
            version=version,
            event_on=doc.document_date,
            memo_ref="อว 0000.00/0",
        )
        if g["state"] == "closed":
            paper = store_version(
                db,
                admin,
                pdf("closing"),
                "demo-close.pdf",
                document=doc,
                purpose=VersionPurpose.CLOSURE,
            )
            details.kpi_result = "ข้อเสนอสำหรับการขอทุนวิจัยภายนอก พร้อมสัญญาทุนวิจัย"
            details.spent_total = 19900
            details.outcome = ProposalOutcome.WON
            details.outcome_funder = "หน่วยงานสมมติ"
            close_project(
                db,
                admin,
                doc,
                closed_on=date(2025, 8, 4),
                closure_ref="อว 0000.00/1",
                closure_note=None,
                ip=None,
            )
            projects.add_event(
                db,
                admin,
                doc,
                ProjectEventType.CLOSE,
                version=paper,
                event_on=date(2025, 8, 4),
                memo_ref="อว 0000.00/1",
                details={"kpi_result": details.kpi_result},
            )
        if g["state"] == "cancelled":
            paper = store_version(
                db,
                admin,
                pdf("cancel"),
                "demo-cancel.pdf",
                document=doc,
                purpose=VersionPurpose.PAPER,
            )
            reason = "ต้องรอผลการทดลองจากห้องปฏิบัติการ ไม่ทันปีงบประมาณ"
            projects.cancel_project(
                db,
                admin,
                doc,
                cancelled_on=date(2024, 9, 20),
                cancel_ref="อว 0000.00/2",
                cancel_reason=reason,
                ip=None,
            )
            projects.add_event(
                db,
                admin,
                doc,
                ProjectEventType.CANCEL,
                version=paper,
                event_on=date(2024, 9, 20),
                memo_ref="อว 0000.00/2",
                details={"reason": reason},
            )
        db.commit()  # status is READY, so the queued OCR jobs only refresh the search text
        print("created:", g["title"])
