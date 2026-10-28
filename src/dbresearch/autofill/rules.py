"""Field-rule engine: turn OCR lines into candidate values (DESIGN §6 step 6).

Rules live in `extraction_templates.field_rules` as {"rules": [...]}. Each rule:

    {"field": "title", "layout": "label", "labels": ["โครงการ"], "continue": 1,
     "post": ["strip_leaders"]}

Layouts:
- label    value after a label at the start of a line (fuzzy ≥ 88), else the next line;
           `continue` = how many more indented lines belong to the value
- footer   regex over every page's footer; majority vote across pages
- sentence regex over the section's running text (contract clauses)
- team     the repeated research-team block (ชื่อ – สกุล / หน่วยงาน / บทบาท / สัดส่วน %)

Optional keys: `pattern` + `group` (regex and capture group), `words_group` (capture group
with the amount in Thai words, checked against the number), `post` (post-processors).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from dbresearch.autofill import thai
from dbresearch.autofill.page import Page
from dbresearch.ocr_layout import Line

LABEL_MIN = 88
_NUMBERING = re.compile(r"^[\d.\s]+")
_SEPARATORS = " :：-–"


@dataclass
class Candidate:
    field: str
    value: Any
    confidence: float
    page: int
    layout: str
    extra: dict[str, Any] = field(default_factory=dict)


def match_label(label: str, text: str) -> tuple[float, int] | None:
    """Fuzzy-match `label` at the start of `text` (spaces ignored, numbering skipped).

    Returns (score, index in `text` where the value begins) or None.
    """
    skip = len(_NUMBERING.match(text)[0]) if _NUMBERING.match(text) else 0
    chars = [(c, i) for i, c in enumerate(text) if i >= skip and not c.isspace()]
    target = label.replace(" ", "")
    if not chars or not target:
        return None
    best: tuple[float, int] | None = None
    for size in range(max(1, len(target) - 2), min(len(chars), len(target) + 2) + 1):
        score = fuzz.ratio(target, "".join(c for c, _ in chars[:size]))
        if best is None or score > best[0]:
            best = (score, chars[size - 1][1] + 1)
    return best if best and best[0] >= LABEL_MIN else None


def _post(value: Any, steps: list[str]) -> Any:
    for step in steps:
        if value is None:
            return None
        if step == "strip_leaders":
            value = thai.strip_leaders(value)
        elif step == "compact":
            value = re.sub(r"\s+", "", value)
        elif step == "upper":
            value = value.upper()
        elif step == "be_year":
            value = thai.be_to_gregorian(int(value))
        elif step == "thai_date":
            value = thai.parse_thai_date(value)
        elif step == "money":
            value = thai.parse_money(value)
        elif step == "strip_brackets":
            value = re.sub(r"^\s*[\[(]|[\])]\s*$", "", value).strip()
        else:
            raise ValueError(f"unknown post-processor {step!r}")
    return value or None


def _apply_pattern(rule: dict, text: str) -> tuple[str, re.Match | None]:
    if "pattern" not in rule:
        return text, None
    match = re.search(rule["pattern"], text, re.DOTALL)
    if match is None:
        return "", None
    return match.group(rule.get("group", 0)), match


def _label_rule(rule: dict, pages: list[Page], other_labels: list[str]) -> list[Candidate]:
    found = []
    for page in pages:
        lines = page.body
        for index, line in enumerate(lines):
            hit = next(
                (h for label in rule["labels"] if (h := match_label(label, line.text))), None
            )
            # 'โครงการ :' is a label; 'โครงการวิจัยไม่เกิน…' (body text) is not.
            if hit is None or (hit[1] < len(line.text) and line.text[hit[1]] not in _SEPARATORS):
                continue
            score, start = hit
            parts = [line.text[start:].lstrip(_SEPARATORS)]
            follow = index + 1
            if not parts[0] and follow < len(lines):  # value on the next line
                parts = [lines[follow].text]
                follow += 1
            height = line.words[0].height if line.words else 40
            for nxt in lines[follow : follow + rule.get("continue", 0)]:
                indented = nxt.left > line.left + 0.5 * height
                if not indented or any(match_label(lab, nxt.text) for lab in other_labels):
                    break
                parts.append(nxt.text)
            raw, match = _apply_pattern(rule, " ".join(p for p in parts if p))
            value = _post(raw, rule.get("post", ["strip_leaders"]))
            if value is not None:
                conf = round(score / 100 * line.conf / 100, 3)
                found.append(Candidate(rule["field"], value, conf, page.number, "label"))
    return found


def _footer_rule(rule: dict, all_pages: list[Page]) -> list[Candidate]:
    votes: Counter[Any] = Counter()
    first_page: dict[Any, int] = {}
    for page in all_pages:
        raw, _ = _apply_pattern(rule, page.footer_text)
        value = _post(raw, rule.get("post", [])) if raw else None
        if value is not None:
            votes[value] += 1
            first_page.setdefault(value, page.number)
    pages_with_footer = sum(1 for p in all_pages if p.footer) or 1
    candidates = [
        Candidate(
            rule["field"],
            value,
            round(count / pages_with_footer, 3),
            first_page[value],
            "footer",
            {"votes": count},
        )
        for value, count in votes.most_common()
    ]
    if len(candidates) > 1:  # different values on different pages: let the pipeline warn
        for candidate in candidates:
            candidate.extra["conflict"] = [c.value for c in candidates]
    return candidates


def _sentence_rule(rule: dict, pages: list[Page]) -> list[Candidate]:
    found = []
    for page in pages:
        text = " ".join(line.text for line in page.body)
        for match in re.finditer(rule["pattern"], text, re.DOTALL):
            value = _post(match.group(rule.get("group", 1)), rule.get("post", []))
            if value is None:
                continue
            extra = {}
            if words_group := rule.get("words_group"):
                extra["words_amount"] = thai.words_to_amount(match.group(words_group) or "")
            conf = round(0.85 * page.confidence / 100, 3)
            found.append(Candidate(rule["field"], value, conf, page.number, "sentence", extra))
    return found


_ROLES = {"หัวหน้าโครงการ": "owner", "ผู้ร่วมวิจัย": "co_investigator", "นักวิจัย": "co_investigator"}
ROLE_MIN = 60  # role values sit on dotted lines and OCR badly; below this the role is inferred
# 'สัดส่วน' is often misread ('สัตส่วน'); the % value follows within a few characters.
_SHARE_LABEL = re.compile(r"ส\S{0,2}ส่วน")
_SHARE = re.compile(r"ส\S{0,2}ส่วน[^\d]{0,25}?(\d(?:\s?\d){0,2})(?!\d)")


def _role(text: str) -> str | None:
    compact = re.sub(r"[\s.…_,]+", "", text)
    if not compact:
        return None
    scores = {code: fuzz.partial_ratio(word, compact) for word, code in _ROLES.items()}
    code, best = max(scores.items(), key=lambda kv: kv[1])
    return code if best >= ROLE_MIN else None


def _team_rule(rule: dict, pages: list[Page]) -> list[Candidate]:
    """One candidate per person in the research-team block."""
    name_labels = rule.get("labels", ["ชื่อ - สกุล", "ชื่อ-สกุล"])
    found = []
    for page in pages:
        lines = page.body
        for index, line in enumerate(lines):
            hit = next((h for lab in name_labels if (h := match_label(lab, line.text))), None)
            if hit is None:
                continue
            rest = line.text[hit[1] :]
            share = _SHARE.search(rest)
            name_text = _SHARE_LABEL.split(rest)[0]
            prefix, name = thai.split_person(name_text)
            if not name:
                continue
            share_pct = float(share[1].replace(" ", "")) if share else None
            person: dict[str, Any] = {
                "prefix_th": prefix,
                "name": name,
                "share_pct": share_pct if share_pct is not None and share_pct <= 100 else None,
                "unit": None,
                "role": None,
            }
            for nxt in lines[index + 1 : index + 4]:
                if unit := match_label("หน่วยงาน", nxt.text):
                    person["unit"] = thai.strip_leaders(nxt.text[unit[1] :]) or None
                elif role := match_label("บทบาทในโครงการ", nxt.text):
                    person["role"] = _role(nxt.text[role[1] :])
            conf = round(hit[0] / 100 * line.conf / 100, 3)
            found.append(Candidate("team", person, conf, page.number, "team"))
    return found


def extract(rules: list[dict], section_pages: list[Page], all_pages: list[Page]) -> list[Candidate]:
    """Run a template's rules on one section (footer rules see the whole document)."""
    labels = [label for rule in rules for label in rule.get("labels", [])]
    candidates: list[Candidate] = []
    for rule in rules:
        layout = rule["layout"]
        if layout == "label":
            others = [lab for lab in labels if lab not in rule["labels"]]
            candidates += _label_rule(rule, section_pages, others)
        elif layout == "footer":
            candidates += _footer_rule(rule, all_pages)
        elif layout == "sentence":
            candidates += _sentence_rule(rule, section_pages)
        elif layout == "team":
            candidates += _team_rule(rule, section_pages)
        else:
            raise ValueError(f"unknown layout {layout!r}")
    return candidates


def lines_of(pages: list[Page]) -> list[Line]:
    return [line for page in pages for line in page.lines]
