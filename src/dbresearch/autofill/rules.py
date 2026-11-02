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

- names_en   English names in the researchers' CV part (ส่วน ค: '(ภาษาอังกฤษ) Mr. …'),
           paired with the Thai name just above
- installments  งวดที่ N จำนวน X บาท / (ร้อยละ P) condition … (budget attachment)

Optional keys: `pattern` + `group` (regex and capture group), `words_group` (capture group
with the amount in Thai words, checked against the number), `post` (post-processors);
label rules also take `stop` (line starts that end a wrapped value) and `reject` (regex:
values to skip, e.g. a person's name under an English-title label).
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
        elif step == "contract_no":
            value = thai.contract_no(value)
        elif step == "person":
            value = thai.clean_person(value)
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
            stops = other_labels + rule.get("stop", [])
            for nxt in lines[follow : follow + rule.get("continue", 0)]:
                indented = nxt.left > line.left + 0.5 * height
                if not indented or any(match_label(lab, nxt.text) for lab in stops):
                    break
                parts.append(nxt.text)
            raw, match = _apply_pattern(rule, " ".join(p for p in parts if p))
            value = _post(raw, rule.get("post", ["strip_leaders"]))
            reject = rule.get("reject")
            if value is not None and reject and re.search(reject, str(value)):
                continue
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
    total = sum(votes.values()) or 1
    candidates = [
        Candidate(
            rule["field"],
            value,
            round(min(1.0, 0.5 + 0.5 * count / total), 3) if count > 1 else 0.3,
            first_page[value],
            "footer",
            {"votes": count},
        )
        for value, count in votes.most_common()
    ]
    # A value the footers really disagree on (a wrong page in the PDF) shows up on several
    # pages. A single-page reading one character off the winner is an OCR slip, not a conflict.
    if candidates:
        top = candidates[0]
        real = [top] + [
            c
            for c in candidates[1:]
            if c.extra["votes"] >= 2 and not _one_char_off(str(c.value), str(top.value))
        ]
        if len(real) > 1:
            for candidate in real:
                candidate.extra["conflict"] = [c.value for c in real]
    return candidates


def _one_char_off(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) <= 1


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
# 'สัดส่วน' is often misread ('สัตส่วน', 'สัต ส่วน'); the % value follows within a few characters.
_SHARE_LABEL = re.compile(r"ส\S{0,2}\s?ส\S?วน")
# The share must stand alone: '10ป 3นนนน' is a misread '100' on a dotted line, so no value.
# A number in brackets right after the label is the misread '(%)', not the share.
_SHARE = re.compile(r"ส\S{0,2}\s?ส\S?วน[^\d]{0,25}?(?<!\()(\d(?:\s?\d){0,2})(?![\d฀-๿)])")
_NAME_LABEL = re.compile(r"^\S{0,3}[ชซข]\S?\S?อ\s*[-–]?\s*(?:\S{2,5}\s+)?")


def _role(text: str) -> str | None:
    compact = re.sub(r"[\s.…_,]+", "", text)
    if not compact:
        return None
    scores = {code: fuzz.partial_ratio(word, compact) for word, code in _ROLES.items()}
    code, best = max(scores.items(), key=lambda kv: kv[1])
    return code if best >= ROLE_MIN else None


def _team_name(text: str) -> str:
    """Name part of 'ชื่อ- สกุล <prefix> <name> สัดส่วนการทำวิจัย(%) 100'. The label itself
    OCRs badly ('ชื่อ- ana'), so start at the first rank/prefix when there is one."""
    text = thai.clean_person(_SHARE_LABEL.split(text)[0])
    positions = [text.find(p) for p in thai.PERSON_PREFIXES if p in text]
    if positions and min(positions) <= 16:
        return text[min(positions) :]
    return _NAME_LABEL.sub("", text)


def _team_rule(rule: dict, pages: list[Page]) -> list[Candidate]:
    """One candidate per person in the research-team block:

        ชื่อ- สกุล  <name>  สัดส่วนการทำวิจัย(%) 100
        หน่วยงาน    <unit>
        บทบาทในโครงการ  <role>

    Anchored on the หน่วยงาน + บทบาทในโครงการ pair, which OCRs far better than the name label.
    """
    found = []
    for page in pages:
        lines = page.body
        for index, line in enumerate(lines):
            unit = match_label("หน่วยงาน", line.text)
            if unit is None or index == 0:
                continue
            role_line = next(
                (n for n in lines[index + 1 : index + 3] if match_label("บทบาทในโครงการ", n.text)),
                None,
            )
            name_line = lines[index - 1]
            if role_line is None and not _SHARE_LABEL.search(name_line.text):
                continue  # 'หน่วยงานที่สังกัด' on a report cover, not a team entry
            prefix, name = thai.split_person(_team_name(name_line.text))
            if len(name) < 4 or any(match_label(lab, name) for lab in _NOT_NAMES):
                continue  # the value sits in another column: only the label was read
            share = _SHARE.search(name_line.text)
            share_pct = float(share[1].replace(" ", "")) if share else None
            role = None
            if role_line is not None:
                role = _role(role_line.text[match_label("บทบาทในโครงการ", role_line.text)[1] :])
            person: dict[str, Any] = {
                "prefix_th": prefix,
                "name": name,
                "share_pct": share_pct if share_pct is not None and share_pct <= 100 else None,
                "unit": thai.clean_person(line.text[unit[1] :]) or None,
                "role": role,
            }
            conf = round(unit[0] / 100 * name_line.conf / 100, 3)
            found.append(Candidate("team", person, conf, page.number, "team"))
    return found


_NOT_NAMES = ("สกุล", "หน่วยงาน", "ชื่อ", "บทบาท")
_HONORIFIC = re.compile(r"^(?:mr|mrs|miss|ms|dr|asst|assoc|prof)\b[\s.,:;/]*", re.IGNORECASE)
_EN_NAME = re.compile(r"^[A-Za-z][A-Za-z'\-]+(?: [A-Za-z][A-Za-z'\-]+){1,3}$")
_TH_OPTIONS = re.compile(r"^.*/\s*")  # 'นาย / นาง / นางสาว <name>': keep what follows the last '/'


def _names_en_rule(rule: dict, pages: list[Page]) -> list[Candidate]:
    """English names from the CV part, each paired with the Thai name on the line above."""
    found = []
    for page in pages:
        lines = page.body
        for index, line in enumerate(lines):
            text = line.text
            compact = text.replace(" ", "")
            if "อังกฤษ" not in compact or ")" not in text:
                continue
            value = text[text.index(")") + 1 :].strip(" :;,.")
            if not re.match(r"(?i)(?:mr|mrs|miss|ms|dr|asst|assoc|prof)\b", value):
                continue  # a title, not a person
            while (stripped := _HONORIFIC.sub("", value)) != value:
                value = stripped
            value = re.sub(r"\s+", " ", value).strip(" .,")
            if not _EN_NAME.match(value):
                continue
            if value.isupper():
                value = value.title()
            name_th = None
            for above in reversed(lines[max(0, index - 3) : index]):
                if "ภาษาไทย" in above.text.replace(" ", ""):
                    raw = above.text[above.text.index(")") + 1 :] if ")" in above.text else ""
                    name_th = thai.split_person(thai.clean_person(_TH_OPTIONS.sub("", raw)))[1]
                    break
            found.append(
                Candidate(
                    "team_en",
                    {"name_th": name_th or None, "name_en": value},
                    round(line.conf / 100, 3),
                    page.number,
                    "names_en",
                )
            )
    return found


# 'งวดที่ 1 จำนวน 40,000 บาท …'; the amount may sit in another column (then it's computed
# from the percentage) and 'งวดที่' itself can OCR as capitals ('VIAN 2 จานวน').
_INSTALLMENT = re.compile(r"^(?:งวด\s*ท\S{0,2}|[A-Z]{3,5}(?=\s*\d\s*จ))\s*(\d{1,2})(?!\d)(.*)$")
_AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d\d)?\s*(?:บาท|[A-Za-z]{1,4})?")
_TAIL_AMOUNT = re.compile(r"จ\S{0,2}นวน(?:เงิน)?\s*(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d\d)?\s*บาท")
_PERCENT = re.compile(r"[รจ]\S?อยละ\s*(\d{1,3}(?:\.\d+)?)")
_WORDS_AMOUNT = re.compile(r"^\s*\([^)]*\)")
_NOTE = re.compile(r"^หมายเหตุ")
_DEADLINE = re.compile(rf"(?:ไม่เกิน|ภายใน)\s*วันท\S{{0,2}}\s*({thai.DATE_RE})")


def _installments_rule(rule: dict, pages: list[Page]) -> list[Candidate]:
    """งวดที่ 1 จำนวน 40,000 บาท (สี่หมื่นบาทถ้วน) / (ร้อยละ 40) จ่ายภายใน 30 วัน หลัง…

    Also the external order 'งวดที่ 1 (ร้อยละ 70) จำนวนเงิน X บาท'. A deadline in the
    หมายเหตุ ('ไม่เกินวันที่ 19 มกราคม 2569') is the due date of the last installment.
    """
    lines = [line for page in pages for line in page.body]
    first_page = pages[0].number if pages else 0
    items: list[dict[str, Any]] = []
    tail: list[str] | None = None
    note: list[str] = []
    for line in lines:
        text = line.text.strip()
        if match := _INSTALLMENT.match(text):
            rest = match[2]
            amount_match = _AMOUNT.search(rest)
            amount = thai.parse_money(amount_match[1]) if amount_match else None
            if amount_match:  # keep '(ร้อยละ 70)' written before the amount, drop the words
                rest = rest[: amount_match.start()] + _WORDS_AMOUNT.sub(
                    "", rest[amount_match.end() :]
                )
            rest = re.sub(r"^\s*จ\S{0,2}นวน(?:เงิน)?", "", rest)
            tail = [rest]
            items.append({"no": int(match[1]), "amount": amount, "tail": tail})
            continue
        if _NOTE.match(text):
            tail = None
            note.append(text)
            continue
        if note and len(note) < 3:
            note.append(text)
        elif tail is not None and len(tail) < 6:
            tail.append(text)
    if not items:
        return []
    lines_out = []
    for item in items:
        joined = re.sub(r"\s+", " ", " ".join(t for t in item["tail"] if t)).strip()
        if item["amount"] is None and (found := _TAIL_AMOUNT.search(joined)):
            # Amount printed in its own column: it comes out a line or two later.
            item["amount"] = thai.parse_money(found[1])
            joined = (
                joined[: found.start()] + _WORDS_AMOUNT.sub("", joined[found.end() :])
            ).strip()
        percent = _PERCENT.search(joined)
        condition = _PERCENT.sub("", joined)
        condition = re.sub(r"^[\s().,]+|[\s(]+$", "", re.sub(r"\(\s*\)", "", condition)).strip()
        lines_out.append(
            {
                "line_type": "installment",
                "label": f"งวดที่ {item['no']}",
                "amount": item["amount"],
                "percent": float(percent[1]) if percent else None,
                "due_date": None,
                "condition": condition or None,
            }
        )
    if deadline := _DEADLINE.search(" ".join(note)):
        lines_out[-1]["due_date"] = thai.parse_thai_date(deadline[1])
    conf = round(0.8 * sum(p.confidence for p in pages) / len(pages) / 100, 3)
    return [Candidate("budget_lines", lines_out, conf, first_page, "installments")]


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
        elif layout == "names_en":
            candidates += _names_en_rule(rule, section_pages)
        elif layout == "installments":
            candidates += _installments_rule(rule, section_pages)
        else:
            raise ValueError(f"unknown layout {layout!r}")
    return candidates


def lines_of(pages: list[Page]) -> list[Line]:
    return [line for page in pages for line in page.lines]


LAYOUTS = {"label", "footer", "sentence", "team", "names_en", "installments"}
POST_STEPS = {
    "strip_leaders",
    "compact",
    "upper",
    "be_year",
    "thai_date",
    "money",
    "strip_brackets",
    "contract_no",
    "person",
}
FIELDS = {
    "title",
    "title_en",
    "reference_no",
    "owner",
    "fiscal_year",
    "document_date",
    "effective_from",
    "effective_to",
    "budget_total",
    "team",
    "team_en",
    "budget_lines",
}


def validate_rules(rules: list[dict]) -> None:
    """Reject template rules the engine can't run (raises ValueError with a readable reason)."""
    for i, rule in enumerate(rules, 1):
        where = f"rule {i}"
        if rule.get("field") not in FIELDS:
            raise ValueError(f"{where}: unknown field {rule.get('field')!r}")
        if rule.get("layout") not in LAYOUTS:
            raise ValueError(f"{where}: unknown layout {rule.get('layout')!r}")
        if rule["layout"] == "label" and not rule.get("labels"):
            raise ValueError(f"{where}: a label rule needs 'labels'")
        if rule["layout"] in {"footer", "sentence"} and not rule.get("pattern"):
            raise ValueError(f"{where}: a {rule['layout']} rule needs 'pattern'")
        if pattern := rule.get("pattern"):
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"{where}: bad pattern ({exc})") from exc
            if rule.get("group", 0) > compiled.groups:
                raise ValueError(f"{where}: pattern has no group {rule['group']}")
        unknown = set(rule.get("post", [])) - POST_STEPS
        if unknown:
            raise ValueError(f"{where}: unknown post-processor(s) {sorted(unknown)}")
