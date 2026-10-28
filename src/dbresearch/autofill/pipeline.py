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
from dbresearch.autofill import thai
from dbresearch.autofill.categories import CategoryIndex, Match
from dbresearch.autofill.page import Page, analyse_pdf, strip_label, word_dicts
from dbresearch.autofill.rules import Candidate, extract
from dbresearch.autofill.sections import Section, TemplateSpec, split_sections
from dbresearch.config import get_settings
from dbresearch.documents import read_version
from dbresearch.models import (
    DocStatus,
    Document,
    DocumentPage,
    DocumentSection,
    DocumentVersion,
    ExtractionTemplate,
    OcrStatus,
)

log = logging.getLogger("dbresearch.autofill")

# Contract no. R + B.E. year + series letter + running no. (department convention)
CONTRACT_NO = re.compile(r"^R(\d{4})([A-Z])(\d+)$")
FUNDING_LETTERS = {"E": "internal", "A": "external"}
INTERNAL_HINT = re.compile(r"งบประมาณรายได้")
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


def best_values(candidates: list[Candidate]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for name in {c.field for c in candidates if c.field != "team"}:
        ranked = sorted(
            (c for c in candidates if c.field == name), key=lambda c: c.confidence, reverse=True
        )
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


def same_person(a: str, b: str) -> bool:
    return fuzz.ratio(re.sub(r"\s+", "", a), re.sub(r"\s+", "", b)) >= SAME_NAME_MIN


def team_people(candidates: list[Candidate], fields: dict[str, dict]) -> list[dict]:
    """Research team from the proposal form, plus the footer owner if not already listed."""
    people: list[dict] = []
    for c in sorted((c for c in candidates if c.field == "team"), key=lambda c: c.page):
        if not any(same_person(c.value["name"], p["name"]) for p in people):
            people.append({**c.value, "page": c.page, "confidence": c.confidence})
    owner = fields.get("owner", {}).get("value")
    owner_name = thai.split_person(owner)[1] if owner else None
    _infer_roles(people, owner_name)
    if owner_name and not any(same_person(owner_name, p["name"]) for p in people):
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

    kinds = {s.template.kind for s in sections if s.template and s.template.kind}
    if len(kinds) == 1:
        inferred["kind"] = kinds.pop()

    ref = fields.get("reference_no", {}).get("value")
    letter_funding = None
    ref_year = None
    if ref and (m := CONTRACT_NO.match(ref)):
        ref_year, letter_funding = int(m[1]), FUNDING_LETTERS.get(m[2])
    text_funding = "internal" if INTERNAL_HINT.search(re.sub(r"\s+", "", header)) else None
    inferred["funding_type"] = letter_funding or text_funding
    if letter_funding and text_funding and letter_funding != text_funding:
        warnings.append(
            {"code": "funding_mismatch", "contract_no": letter_funding, "header": text_funding}
        )

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


def field_warnings(
    fields: dict[str, dict], candidates: list[Candidate], people: list[dict]
) -> list[dict]:
    warnings = []
    budget = fields.get("budget_total", {})
    words, number = budget.get("words_amount"), budget.get("value")
    if words is not None and number is not None and Decimal(str(words)) != Decimal(number):
        warnings.append({"code": "amount_words_mismatch", "digits": number, "words": words})
    refs = {c.value for c in candidates if c.field == "reference_no"}
    if len(refs) > 1:
        warnings.append({"code": "multiple_contract_numbers", "values": sorted(refs)})
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
    return pages, sections, payload


def process_version(db: Session, version_id: uuid.UUID) -> None:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        log.warning("version %s no longer exists; skipping", version_id)
        return
    document = db.get(Document, version.document_id)
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
    if document.current_version_id == version.id:
        if document.status == DocStatus.PROCESSING:
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
