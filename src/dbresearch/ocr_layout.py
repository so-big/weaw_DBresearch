"""Turn Tesseract word boxes into text lines with *real* spaces.

Tesseract splits Thai into small clusters ("สั ญ ญ า"). Joining them with spaces breaks every
label match; dropping all spaces loses real phrase breaks. Instead, a space is inserted only
where the horizontal gap between two boxes is wide relative to the line's text height.
Thresholds were measured on the first real scan (gap/height valley between 0.4 and 0.5).
"""

import re
import statistics
from dataclasses import dataclass

from dbresearch.textnorm import normalize

_THAI = re.compile(r"[฀-๿]")
# Gap / median word height above which a space is real.
THAI_SPACE_RATIO = 0.45  # between two Thai clusters
OTHER_SPACE_RATIO = 0.2  # when either side is Latin/digits/punctuation
MIN_LINE_CONFIDENCE = 50.0  # lines below this are usually watermark or seal noise


@dataclass(frozen=True)
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float


@dataclass(frozen=True)
class Line:
    text: str
    words: tuple[Word, ...]
    conf: float

    @property
    def left(self) -> int:
        return min(w.left for w in self.words)

    @property
    def top(self) -> int:
        return min(w.top for w in self.words)


def join_words(words: list[Word]) -> str:
    """Join one line's words left to right, keeping only wide gaps as spaces."""
    if not words:
        return ""
    ordered = sorted(words, key=lambda w: w.left)
    height = statistics.median(w.height for w in ordered) or 1
    parts = [ordered[0].text]
    for prev, word in zip(ordered, ordered[1:], strict=False):
        gap = word.left - (prev.left + prev.width)
        both_thai = bool(_THAI.search(prev.text[-1:]) and _THAI.search(word.text[:1]))
        ratio = THAI_SPACE_RATIO if both_thai else OTHER_SPACE_RATIO
        parts.append(" " if gap > ratio * height else "")
        parts.append(word.text)
    return "".join(parts)


def build_lines(data: dict[str, list]) -> list[Line]:
    """Group `pytesseract.image_to_data(..., output_type=DICT)` output into normalised lines."""
    groups: dict[tuple[int, int, int], list[Word]] = {}
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not text.strip() or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(
            Word(
                text.strip(),
                data["left"][i],
                data["top"][i],
                data["width"][i],
                data["height"][i],
                conf,
            )
        )
    lines = []
    for words in groups.values():
        text = normalize(join_words(words))
        if text:
            conf = statistics.fmean(w.conf for w in words)
            lines.append(Line(text, tuple(words), conf))
    return sorted(lines, key=lambda line: (line.top, line.left))


def page_text(lines: list[Line]) -> str:
    """Searchable page text: confident lines only, top to bottom."""
    return "\n".join(line.text for line in lines if line.conf >= MIN_LINE_CONFIDENCE)
