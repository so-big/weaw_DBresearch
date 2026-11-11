"""Spreadsheet export of search results and the proposal report (xlsx or csv).

Metadata only (never OCR text, snippets, hashes or internal ids), built in memory. Text cells
that a spreadsheet could read as a formula get a leading apostrophe."""

import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch import search
from dbresearch.models import (
    Category,
    CategoryGroup,
    DocKind,
    DocStatus,
    Document,
    DocumentCategory,
    FundingSource,
    FundingType,
    ProposalOutcome,
    ProposalProject,
    User,
)

MAX_ROWS = 5000
BE = 543
FORMATS = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}

# Thai labels, the same wording the web app shows (web/src/lib/format.js).
STATUS = {
    DocStatus.PROCESSING: "กำลังอ่านเอกสาร",
    DocStatus.NEEDS_REVIEW: "รอตรวจสอบ",
    DocStatus.READY: "พร้อมใช้งาน",
    DocStatus.FAILED: "อ่านไม่สำเร็จ",
}
KIND = {
    DocKind.CONTRACT: "สัญญา",
    DocKind.GRANT: "ทุนวิจัย",
    DocKind.PROPOSAL_DEV: "ทุนพัฒนาข้อเสนอ",
    DocKind.OTHER: "เอกสารประกอบ",
}
FUNDING_TYPE = {FundingType.INTERNAL: "ทุนภายใน", FundingType.EXTERNAL: "ทุนภายนอก"}
FUNDING_SOURCE = {
    FundingSource.FF: "งบประมาณ FF",
    FundingSource.NU_INCOME: "รายได้ ม.นเรศวร",
    FundingSource.FACULTY_INCOME: "รายได้คณะ",
    FundingSource.EXTERNAL: "แหล่งทุนภายนอก",
}
PROJECT_STATE = {
    "active": "ดำเนินการอยู่",
    "overdue": "เกินกำหนด",
    "closed": "ปิดทุนแล้ว",
    "cancelled": "ยกเลิก",
}
OUTCOME = {
    ProposalOutcome.SUBMITTED: "ยื่นข้อเสนอแล้ว",
    ProposalOutcome.WON: "ได้รับทุน",
    ProposalOutcome.NOT_WON: "ไม่ได้รับทุน",
}

CONTRACT_HEADERS = [
    "เลขที่สัญญา",
    "ชื่อเรื่อง (ไทย)",
    "ชื่อเรื่อง (อังกฤษ)",
    "ประเภทเอกสาร",
    "แหล่งทุน",
    "ประเภททุน",
    "ปีงบประมาณ (พ.ศ.)",
    "วันที่เอกสาร (พ.ศ.)",
    "งบประมาณรวม (บาท)",
    "ผู้วิจัย",
    "หมวดหมู่",
    "สถานะเอกสาร",
    "โครงการ",
    "ผู้อัปโหลด",
    "อัปโหลดเมื่อ (พ.ศ.)",
]
PROPOSAL_HEADERS = [
    "เลขรับ",
    "เลขที่บันทึกขออนุมัติ",
    "ผู้วิจัย",
    "หน่วยงาน",
    "ชื่อโครงการ",
    "ปีงบประมาณ (พ.ศ.)",
    "งบประมาณ (บาท)",
    "วันเริ่มโครงการ (พ.ศ.)",
    "วันสิ้นสุดโครงการ (พ.ศ.)",
    "กรอบงานวิจัย",
    "กำหนดส่งผลงาน (พ.ศ.)",
    "สถานะ",
    "ใช้จ่ายจริง (บาท)",
    "คงเหลือ (บาท)",
    "ผลการยื่นขอทุน",
    "แหล่งทุนภายนอก",
]
REPORT_HEADERS = [
    "ปีงบประมาณ (พ.ศ.)",
    "โครงการทั้งหมด",
    "ปิดทุนแล้ว",
    "ดำเนินการอยู่",
    "เกินกำหนด",
    "ยกเลิก",
    "งบประมาณ (บาท)",
    "ใช้จ่ายจริง (บาท)",
    "ได้รับทุนภายนอก",
]

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe(value: Any) -> Any:
    """Text a spreadsheet could run as a formula gets a leading apostrophe; other values pass."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def th_date(value: date | datetime | None) -> str | None:
    """Gregorian date → dd/mm/yyyy in พ.ศ. as text (Bangkok time for timestamps)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.astimezone(ZoneInfo("Asia/Bangkok"))
    return f"{value.day:02d}/{value.month:02d}/{value.year + BE}"


def _number(value: Decimal | float | int | None) -> float | None:
    return None if value is None else float(value)


def build_xlsx(sheet: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    workbook = Workbook(write_only=True)
    ws = workbook.create_sheet(sheet)
    ws.append(headers)
    for row in rows:
        ws.append([safe(v) for v in row])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def build_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else safe(v) for v in row])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")  # BOM: Excel reads Thai as UTF-8


def build(fmt: str, sheet: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    return build_xlsx(sheet, headers, rows) if fmt == "xlsx" else build_csv(headers, rows)


def content_disposition(name: str) -> str:
    fallback = name.encode("ascii", "ignore").decode().replace('"', "") or "export"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


def filename(name: str, fmt: str) -> str:
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat()
    return f"dbresearch-{name}-{today}.{fmt}"


def document_table(
    db: Session, documents: list[Document], section: str
) -> tuple[str, list[str], list[list[Any]]]:
    """Sheet name, headers and rows for the found documents. Extra lookups are batched."""
    ids = [d.id for d in documents]
    owners = search.owners(db, ids)
    if section == "proposals":
        return "ทุนพัฒนาข้อเสนอ", PROPOSAL_HEADERS, _proposal_rows(db, documents, owners)
    categories: dict[uuid.UUID, list[str]] = {}
    for doc_id, name in db.execute(
        select(DocumentCategory.document_id, Category.name_th)
        .join(Category, Category.id == DocumentCategory.category_id)
        .join(CategoryGroup, CategoryGroup.id == Category.group_id)
        .where(DocumentCategory.document_id.in_(ids))
        .order_by(CategoryGroup.sort, Category.sort, Category.name_th)
    ):
        categories.setdefault(doc_id, []).append(name)
    uploaders = dict(
        db.execute(
            select(User.id, User.display_name).where(
                User.id.in_({d.uploaded_by for d in documents})
            )
        ).all()
    )
    rows = [
        [
            d.reference_no,
            d.title,
            d.title_en,
            KIND.get(d.kind) if d.kind else None,
            FUNDING_SOURCE.get(d.funding_source) if d.funding_source else None,
            FUNDING_TYPE.get(d.funding_type) if d.funding_type else None,
            d.fiscal_year + BE if d.fiscal_year else None,
            th_date(d.document_date),
            _number(d.budget_total),
            ", ".join(owners.get(d.id, [])),
            ", ".join(categories.get(d.id, [])),
            STATUS[d.status],
            "ปิดโครงการแล้ว" if d.closed_at else "ดำเนินการอยู่",
            uploaders.get(d.uploaded_by),
            th_date(d.created_at),
        ]
        for d in documents
    ]
    return "เอกสาร", CONTRACT_HEADERS, rows


def _proposal_rows(
    db: Session, documents: list[Document], owners: dict[uuid.UUID, list[str]]
) -> list[list[Any]]:
    ids = [d.id for d in documents]
    extras = search.proposal_rows(db, ids)
    projects = {
        p.document_id: p
        for p in db.scalars(select(ProposalProject).where(ProposalProject.document_id.in_(ids)))
    }
    rows = []
    for d in documents:
        extra = extras.get(d.id, {})
        project = projects.get(d.id)
        spent = project.spent_total if project else None
        left = d.budget_total - spent if d.budget_total is not None and spent is not None else None
        rows.append(
            [
                extra.get("received_no"),
                extra.get("request_ref"),
                ", ".join(owners.get(d.id, [])),
                extra.get("department"),
                d.title,
                d.fiscal_year + BE if d.fiscal_year else None,
                _number(d.budget_total),
                th_date(d.effective_from),
                th_date(d.effective_to),
                project.research_area if project else None,
                th_date(extra.get("kpi_due")),
                PROJECT_STATE.get(extra.get("state"), extra.get("state")),
                _number(spent),
                _number(left),
                OUTCOME.get(project.outcome) if project and project.outcome else None,
                project.outcome_funder if project else None,
            ]
        )
    return rows


def report_rows(report: dict) -> list[list[Any]]:
    """The proposal report's per-year table (what the overview page shows)."""
    return [
        [
            y["fiscal_year_be"],
            y["total"],
            y["closed"],
            y["active"],
            y["overdue"],
            y["cancelled"],
            y["budget"],
            y["spent"],
            y["won"],
        ]
        for y in report["by_year"]
    ]
