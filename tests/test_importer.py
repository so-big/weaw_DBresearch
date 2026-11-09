"""Bulk import of proposal-development papers (DESIGN §11). Invented names and titles."""

from pathlib import Path

import pytest
from sqlalchemy import select

from dbresearch.importer import Paper, apply_plan, build_plan, plan_from_json, plan_to_json
from tests.conftest import HAS_DB, make_pdf

OWNER = "ผศ.ดร. สมมติ ทดสอบดี"


def paper(file, kind, title=None, owner=OWNER, year=2025, sha=None, **fields) -> Paper:
    values = {"title": title, "owner": owner, "fiscal_year": year, **fields}
    return Paper(file, sha or file, kind, {k: v for k, v in values.items() if v is not None})


# ───────────── Grouping (no DB) ─────────────
def test_papers_join_their_project_by_title_not_folder():
    plan = build_plan(
        [
            paper("2568/1 request.pdf", "request", "ระบบตัวอย่างสำหรับทดสอบการนำเข้า"),
            paper("2568/2 request.pdf", "request", "เครื่องมือวัดสมมติแบบใหม่", owner="ดร.อื่น ทดสอบ"),
            # Filed a year later, OCR dropped a letter: still the first project.
            paper("2569/3 close.pdf", "close", "ระบบตัวอยางสำหรับทดสอบการนำเข้า", year=None),
            paper("2569/4 cancel.pdf", "cancel", "เครื่องมือวัดสมมติแบบใหม่", owner="ดร.อื่น ทดสอบ"),
        ]
    )
    first, second = plan.projects
    assert [p.file for p in first.papers] == ["2569/3 close.pdf"]
    assert [p.file for p in second.papers] == ["2569/4 cancel.pdf"]
    assert not first.notes and not second.notes


def test_duplicates_resubmissions_and_title_changes():
    plan = build_plan(
        [
            paper("a/5 request.pdf", "request", "ระบบเดิมสำหรับทดสอบการนำเข้า", sha="x"),
            paper("a/5 request copy.pdf", "request", "ระบบเดิมสำหรับทดสอบการนำเข้า", sha="x"),
            paper("a/5 (แก้ไข) request.pdf", "request", "ระบบเดิมสำหรับทดสอบการนำเข้า"),
            paper(
                "b/6 change.pdf",
                "title_change",
                "ระบบเดิมสำหรับทดสอบการนำเข้า",
                new_title="หัวข้อใหม่ที่ไม่เหมือนเดิมเลย",
            ),
            # The closing names the project by its new title.
            paper("b/7 close.pdf", "close", "หัวข้อใหม่ที่ไม่เหมือนเดิมเลย"),
        ]
    )
    assert plan.duplicates == [("a/5 request.pdf", "a/5 request copy.pdf")]
    (project,) = plan.projects
    assert project.request.file == "a/5 request copy.pdf"
    assert [p.file for p in project.resubmissions] == ["a/5 (แก้ไข) request.pdf"]
    assert [p.kind for p in project.papers] == ["title_change", "close"]


def test_same_title_reapplied_goes_by_year_and_unmatched_papers_are_flagged():
    plan = build_plan(
        [
            paper("1.pdf", "request", "หัวข้อที่ขอซ้ำอีกปีหนึ่งได้", year=2023),
            paper("2.pdf", "cancel", "หัวข้อที่ขอซ้ำอีกปีหนึ่งได้", year=2023),
            paper("3.pdf", "request", "หัวข้อที่ขอซ้ำอีกปีหนึ่งได้", year=2024),
            paper("4.pdf", "close", "หัวข้อที่ขอซ้ำอีกปีหนึ่งได้", year=2024, owner=None),
            paper("5.pdf", "close", "ไม่มีคำขอในแฟ้มนี้เลยจริงๆ", owner="ดร.คนอื่น ไม่มีคำขอ"),
            paper("6.pdf", "programme", None, owner=None),
            paper("7.pdf", "request", "งานสัมมนาที่อ่านเป็นคำขอผิด"),  # forced to 'other'
        ],
        other={"7.pdf"},
    )
    cancelled, closed, orphan = plan.projects
    assert [p.file for p in cancelled.papers] == ["2.pdf"]
    assert [p.file for p in closed.papers] == ["4.pdf"]
    assert orphan.request is None and orphan.notes == ["no request paper found"]
    assert sorted(p.file for p in plan.programme) == ["6.pdf", "7.pdf"]


def test_unreadable_title_matches_by_researcher_and_year():
    plan = build_plan(
        [
            paper("1.pdf", "request", "หัวข้อปีแรกของนักวิจัยคนนี้", year=2023),
            paper("2.pdf", "request", "หัวข้อปีที่สองของนักวิจัยคนนี้", year=2024),
            paper("3.pdf", "close", None, year=2024),
        ]
    )
    assert [p.file for p in plan.projects[1].papers] == ["3.pdf"]
    assert "researcher and year" in plan.projects[1].notes[0]


def test_plan_round_trips_through_json():
    plan = build_plan([paper("1.pdf", "request", "หัวข้อสำหรับทดสอบไฟล์แผน")])
    again = plan_from_json(plan_to_json(plan))
    assert again.projects[0].request == plan.projects[0].request


# ───────────── Apply (DB + encrypted store) ─────────────
@pytest.mark.skipif(not HAS_DB, reason="needs the compose stack (DATABASE_URL)")
def test_apply_creates_projects_in_review_and_is_safe_to_rerun(tmp_path: Path, make_user):
    import hashlib

    from dbresearch.db import new_session
    from dbresearch.models import (
        AuditEvent,
        Document,
        DocumentPerson,
        DocumentVersion,
        Job,
        ProjectEvent,
        ProposalProject,
        User,
    )

    def write(name: str) -> str:
        data = make_pdf()
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    title = "ระบบตัวอย่างสำหรับทดสอบการนำเข้า"
    papers = [
        paper(
            "2569/req.pdf",
            "request",
            title,
            sha=write("2569/req.pdf"),
            budget_total="20000",
            funding_source="faculty_income",
            department="ภาควิชาสมมติ",
            kpi_target="จัดทำข้อเสนอ",
            kpi_due="2026-09-01",
            document_date="2025-12-03",
            memo_ref="อว 0000.00/1",
        ),
        paper(
            "2569/close.pdf",
            "close",
            title,
            sha=write("2569/close.pdf"),
            document_date="2026-08-04",
            kpi_result="ข้อเสนอสำหรับทุนภายนอก",
        ),
        paper("2569/cancel.pdf", "cancel", "อีกโครงการที่ยกเลิกไปแล้ว", sha=write("2569/cancel.pdf")),
        paper("call.pdf", "programme", None, owner=None, sha=write("call.pdf")),
    ]
    user_id, _, _ = make_user()
    with new_session() as db:
        email = db.get(User, user_id).email
    plan = build_plan(papers)

    first = apply_plan(plan, tmp_path, email)
    assert first == {"projects": 2, "programme": 1, "files": 4, "skipped": 0, "failed": 0}
    with new_session() as db:
        project = db.scalar(select(Document).where(Document.title == title))
        assert project.kind == "proposal_dev" and project.status == "processing"
        assert (project.funding_source, project.funding_type) == ("faculty_income", "internal")
        assert project.closed_on.isoformat() == "2026-08-04" and project.cancelled_at is None
        details = db.get(ProposalProject, project.id)
        assert (details.kpi_target, details.kpi_result) == ("จัดทำข้อเสนอ", "ข้อเสนอสำหรับทุนภายนอก")
        assert details.request_ref == "อว 0000.00/1"
        events = db.scalars(
            select(ProjectEvent.event_type).where(ProjectEvent.document_id == project.id)
        ).all()
        assert sorted(events) == ["approved", "close"]
        purposes = db.scalars(
            select(DocumentVersion.purpose).where(DocumentVersion.document_id == project.id)
        ).all()
        assert sorted(purposes) == ["closure", "main"]
        owner = db.scalar(select(DocumentPerson).where(DocumentPerson.document_id == project.id))
        assert owner.role == "owner" and owner.unit == "ภาควิชาสมมติ"
        cancelled = db.scalar(select(Document).where(Document.title == "อีกโครงการที่ยกเลิกไปแล้ว"))
        assert cancelled.cancelled_at is not None and cancelled.closed_at is None
        assert db.scalar(select(Document).where(Document.kind == "other")) is not None
        assert len(db.scalars(select(Job)).all()) == 4  # every file queued for full OCR
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "document.import"))

    again = apply_plan(plan, tmp_path, email)
    assert again == {"projects": 0, "programme": 0, "files": 0, "skipped": 4, "failed": 0}
