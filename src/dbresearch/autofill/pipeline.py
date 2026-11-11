"""Auto-fill one stored version: decrypt to tmpfs → pages → sections → candidates → review.

Nothing here leaves the server, and the decrypted file only exists on the worker's tmpfs
for the duration of the run (CLAUDE.md).
"""

import logging
import os
import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from dbresearch import search_text
from dbresearch.autofill import closure, proposal, thai
from dbresearch.autofill.categories import CategoryIndex, Match
from dbresearch.autofill.page import Page, analyse_pdf, strip_label, word_dicts
from dbresearch.autofill.rules import Candidate, extract
from dbresearch.autofill.sections import Section, TemplateSpec, split_sections
from dbresearch.config import get_settings
from dbresearch.documents import read_version
from dbresearch.models import (
    DocKind,
    DocStatus,
    Document,
    DocumentPage,
    DocumentSection,
    DocumentVersion,
    ExtractionTemplate,
    OcrStatus,
    VersionPurpose,
)

log = logging.getLogger("dbresearch.autofill")

# Contract no. R + B.E. year + series letter + running no. (department convention)
# The series letter is the faculty that issued the number (E = engineering), *not* the
# funding type: an engineering contract can be internal or external.
CONTRACT_NO = re.compile(r"^R(\d{4})([A-Z])(\d+)$")
# Funding type from the contract's title block (above 'โครงการ :'): a contract *between* an
# outside agency and the university ('… ระหว่าง <agency> กับมหาวิทยาลัยนเรศวร') is external;
# one paid 'จากงบประมาณ…' of a single unit (e.g. รายได้คณะ) is internal. The parties clause
# below the title also says 'ระหว่างคณะ… กับ <researcher>', so only the title block counts.
EXTERNAL_HINT = re.compile(r"ระหว่าง.{2,120}?กับ")
INTERNAL_HINT = re.compile(r"จากง\S?บ\S?ประมาณ|งบประมาณรายได้")
TITLE_BLOCK_END = re.compile(r"^(?:โครงการ\s*[:：]|สัญญานี้|สัญญาฉบับนี้)")
CONSENSUS_FIELDS = ("title", "title_en", "owner")
LIST_FIELDS = ("team", "team_en", "budget_lines")
PROGRAMME = re.compile(r"\[([^\]]{2,60})\]")
REQUIRED = ("title", "reference_no")
PRINTED_PAGE = re.compile(r"หน้า\s*(\d{1,3})")


def load_templates(db: Session) -> list[TemplateSpec]:
    rows = db.scalars(
        select(ExtractionTemplate)
        .where(ExtractionTemplate.active.is_(True))
        .order_by(ExtractionTemplate.priority.desc())
    )
    return [
        TemplateSpec(
            id=t.id,
            name=t.name,
            attachment_no=t.attachment_no,
            kind=t.kind.value if t.kind else None,
            funding_type=t.funding_type.value if t.funding_type else None,
            keywords=tuple(t.match_rules.get("keywords", [])),
            min_score=float(t.match_rules.get("min_score", 1)),
            rules=tuple(t.field_rules.get("rules", [])),
            checkbox_groups=t.checkbox_groups,
            priority=t.priority,
        )
        for t in rows
    ]


def _json(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    return value


# ───────────── Extraction ─────────────
def collect_candidates(
    sections: list[Section], pages: list[Page], templates: list[TemplateSpec]
) -> list[Candidate]:
    """Section rules per matched section; footer rules of *all* templates once over the whole
    PDF (the footer carries the contract no. even when no section template matched)."""
    candidates: list[Candidate] = []
    for section in sections:
        if section.template is not None:
            rules = [r for r in section.template.rules if r["layout"] != "footer"]
            candidates += extract(rules, section.pages, pages)
    footer_rules: dict[tuple[str, str], dict] = {}
    for template in templates:
        for rule in template.rules:
            if rule["layout"] == "footer":
                footer_rules.setdefault((rule["field"], rule.get("pattern", "")), rule)
    candidates += extract(list(footer_rules.values()), [], pages)
    return candidates


def _support(candidate: Candidate, others: list[Candidate]) -> float:
    """How much the other sources agree with this value (titles repeat across sections)."""
    text = re.sub(r"\s+", "", str(candidate.value))
    return sum(
        fuzz.ratio(text, re.sub(r"\s+", "", str(o.value))) / 100
        for o in others
        if o is not candidate and o.page != candidate.page
    )


def best_values(candidates: list[Candidate]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for name in {c.field for c in candidates if c.field not in LIST_FIELDS}:
        mine = [c for c in candidates if c.field == name]
        if name in CONSENSUS_FIELDS and len(mine) > 2:
            # The same title is printed in the contract, the budget sheet and the proposal
            # form. A misread label elsewhere (a table line read as 'โครงการ …') has no support.
            support = {id(c): round(_support(c, mine), 1) for c in mine}
            ranked = sorted(mine, key=lambda c: (support[id(c)], c.confidence), reverse=True)
        else:
            ranked = sorted(mine, key=lambda c: c.confidence, reverse=True)
        best = ranked[0]
        alternatives = []
        for c in ranked[1:]:
            if c.value != best.value and _json(c.value) not in alternatives:
                alternatives.append(_json(c.value))
        fields[name] = {
            "value": _json(best.value),
            "confidence": best.confidence,
            "page": best.page,
            "source": best.layout,
            "alternatives": alternatives[:5],
            **{k: _json(v) for k, v in best.extra.items() if k != "conflict"},
        }
    return fields


SAME_NAME_MIN = 85  # one misread character must not split a person in two


def _best_list(candidates: list[Candidate], name: str) -> list:
    found = sorted((c for c in candidates if c.field == name), key=lambda c: -c.confidence)
    return found[0].value if found else []


def installments(candidates: list[Candidate], fields: dict[str, dict]) -> list[dict]:
    """Installment suggestions; an amount printed in another column is computed from the
    percentage and the total (and marked so the review screen can say so)."""
    lines = [dict(line) for line in _best_list(candidates, "budget_lines")]
    total = fields.get("budget_total", {}).get("value")
    for line in lines:
        if line["amount"] is None and line["percent"] is not None and total is not None:
            line["amount"] = (Decimal(str(total)) * Decimal(str(line["percent"])) / 100).quantize(
                Decimal("0.01")
            )
            line["computed"] = True
    return [line for line in lines if line["amount"] is not None]


def same_person(a: str, b: str, minimum: float = SAME_NAME_MIN) -> bool:
    """Same name despite OCR slips. A surname on a dotted line often fails to read at all
    ('สมชาย' vs 'สมชายใจดี'), so a 4+ letter start of the other name also counts."""
    a, b = _bare(a, b)
    short, long = sorted((a, b), key=len)
    if len(short) >= 4 and long.startswith(short):
        return True
    return fuzz.ratio(a, b) >= minimum


def team_people(candidates: list[Candidate], fields: dict[str, dict]) -> list[dict]:
    """Research team from the proposal form, plus the footer owner if not already listed."""
    people: list[dict] = []
    for c in sorted((c for c in candidates if c.field == "team"), key=lambda c: c.page):
        if not any(same_person(c.value["name"], p["name"]) for p in people):
            people.append({**c.value, "page": c.page, "confidence": c.confidence})
    for c in (c for c in candidates if c.field == "team_en"):
        name_th, name_en = c.value["name_th"], c.value["name_en"]
        target = next(
            (p for p in people if name_th and fuzz.ratio(*_bare(p["name"], name_th)) >= 70),
            people[0] if len(people) == 1 else None,
        )
        if target is not None and not target.get("name_en"):
            target["name_en"] = name_en
    owner = fields.get("owner", {}).get("value")
    owner_name = thai.split_person(owner)[1] if owner else None
    _infer_roles(people, owner_name)
    match = next((p for p in people if owner_name and same_person(owner_name, p["name"], 75)), None)
    if match is not None and len(_bare(owner_name, "")[0]) > len(_bare(match["name"], "")[0]):
        match["name"] = owner_name  # the contract spells the grantee's name out in full
    if owner_name and match is None:
        people.insert(
            0,
            {
                "prefix_th": thai.split_person(owner)[0],
                "name": owner_name,
                "role": "owner",
                "role_source": "footer",
                "share_pct": None,
                "unit": None,
                "page": None,
                "confidence": fields["owner"]["confidence"],
            },
        )
    return people


def _bare(a: str, b: str) -> tuple[str, str]:
    return re.sub(r"\s+", "", a), re.sub(r"\s+", "", b)


def _infer_roles(people: list[dict], owner_name: str | None) -> None:
    """Roles OCR badly (dotted lines). The footer owner, else the first person listed, is the
    project head; everyone else without a readable role is a co-researcher."""
    has_owner = any(p.get("role") == "owner" for p in people)
    for index, person in enumerate(people):
        if person.get("role") is not None:
            person["role_source"] = "ocr"
            continue
        # Without a footer owner, the first person listed is taken as the project head.
        is_owner = same_person(person["name"], owner_name) if owner_name else index == 0
        person["role"] = "owner" if is_owner and not has_owner else "co_investigator"
        person["role_source"] = "inferred"
        has_owner = has_owner or person["role"] == "owner"
    # Someone heads every project: the contract's grantee, else a researcher working alone.
    if people and not has_owner:
        head = next((p for p in people if owner_name and same_person(p["name"], owner_name)), None)
        if head is None and len(people) == 1:
            head = people[0]
        if head is not None:
            head["role"], head["role_source"] = "owner", "inferred"


def checkbox_suggestions(
    sections: list[Section], index: CategoryIndex
) -> tuple[list[dict], list[dict]]:
    """Checked boxes → category suggestions (or suggested tags). Unchecked boxes are ignored."""
    checks: list[dict] = []
    warnings: list[dict] = []
    for section in sections:
        if section.template is None or not section.template.checkbox_groups:
            continue
        for page in section.pages:
            for box in page.boxes:
                if box.checked is not True:
                    continue
                group = index.match_group(box.heading)
                match: Match | None = None
                label = box.row_label
                if group is None and thai.is_noise(label):
                    continue  # a ticked table cell ('2', '[] 10'), not a form option
                if group is not None:
                    match = index.match_option(group, label)
                    if match is None and page.image is not None:
                        label = strip_label(box, page.image)
                        match = index.match_option(group, label)
                checks.append(
                    {
                        "page": page.number,
                        "group_key": group.key if group else None,
                        "heading": box.heading,
                        "label": label,
                        "category_id": str(match.category_id) if match else None,
                        "category_name": match.category_name if match else None,
                        "score": match.score if match else None,
                        "suggest": "category" if match else ("tag" if label else None),
                    }
                )
    by_group: dict[str, int] = {}
    for check in checks:
        if check["category_id"]:
            by_group[check["group_key"]] = by_group.get(check["group_key"], 0) + 1
    for key, count in by_group.items():
        if count > 1 and not index.groups[key].multi:
            warnings.append({"code": "single_choice_violation", "group": key, "count": count})
    return checks, warnings


def infer(
    fields: dict[str, dict], sections: list[Section], index: CategoryIndex
) -> tuple[dict[str, Any], list[dict], list[dict]]:
    """Kind, funding type, fiscal year, agency/programme hints, and cross-check warnings."""
    inferred: dict[str, Any] = {}
    hints: list[dict] = []
    warnings: list[dict] = []
    body = next((s for s in sections if s.template and s.template.attachment_no is None), None)
    header = " ".join(ln.text for ln in body.pages[0].body[:8]) if body else ""
    title_block = _title_block(body.pages[0]) if body else ""

    kinds = {s.template.kind for s in sections if s.template and s.template.kind}
    if len(kinds) == 1:
        inferred["kind"] = kinds.pop()

    ref = fields.get("reference_no", {}).get("value")
    ref_year = None
    if ref and (m := CONTRACT_NO.match(ref)):
        ref_year = int(m[1])
    inferred["funding_type"] = funding_from_title(title_block)

    fiscal = fields.get("fiscal_year", {}).get("value")
    if fiscal is None and fields.get("document_date", {}).get("value"):
        fiscal = thai.fiscal_year_of(date.fromisoformat(fields["document_date"]["value"]))
    inferred["fiscal_year"] = fiscal
    if fiscal and ref_year and thai.be_to_gregorian(ref_year) != fiscal:
        warnings.append(
            {
                "code": "fiscal_year_mismatch",
                "header_be": fiscal + thai.BE_OFFSET,
                "contract_no_be": ref_year,
            }
        )

    if agency := index.find_in_text("agency", header):
        hints.append(
            {
                "group_key": "agency",
                "category_id": str(agency.category_id),
                "category_name": agency.category_name,
                "score": agency.score,
                "suggest": "category",
                "source": "header",
            }
        )
    if programme := PROGRAMME.search(header):
        label = programme[1].strip()
        group = index.groups.get("grant_programme")
        match = index.match_option(group, label) if group else None
        hints.append(
            {
                "group_key": "grant_programme",
                "label": label,
                "category_id": str(match.category_id) if match else None,
                "category_name": match.category_name if match else None,
                "suggest": "category" if match else "tag",
                "source": "header",
            }
        )
    return inferred, hints, warnings


def _title_block(page: Page) -> str:
    """The contract's title lines: from the top down to 'โครงการ :' / 'สัญญานี้ทำขึ้น'."""
    out = []
    for line in page.body[:10]:
        if TITLE_BLOCK_END.match(line.text.strip()):
            break
        out.append(line.text)
    return " ".join(out)


def funding_from_title(title_block: str) -> str | None:
    text = re.sub(r"\s+", "", title_block)
    if EXTERNAL_HINT.search(text):
        return "external"
    if INTERNAL_HINT.search(text):
        return "internal"
    return None


def field_warnings(
    fields: dict[str, dict], candidates: list[Candidate], people: list[dict]
) -> list[dict]:
    warnings = []
    budget = fields.get("budget_total", {})
    words, number = budget.get("words_amount"), budget.get("value")
    if words is not None and number is not None and Decimal(str(words)) != Decimal(number):
        warnings.append({"code": "amount_words_mismatch", "digits": number, "words": words})
    conflict = next(
        (
            c.extra["conflict"]
            for c in candidates
            if c.field == "reference_no" and "conflict" in c.extra
        ),
        None,
    )
    if conflict:
        warnings.append({"code": "multiple_contract_numbers", "values": sorted(conflict)})
    for name in REQUIRED:
        if name not in fields:
            warnings.append({"code": "missing_field", "field": name})
    shares = [p["share_pct"] for p in people if p.get("share_pct") is not None]
    if shares and abs(sum(shares) - 100) > 0.5:
        warnings.append({"code": "team_share_not_100", "total": sum(shares)})
    return warnings


# ───────────── Orchestration ─────────────
def analyse(path: Path, db: Session) -> tuple[list[Page], list[Section], dict[str, Any]]:
    """Pure analysis (no writes): returns pages, sections and the review payload."""
    pages = analyse_pdf(path)
    sections, payload = analyse_pages(pages, db)
    return pages, sections, payload


def analyse_pages(pages: list[Page], db: Session) -> tuple[list[Section], dict[str, Any]]:
    """Everything after OCR (also used to replay saved OCR while tuning rules)."""
    templates = load_templates(db)
    sections = split_sections(pages, templates)
    index = CategoryIndex.load(db)
    candidates = collect_candidates(sections, pages, templates)
    fields = best_values(candidates)
    people = team_people(candidates, fields)
    checks, check_warnings = checkbox_suggestions(sections, index)
    inferred, hints, infer_warnings = infer(fields, sections, index)
    payload = {
        "fields": fields,
        "inferred": {k: _json(v) for k, v in inferred.items()},
        "people": people,
        "checks": checks,
        "hints": hints,
        "budget_lines": _json(installments(candidates, fields)),
        "warnings": field_warnings(fields, candidates, people) + check_warnings + infer_warnings,
        "sections": [
            {
                "attachment_no": s.attachment_no,
                "template": s.template.name if s.template else None,
                "pages": [p.number for p in s.pages],
            }
            for s in sections
        ],
    }
    return sections, payload


def process_version(db: Session, version_id: uuid.UUID) -> None:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        log.warning("version %s no longer exists; skipping", version_id)
        return
    document = db.get(Document, version.document_id)
    side_paper = version.purpose != VersionPurpose.MAIN  # closing / cancel / change memo
    # Proposal-development grants and programme papers are prose memos (DESIGN §11).
    memo = document.kind in (DocKind.PROPOSAL_DEV, DocKind.OTHER)
    version.ocr_status = OcrStatus.RUNNING
    db.commit()

    work_dir = get_settings().work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"{version.id.hex}.pdf"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            for chunk in read_version(version):
                handle.write(chunk)
        if memo:
            pages, sections = analyse_pdf(path), []
            payload = proposal.extract(pages)
            if number := proposal.received_no(version.original_filename):
                payload["fields"].setdefault("received_no", {"value": number, "page": 1})
        elif side_paper:
            pages, sections = analyse_pdf(path), []
            payload = closure.extract(pages)
        else:
            pages, sections, payload = analyse(path, db)
    finally:
        path.unlink(missing_ok=True)  # plaintext never outlives the run

    db.execute(delete(DocumentPage).where(DocumentPage.version_id == version.id))
    db.execute(delete(DocumentSection).where(DocumentSection.version_id == version.id))
    for page in pages:
        printed = PRINTED_PAGE.search(" ".join(ln.text for ln in page.footer))
        db.add(
            DocumentPage(
                version_id=version.id,
                page_no=page.number,
                printed_page_no=int(printed[1]) if printed else None,
                text=page.text,
                words={"words": word_dicts(page.lines)},
                checkboxes={
                    "boxes": [
                        {
                            "x": b.x,
                            "y": b.y,
                            "w": b.w,
                            "h": b.h,
                            "fill": round(b.fill, 3),
                            "checked": b.checked,
                            "heading": b.heading,
                            "label": b.row_label,
                        }
                        for b in page.boxes
                    ]
                },
                ocr_confidence=round(page.confidence, 1),
            )
        )
    for section in sections:
        db.add(
            DocumentSection(
                version_id=version.id,
                attachment_no=section.attachment_no,
                heading=section.heading,
                page_from=section.pages[0].number,
                page_to=section.pages[-1].number,
                template_id=section.template.id if section.template else None,
                match_score=section.score,
            )
        )
    version.extracted_fields = payload
    version.ocr_status = OcrStatus.DONE
    db.flush()
    if document.current_version_id == version.id or side_paper:
        if document.status == DocStatus.PROCESSING and not side_paper:
            document.status = DocStatus.NEEDS_REVIEW
        document.search_text = search_text.build(db, document)
    db.commit()
    log.info(
        "version %s: %d pages, %d sections, %d warnings",
        version.id,
        len(pages),
        len(sections),
        len(payload["warnings"]),
    )
