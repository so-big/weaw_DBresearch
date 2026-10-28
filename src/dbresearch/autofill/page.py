"""Per-page analysis: render at 300 dpi, OCR into gap-joined lines, detect checkboxes.

Thresholds were measured in the Phase 1 spikes (DESIGN §6 "Spike results").
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract

from dbresearch.ocr_layout import Line, Word, build_lines, join_words, page_text
from dbresearch.textnorm import normalize

DPI = 300
MM = DPI / 25.4
TESSERACT = "--oem 1 --psm 3"
FOOTER_ZONE = 0.88  # lines below 88 % of the page height belong to the footer

# Checkboxes
MIN_SIDE, MAX_SIDE = 3.0 * MM, 7.0 * MM
INSET = 0.2
CHECKED_MIN, EMPTY_MAX = 0.12, 0.03


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    fill: float
    heading: str = ""
    row_label: str = ""
    strip_label: str | None = None  # read lazily, only when the row label doesn't match

    @property
    def checked(self) -> bool | None:
        if self.fill >= CHECKED_MIN:
            return True
        return False if self.fill <= EMPTY_MAX else None


@dataclass
class Page:
    number: int  # 1-based position in the PDF
    width: int
    height: int
    lines: list[Line]
    boxes: list[Box] = field(default_factory=list)
    image: np.ndarray | None = None  # kept only while the version is processed

    @property
    def body(self) -> list[Line]:
        return [line for line in self.lines if line.top < self.height * FOOTER_ZONE]

    @property
    def footer(self) -> list[Line]:
        return [line for line in self.lines if line.top >= self.height * FOOTER_ZONE]

    @property
    def text(self) -> str:
        return page_text(self.lines)

    @property
    def confidence(self) -> float:
        words = [w for line in self.lines for w in line.words]
        return sum(w.conf for w in words) / len(words) if words else 0.0


def ocr_lines(image: np.ndarray, config: str = TESSERACT) -> list[Line]:
    data = pytesseract.image_to_data(
        image, lang="tha+eng", config=config, output_type=pytesseract.Output.DICT
    )
    return build_lines(data)


def analyse_pdf(path: Path) -> list[Page]:
    pdf = pdfium.PdfDocument(path)
    try:
        pages = []
        for index in range(len(pdf)):
            gray = pdf[index].render(scale=DPI / 72, grayscale=True).to_numpy()
            if gray.ndim == 3:
                gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
            lines = ocr_lines(gray)
            page = Page(index + 1, gray.shape[1], gray.shape[0], lines, image=gray)
            page.boxes = find_boxes(gray)
            for box in page.boxes:
                box.heading = heading_for(box, page.boxes, lines)
                box.row_label = row_label(box, lines)
            pages.append(page)
        return pages
    finally:
        pdf.close()


# ───────────── Checkboxes ─────────────
def has_four_sides(patch: np.ndarray, band: float = 0.15, coverage: float = 0.8) -> bool:
    """True if all four edges of the patch are (almost) continuous ink lines, like a box."""
    h, w = patch.shape
    bh, bw = max(1, int(h * band)), max(1, int(w * band))
    sides = (
        patch[:bh, :].any(axis=0),
        patch[-bh:, :].any(axis=0),
        patch[:, :bw].any(axis=1),
        patch[:, -bw:].any(axis=1),
    )
    return all(side.mean() >= coverage for side in sides)


def find_boxes(gray: np.ndarray) -> list[Box]:
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 15
    )
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[Box] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE and 0.75 <= w / h <= 1.33):
            continue
        approx = cv2.approxPolyDP(contour, 0.06 * cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        if cv2.contourArea(contour) < 0.7 * w * h or not has_four_sides(ink[y : y + h, x : x + w]):
            continue
        dx, dy = int(w * INSET), int(h * INSET)
        inner = ink[y + dy : y + h - dy, x + dx : x + w - dx]
        fill = float(np.count_nonzero(inner)) / max(inner.size, 1)
        same = next((b for b in boxes if abs(b.x - x) < w * 0.3 and abs(b.y - y) < h * 0.3), None)
        if same is None:
            boxes.append(Box(x, y, w, h, fill))
        elif w * h > same.w * same.h:
            same.x, same.y, same.w, same.h, same.fill = x, y, w, h, fill
    return sorted(boxes, key=lambda b: (b.y, b.x))


def row_label(box: Box, lines: list[Line]) -> str:
    """Page-OCR words on the box's row, right of the box."""
    mid = box.y + box.h / 2
    words = [
        w
        for line in lines
        for w in line.words
        if w.left > box.x + box.w * 0.9
        and w.top <= mid <= w.top + w.height
        and w.left < box.x + box.w + 90 * MM
    ]
    return normalize(join_words(words))


def strip_label(box: Box, gray: np.ndarray) -> str:
    """Re-OCR the strip right of the box as one line (page OCR sometimes drops option rows).

    Tries with and without strikethrough removal and keeps the more confident read.
    """
    top, bottom = max(0, box.y - box.h // 3), box.y + box.h + box.h // 3
    left, right = box.x + box.w + int(0.5 * MM), box.x + box.w + int(90 * MM)
    strip = gray[top:bottom, left:right]
    ink = cv2.threshold(strip, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1))
    long_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    cleaned = strip.copy()
    cleaned[long_lines > 0] = 255
    reads = []
    for image in (strip, cleaned):
        words = [w for line in ocr_lines(image, "--oem 1 --psm 7") for w in line.words]
        conf = sum(w.conf for w in words) / len(words) if words else 0.0
        reads.append((normalize(join_words(words)), conf))
    return max(reads, key=lambda r: r[1])[0]


def heading_for(box: Box, boxes: list[Box], lines: list[Line]) -> str:
    """Nearest line above the box, further left, that is not itself an option row.

    Numbering ('1.') and bracketed instructions ('(ระบุ…เพียงข้อเดียว)') are removed.
    """

    def is_option_row(line: Line) -> bool:
        bottom = max(w.top + w.height for w in line.words)
        return any(line.top <= b.y + b.h / 2 <= bottom for b in boxes)

    above = [
        line
        for line in lines
        if line.top < box.y - box.h * 0.5
        and line.left < box.x - box.w * 0.3
        and not is_option_row(line)
    ]
    if not above:
        return ""
    heading = re.sub(r"^[\d.\s]+", "", above[-1].text)
    return re.sub(r"\(.*?\)", "", heading).strip()


def word_dicts(lines: list[Line]) -> list[list]:
    """Compact word storage for document_pages.words: [text, x, y, w, h, conf]."""
    return [
        [w.text, w.left, w.top, w.width, w.height, round(w.conf, 1)]
        for line in lines
        for w in line.words
    ]


__all__ = ["Box", "Page", "Word", "analyse_pdf", "strip_label", "word_dicts"]
