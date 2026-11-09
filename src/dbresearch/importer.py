"""Bulk import of proposal-development papers from a folder (Phase 7 step 4, DESIGN §11).

Two passes, both run in the worker container (it has Tesseract, the KEK, the blob store and
the read-only `/samples` mount):

    # 1. Read and group; writes the plan (JSON) to stdout and a report to stderr. No DB writes.
    docker compose exec -T worker python -m dbresearch.importer plan /samples/proposal_dev \\
        [--ocr-cache /samples/proposal_dev/ocr.jsonl] [--sheet /samples/proposal_dev/sheet.csv] \\
        > samples/proposal_dev/plan.json
    # 2. Store the files (encrypted) and create the projects, all in review.
    docker compose exec -T worker python -m dbresearch.importer apply \\
        /samples/proposal_dev/plan.json --as-email someone@example.org

The plan and `--detail` output hold names and titles: confidential, keep them in `samples/`.
Grouping is by content (title, researcher, year), never by folder: closings are often filed
under a later year. Every project lands in `needs_review` for a person to confirm.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from dbresearch.autofill import proposal, thai

# ───────────── Plan (pure: no DB, no files) ─────────────
TITLE_SAME = 90  # same project (a re-submitted / corrected request)
TITLE_MATCH = 80  # a closing / cancel / change paper belongs to this project
SIDE_TYPES = ("title_change", "close", "cancel", "budget_change")


@dataclass
class Paper:
    file: str  # path relative to the import folder
    sha256: str
    kind: str | None  # paper type from `proposal.extract`
    fields: dict[str, Any]

    @property
    def title(self) -> str:
        return compact(self.fields.get("title"))

    @property
    def first_name(self) -> str:
        return first_name(self.fields.get("owner"))


@dataclass
class Project:
    request: Paper | None = None
    resubmissions: list[Paper] = field(default_factory=list)  # corrected requests → versions
    papers: list[Paper] = field(default_factory=list)  # closing, cancel, change memos
    titles: list[str] = field(default_factory=list)  # every title it went by (compact)
    notes: list[str] = field(default_factory=list)

    @property
    def lead(self) -> Paper:
        return self.request or self.papers[0]


@dataclass
class Plan:
    projects: list[Project] = field(default_factory=list)
    programme: list[Paper] = field(default_factory=list)
    unknown: list[Paper] = field(default_factory=list)
    duplicates: list[tuple[str, str]] = field(default_factory=list)  # (file, same as)


def compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def first_name(owner: Any) -> str:
    _, name = thai.split_person(str(owner or ""))
    return name.split()[0] if name.split() else ""


def _title_score(title: str, project: Project) -> float:
    if not title:
        return 0.0
    best = 0.0
    for known in project.titles:
        score = fuzz.ratio(title, known)
        if min(len(title), len(known)) >= 15:  # one side cut short ('…ในอากาศ' vs the full title)
            score = max(score, 0.95 * fuzz.partial_ratio(title, known))
        best = max(best, score)
    return best


def _match(paper: Paper, projects: list[Project]) -> Project | None:
    """The project this paper belongs to: title first, the researcher's name as a tie-break
    (one researcher often has a grant every year)."""
    scored = []
    for project in projects:
        score = _title_score(paper.title, project)
        if paper.first_name and paper.first_name == project.lead.first_name:
            score += 5
        year = paper.fields.get("fiscal_year")
        if year is not None and year == project.lead.fields.get("fiscal_year"):
            score += 3  # the same title re-applied a year later (after a cancellation)
        scored.append((score, project))
    scored.sort(key=lambda s: s[0], reverse=True)
    if scored and scored[0][0] >= TITLE_MATCH:
        return scored[0][1]
    if paper.first_name:
        # Title unreadable or different: the researcher's one project of that fiscal year.
        year = paper.fields.get("fiscal_year")
        same = [
            p
            for p in projects
            if p.lead.first_name == paper.first_name
            and year is not None
            and p.lead.fields.get("fiscal_year") == year
        ]
        if len(same) == 1:
            same[0].notes.append(f"matched by researcher and year, not title: {paper.file}")
            return same[0]
    return None


def _resubmission_last(paper: Paper) -> tuple[int, str]:
    """Corrected re-submissions ('(แก้ไข)') sort after the original."""
    return ("แก้ไข" in paper.file, paper.file)


def build_plan(papers: list[Paper], other: set[str] = frozenset()) -> Plan:
    """`other`: files that go to the separate 'other' part whatever they read as."""
    plan = Plan()
    seen: dict[str, str] = {}
    unique = []
    for paper in sorted(papers, key=lambda p: p.file):
        if paper.sha256 in seen:
            plan.duplicates.append((paper.file, seen[paper.sha256]))
            continue
        seen[paper.sha256] = paper.file
        if paper.file in other:
            plan.programme.append(paper)
            continue
        unique.append(paper)

    requests = sorted((p for p in unique if p.kind == "request"), key=_resubmission_last)
    for paper in requests:
        twin = next(
            (
                p
                for p in plan.projects
                if _title_score(paper.title, p) >= TITLE_SAME
                and paper.fields.get("fiscal_year") == p.lead.fields.get("fiscal_year")
                and paper.first_name == p.lead.first_name
            ),
            None,
        )
        if twin is not None:
            twin.resubmissions.append(paper)
            continue
        plan.projects.append(Project(request=paper, titles=[paper.title] if paper.title else []))

    # Title changes first: their new title is how later papers (closings) name the project.
    order = {kind: i for i, kind in enumerate(SIDE_TYPES)}
    side = sorted((p for p in unique if p.kind in SIDE_TYPES), key=lambda p: order[p.kind])
    for paper in side:
        project = _match(paper, plan.projects)
        if project is None:
            project = Project(titles=[paper.title] if paper.title else [])
            project.notes.append("no request paper found")
            plan.projects.append(project)
        project.papers.append(paper)
        new_title = compact(paper.fields.get("new_title"))
        if new_title and new_title not in project.titles:
            project.titles.append(new_title)

    plan.programme += [p for p in unique if p.kind == "programme"]
    plan.unknown = [p for p in unique if p.kind is None]
    for project in plan.projects:
        kinds = [p.kind for p in project.papers]
        if "close" in kinds and "cancel" in kinds:
            project.notes.append("both a closing and a cancellation: check which is right")
        if kinds.count("close") > 1:
            project.notes.append("more than one closing paper")
    return plan


# ───────────── Spreadsheet check (report only) ─────────────
def sheet_report(plan: Plan, sheet_path: Path) -> list[str]:
    with sheet_path.open() as f:
        rows = [r for r in csv.reader(f) if len(r) >= 5]
    lines = []
    matched = set()
    for no, (_n, _name, title, year, remark) in enumerate(rows, 1):
        best, best_score = None, 0.0
        for project in plan.projects:
            score = _title_score(compact(title), project)
            fiscal = project.lead.fields.get("fiscal_year")
            if fiscal is not None and str(fiscal + thai.BE_OFFSET) == year.strip():
                score += 3  # same title in two years (re-applied after a cancellation)
            if score > best_score:
                best, best_score = project, score
        if best is None or best_score < TITLE_MATCH:
            lines.append(f"sheet row {no}: no project found")
            continue
        matched.add(id(best))
        kinds = {p.kind for p in best.papers}
        if "ปิดทุน" in remark and "close" not in kinds and not _also_closes(best):
            lines.append(f"sheet row {no}: sheet says closed, no closing paper")
        if "ยกเลิก" in remark and "cancel" not in kinds:
            lines.append(f"sheet row {no}: sheet says cancelled, no cancellation paper")
    missing = [p for p in plan.projects if id(p) not in matched]
    lines.append(f"projects not in the sheet: {len(missing)}")
    return lines


def _also_closes(project: Project) -> bool:
    return any(p.fields.get("also_close") for p in project.papers)


# ───────────── Reading files ─────────────
PLAN_PAGES = 4  # the memo and its first attachments; the worker OCRs everything later


def read_paper(path: Path, root: Path, cache: dict[str, dict]) -> Paper:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pages = _cached_pages(cache[digest]) if digest in cache else _ocr_pages(path, PLAN_PAGES)
    result = proposal.extract(pages)
    return Paper(
        file=str(path.relative_to(root)),
        sha256=digest,
        kind=result["kind"],
        fields={k: v["value"] for k, v in result["fields"].items()},
    )


def _cached_pages(record: dict) -> list:
    from dbresearch.autofill.page import Page
    from dbresearch.ocr_layout import Line, Word

    pages = []
    for number, cached in enumerate(record["pages"], 1):
        lines = [
            Line(ln["text"], (Word(ln["text"], 0, ln["top"], 0, 0, ln["conf"]),), ln["conf"])
            for ln in cached["lines"]
        ]
        pages.append(Page(number, cached["width"], cached["height"], lines))
    return pages


def _ocr_pages(path: Path, limit: int) -> list:
    import cv2
    import pypdfium2 as pdfium

    from dbresearch.autofill.page import DPI, Page, ocr_lines

    pdf = pdfium.PdfDocument(path)
    try:
        pages = []
        for index in range(min(len(pdf), limit)):
            gray = pdf[index].render(scale=DPI / 72, grayscale=True).to_numpy()
            if gray.ndim == 3:
                gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
            pages.append(Page(index + 1, gray.shape[1], gray.shape[0], ocr_lines(gray)))
        return pages
    finally:
        pdf.close()


def plan_to_json(plan: Plan) -> str:
    return json.dumps(asdict(plan), ensure_ascii=False, indent=1, default=str)


def plan_from_json(text: str) -> Plan:
    data = json.loads(text)

    def paper(d: dict | None) -> Paper | None:
        return Paper(**d) if d else None

    return Plan(
        projects=[
            Project(
                request=paper(p["request"]),
                resubmissions=[paper(x) for x in p["resubmissions"]],
                papers=[paper(x) for x in p["papers"]],
                titles=p["titles"],
                notes=p["notes"],
            )
            for p in data["projects"]
        ],
        programme=[paper(x) for x in data["programme"]],
        unknown=[paper(x) for x in data["unknown"]],
        duplicates=[tuple(d) for d in data["duplicates"]],
    )


def summary(plan: Plan) -> list[str]:
    kinds: dict[str, int] = {}
    for project in plan.projects:
        for p in [project.request, *project.resubmissions, *project.papers]:
            if p:
                kinds[p.kind or "?"] = kinds.get(p.kind or "?", 0) + 1
    closed = sum(
        any(p.kind == "close" for p in pr.papers) or _also_closes(pr) for pr in plan.projects
    )
    cancelled = sum(any(p.kind == "cancel" for p in pr.papers) for pr in plan.projects)
    return [
        f"projects: {len(plan.projects)} (closed {closed}, cancelled {cancelled}, "
        f"without a request {sum(pr.request is None for pr in plan.projects)}, "
        f"with notes {sum(bool(pr.notes) for pr in plan.projects)})",
        f"papers in projects: {kinds}",
        f"programme papers: {len(plan.programme)}, unreadable: {len(plan.unknown)}, "
        f"duplicates skipped: {len(plan.duplicates)}",
    ]


# ───────────── Apply (DB + encrypted store) ─────────────
def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _money(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None


def apply_plan(plan: Plan, root: Path, user_email: str, out=sys.stderr) -> dict[str, int]:
    """Store every paper (encrypted) and create the projects. Safe to re-run: files already
    stored are skipped, and papers are added to the project that holds their request."""
    from sqlalchemy import select

    from dbresearch import audit
    from dbresearch.db import new_session
    from dbresearch.models import DocumentVersion, User

    counts = {"projects": 0, "programme": 0, "files": 0, "skipped": 0, "failed": 0}
    with new_session() as db:
        user = db.scalar(select(User).where(User.email == user_email))
        if user is None:
            raise SystemExit(f"No user with email {user_email}")

        def stored(paper: Paper):
            return db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.sha256_plain == bytes.fromhex(paper.sha256)
                )
            )

        for project in plan.projects:
            try:
                created = _apply_project(db, user, project, root, stored, counts)
                db.commit()
                counts["projects"] += created
            except Exception as exc:  # one bad file must not stop the import
                db.rollback()
                counts["failed"] += 1
                print(f"failed: {project.lead.file}: {type(exc).__name__}: {exc}", file=out)
        for paper in plan.programme + plan.unknown:
            try:
                if stored(paper) is not None:
                    counts["skipped"] += 1
                    continue
                _store_other(db, user, paper, root)
                db.commit()
                counts["programme"] += 1
                counts["files"] += 1
            except Exception as exc:
                db.rollback()
                counts["failed"] += 1
                print(f"failed: {paper.file}: {type(exc).__name__}: {exc}", file=out)
        audit.record(db, "document.import", "document", actor_id=user.id, **counts)
        db.commit()
    return counts


def _store(db, user, paper: Paper, root: Path, **kwargs):
    from dbresearch.documents import store_version

    with (root / paper.file).open("rb") as handle:
        return store_version(db, user, handle, Path(paper.file).name, **kwargs)


def _store_other(db, user, paper: Paper, root: Path) -> None:
    from dbresearch.models import DocKind, Document

    version = _store(db, user, paper, root, kind=DocKind.OTHER)
    document = db.get(Document, version.document_id)
    f = paper.fields
    document.title = (f.get("title") or Path(paper.file).stem)[:500]
    document.document_date = _date(f.get("document_date"))
    document.fiscal_year = f.get("fiscal_year")


def _apply_project(db, user, project: Project, root: Path, stored, counts) -> int:
    """One project: its lead paper (the request, else its first paper) becomes the document;
    re-submissions become new versions; the other papers attach with their events."""
    from dbresearch.models import DocKind, Document, ProposalProject, VersionPurpose

    lead = project.lead
    existing = stored(lead)
    created = 0
    if existing is not None:
        document = db.get(Document, existing.document_id)
        counts["skipped"] += 1
    else:
        version = _store(db, user, lead, root, kind=DocKind.PROPOSAL_DEV)
        document = db.get(Document, version.document_id)
        counts["files"] += 1
        created = 1
        _fill_document(db, document, lead)
        db.add(
            ProposalProject(
                document_id=document.id,
                request_ref=lead.fields.get("memo_ref") if project.request else None,
                research_area=lead.fields.get("research_area"),
                kpi_target=lead.fields.get("kpi_target"),
                kpi_due=_date(lead.fields.get("kpi_due")),
            )
        )
        db.flush()
        if project.notes:
            document.extra = {**(document.extra or {}), "import_notes": project.notes}
        _handle(db, user, document, lead, version)

    for paper in project.resubmissions:
        if stored(paper) is None:
            _store(db, user, paper, root, document=document)
            counts["files"] += 1
        else:
            counts["skipped"] += 1

    for paper in project.papers:
        if paper is lead:
            continue
        if stored(paper) is not None:
            counts["skipped"] += 1
            continue
        purpose = VersionPurpose.CLOSURE if paper.kind == "close" else VersionPurpose.PAPER
        version = _store(db, user, paper, root, document=document, purpose=purpose)
        counts["files"] += 1
        _handle(db, user, document, paper, version)
    return created


def _handle(db, user, document, paper: Paper, version) -> None:
    """The paper's timeline event, and what it changes (title, closed, cancelled)."""
    from dbresearch import audit
    from dbresearch.models import ProjectEventType, ProposalProject

    f = paper.fields
    kind = {
        "request": ProjectEventType.APPROVED,
        "title_change": ProjectEventType.TITLE_CHANGE,
        "budget_change": ProjectEventType.BUDGET_CHANGE,
        "close": ProjectEventType.CLOSE,
        "cancel": ProjectEventType.CANCEL,
    }.get(paper.kind or "", ProjectEventType.OTHER)
    _event(db, user, document, kind, paper, version)
    details = db.get(ProposalProject, document.id)
    if kind == ProjectEventType.TITLE_CHANGE and f.get("new_title"):
        document.title = f["new_title"]
    if kind == ProjectEventType.CLOSE or (
        kind == ProjectEventType.TITLE_CHANGE and f.get("also_close")
    ):
        if kind == ProjectEventType.TITLE_CHANGE:
            _event(db, user, document, ProjectEventType.CLOSE, paper, version)
        _close(db, user, document, paper, details)
    if (
        kind == ProjectEventType.CANCEL
        and document.closed_at is None
        and document.cancelled_at is None
    ):
        document.cancelled_at = datetime.now(UTC)
        document.cancelled_by = user.id
        document.cancelled_on = _date(f.get("document_date"))
        document.cancel_ref = f.get("memo_ref")
        document.cancel_reason = f.get("cancel_reason")
        audit.record(
            db, "document.cancel", "document", document.id, actor_id=user.id, source="import"
        )


def _owner(db, owner: str):
    """The researcher as a `people` row (same lookup as the review form: by Thai name)."""
    from sqlalchemy import select

    from dbresearch.models import Person
    from dbresearch.textnorm import normalize

    prefix, name = thai.split_person(owner)
    name = normalize(name).strip()
    if not name:
        return None
    person = db.scalars(select(Person).where(Person.name_th == name).limit(1)).first()
    if person is None:
        person = Person(prefix_th=prefix, name_th=name)
        db.add(person)
        db.flush()
    return person


def _fill_document(db, document, paper: Paper) -> None:
    """Readings → document fields (suggestions: the project still needs review)."""
    from dbresearch.models import FUNDING_TYPE_OF, DocumentPerson, FundingSource, PersonRole
    from dbresearch.textnorm import normalize

    f = paper.fields
    document.title = normalize(f.get("title") or Path(paper.file).stem)[:500]
    document.document_date = _date(f.get("document_date"))
    document.effective_from = _date(f.get("effective_from"))
    document.effective_to = _date(f.get("effective_to"))
    start, end = document.effective_from, document.effective_to
    if start and end and end < start:
        document.effective_to = None  # a misread date must not break the range check
    document.fiscal_year = f.get("fiscal_year")
    document.budget_total = _money(f.get("budget_total"))
    if source := f.get("funding_source"):
        document.funding_source = FundingSource(source)
        document.funding_type = FUNDING_TYPE_OF[FundingSource(source)]
    if f.get("owner") and (person := _owner(db, f["owner"])) is not None:
        db.add(
            DocumentPerson(
                document_id=document.id,
                person_id=person.id,
                role=PersonRole.OWNER,
                unit=f.get("department"),
            )
        )


def _event(db, user, document, kind, paper: Paper, version) -> None:
    from dbresearch.models import ProjectEvent

    f = paper.fields
    details: dict[str, Any] = {"file": Path(paper.file).name, "source": "import"}
    if f.get("new_title"):
        details |= {"old_title": f.get("title"), "new_title": f["new_title"]}
    if f.get("kpi_result"):
        details["kpi_result"] = f["kpi_result"]
    if f.get("cancel_reason"):
        details["reason"] = f["cancel_reason"]
    db.add(
        ProjectEvent(
            document_id=document.id,
            event_type=kind,
            event_on=_date(f.get("document_date")),
            memo_ref=f.get("memo_ref"),
            version_id=version.id,
            details=details,
            created_by=user.id,
        )
    )


def _close(db, user, document, paper: Paper, details) -> None:
    from dbresearch.documents import close_project

    f = paper.fields
    if details is not None:
        details.kpi_result = details.kpi_result or f.get("kpi_result")
        details.spent_total = details.spent_total or _money(f.get("spent_total"))
    if document.cancelled_at is not None:
        return  # both a closing and a cancellation: flagged in the plan notes for a person
    close_project(
        db,
        user,
        document,
        closed_on=_date(f.get("document_date")),
        closure_ref=f.get("memo_ref"),
        closure_note=None,
        ip=None,
    )


# ───────────── CLI ─────────────
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dbresearch.importer")
    commands = parser.add_subparsers(dest="command", required=True)
    plan_cmd = commands.add_parser("plan", help="read and group a folder (no DB writes)")
    plan_cmd.add_argument("root", type=Path)
    plan_cmd.add_argument("--ocr-cache", type=Path, help="OCR cache from proposal_dev_ocr.py")
    plan_cmd.add_argument("--sheet", type=Path, help="research office spreadsheet (CSV)")
    plan_cmd.add_argument("--detail", action="store_true", help="print names/titles (confidential)")
    plan_cmd.add_argument(
        "--other-top-level",
        action="store_true",
        help="files directly in the folder (not in a year folder) go to the 'other' part",
    )
    apply_cmd = commands.add_parser("apply", help="store the files and create the projects")
    apply_cmd.add_argument("plan", type=Path)
    apply_cmd.add_argument("--root", type=Path, help="import folder (default: the plan's)")
    apply_cmd.add_argument("--as-email", required=True, help="the importing user's email")
    args = parser.parse_args(argv)

    if args.command == "plan":
        cache = {}
        if args.ocr_cache:
            for line in args.ocr_cache.open():
                if line.strip():
                    record = json.loads(line)
                    cache[record["sha256"]] = record
        files = sorted(args.root.rglob("*.pdf"))
        papers = []
        for n, path in enumerate(files, 1):
            papers.append(read_paper(path, args.root, cache))
            print(f"read {n}/{len(files)}", file=sys.stderr, flush=True)
        other = {p.file for p in papers if "/" not in p.file} if args.other_top_level else set()
        plan = build_plan(papers, other)
        print(plan_to_json(plan))
        for line in summary(plan):
            print(line, file=sys.stderr)
        if args.sheet:
            for line in sheet_report(plan, args.sheet):
                print(line, file=sys.stderr)
        if args.detail:
            for project in plan.projects:
                print(f"- {project.lead.fields.get('title', '?')[:70]}", file=sys.stderr)
                for p in [project.request, *project.resubmissions, *project.papers]:
                    if p:
                        print(f"    {p.kind:13} {p.file}", file=sys.stderr)
                for note in project.notes:
                    print(f"    ! {note}", file=sys.stderr)
    else:
        plan = plan_from_json(args.plan.read_text())
        root = args.root or args.plan.parent
        counts = apply_plan(plan, root, args.as_email)
        print(counts, file=sys.stderr)


if __name__ == "__main__":
    main()
