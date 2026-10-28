"""Split a PDF into sections (contract body, เอกสารแนบหมายเลข N) by classifying each page.

Keywords decide; the attachment marker is only a hint, because the real contract page itself
carries a boxed 'เอกสารแนบ 1' label (DESIGN §6 step 4).
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from dbresearch.autofill.page import Page

MARKER = re.compile(r"เอกสารแนบ(?:หมายเลข)?(?:ที่)?(\d{1,2})")
MARKER_ZONE = 0.22  # markers sit in the top fifth of the page
HEADER_ZONE = 0.35  # a keyword here counts double (it is the page's heading)
KEYWORD_FUZZY_MIN = 95  # strict: 'งบประมาณรวม' must not match 'งบประมาณรายได้'


@dataclass(frozen=True)
class TemplateSpec:
    id: uuid.UUID
    name: str
    attachment_no: int | None
    kind: str | None
    funding_type: str | None
    keywords: tuple[str, ...]
    min_score: float
    rules: tuple[dict[str, Any], ...]
    checkbox_groups: bool
    priority: int


@dataclass
class Section:
    template: TemplateSpec | None
    attachment_no: int | None
    pages: list[Page] = field(default_factory=list)
    score: float = 0.0

    @property
    def heading(self) -> str | None:
        first = self.pages[0]
        for line in first.body:
            if line.conf >= 60 and len(line.text) > 6 and not MARKER.search(_compact(line.text)):
                return line.text[:200]
        return None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def find_marker(page: Page) -> int | None:
    top = _compact(" ".join(ln.text for ln in page.body if ln.top < page.height * MARKER_ZONE))
    match = MARKER.search(top)
    return int(match[1]) if match else None


def _has(keyword: str, text: str) -> bool:
    key = _compact(keyword)
    return key in text or fuzz.partial_ratio(key, text) >= KEYWORD_FUZZY_MIN


def score(template: TemplateSpec, page: Page, marker: int | None) -> float:
    header = _compact(" ".join(ln.text for ln in page.body if ln.top < page.height * HEADER_ZONE))
    body = _compact(" ".join(ln.text for ln in page.body))
    hits = sum(2 if _has(k, header) else 1 if _has(k, body) else 0 for k in template.keywords)
    if hits == 0:
        return 0.0
    if template.attachment_no is not None and marker is not None:
        hits += 2 if marker == template.attachment_no else -1
    return float(hits)


def split_sections(pages: list[Page], templates: list[TemplateSpec]) -> list[Section]:
    sections: list[Section] = []
    for page in pages:
        marker = find_marker(page)
        ranked = sorted(
            ((score(t, page, marker), t.priority, t) for t in templates),
            key=lambda r: (r[0], r[1]),
            reverse=True,
        )
        best_score, _, best = ranked[0] if ranked else (0.0, 0, None)
        template = best if best is not None and best_score >= best.min_score else None
        current = sections[-1] if sections else None

        if template is not None:
            same = current is not None and current.template == template
            if same and (marker is None or marker == current.attachment_no):
                current.pages.append(page)
                continue
            number = template.attachment_no if template.attachment_no is not None else None
            if template.attachment_no is not None and marker is not None:
                number = marker
            sections.append(Section(template, number, [page], best_score))
        elif current is not None and (marker is None or marker == current.attachment_no):
            current.pages.append(page)  # continuation page of the running section
        else:
            sections.append(Section(None, marker, [page]))
    return sections
