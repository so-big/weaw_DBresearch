"""Checkbox spike: find printed boxes on a page image and decide checked / unchecked.

    docker compose exec worker python spikes/checkbox_probe.py /samples/<file>.pdf --page 3

Prints each box found (position, size, interior ink ratio, state), the label to its right and
the group heading above it (form labels only; no personal data on these lines).
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract
from rapidfuzz import fuzz, process

from dbresearch.ocr_layout import Line, Word, build_lines, join_words
from dbresearch.textnorm import normalize

DPI = 300
MM = DPI / 25.4
MIN_SIDE, MAX_SIDE = 3.0 * MM, 7.0 * MM  # printed checkboxes are ~3.5–5 mm; bold letters < 3 mm
INSET = 0.2  # ignore the border: measure ink only in the inner 60 % of the box
CHECKED_MIN, EMPTY_MAX = 0.12, 0.03  # interior ink ratio; in between = unsure → no suggestion


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    fill: float

    @property
    def state(self) -> str:
        if self.fill >= CHECKED_MIN:
            return "CHECKED"
        return "empty" if self.fill <= EMPTY_MAX else "unsure"


def has_four_sides(patch: np.ndarray, band: float = 0.15, coverage: float = 0.8) -> bool:
    """True if all four edges of the patch are (almost) continuous ink lines, like a box."""
    h, w = patch.shape
    bh, bw = max(1, int(h * band)), max(1, int(w * band))
    sides = (
        patch[:bh, :].any(axis=0),  # top: does each column have ink near the top edge?
        patch[-bh:, :].any(axis=0),  # bottom
        patch[:, :bw].any(axis=1),  # left
        patch[:, -bw:].any(axis=1),  # right
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
        # A box outline fills its bounding rect and has four straight sides; letters don't.
        if cv2.contourArea(contour) < 0.7 * w * h or not has_four_sides(ink[y : y + h, x : x + w]):
            continue
        dx, dy = int(w * INSET), int(h * INSET)
        inner = ink[y + dy : y + h - dy, x + dx : x + w - dx]
        fill = float(np.count_nonzero(inner)) / max(inner.size, 1)
        # Outer and inner edges of one printed border give two contours: keep the outer one.
        same = next((b for b in boxes if abs(b.x - x) < w * 0.3 and abs(b.y - y) < h * 0.3), None)
        if same is None:
            boxes.append(Box(x, y, w, h, fill))
        elif w * h > same.w * same.h:
            same.x, same.y, same.w, same.h, same.fill = x, y, w, h, fill
    return sorted(boxes, key=lambda b: (b.y, b.x))


# Seed categories from DESIGN §6 (form option labels, not personal data).
GROUPS = {
    "grant_type": (["ประเภททุน"], ["นักวิจัยรุ่นใหม่", "ทุนวิจัยสำหรับนักวิจัยที่มีประสบการณ์ด้านการวิจัย"]),
    "research_type": (
        ["ประเภทการวิจัย", "ประเภทวิจัย"],
        ["เพื่อแก้ปัญหา", "เพื่อการวางแผนพัฒนา", "เพื่อการประกันคุณภาพ", "พื้นฐาน", "ทดลองและพัฒนา"],
    ),
    "research_group": (
        ["กลุ่มการวิจัย"],
        [
            "นิสิต / นักศึกษา",
            "บุคลากร",
            "หลักสูตร / โปรแกรมการศึกษา",
            "การเงิน / งบประมาณ",
            "อาคารสถานที่ และสิ่งอำนวยความสะดวก",
            "วิทยาศาสตร์เทคโนโลยี",
            "วิทยาศาสตร์สุขภาพ",
        ],
    ),
    "discipline": (["สาขาวิชาการ"], ["วิศวกรรมศาสตร์และอุตสาหกรรมวิจัย", "นิติศาสตร์"]),
}
GROUP_MIN, OPTION_MIN, OPTION_MARGIN = 80, 70, 10


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\(.*?\)", "", text))


def match_group(heading: str) -> str | None:
    best = max(
        (
            (key, fuzz.ratio(_compact(alias), _compact(heading)[: len(_compact(alias)) + 2]))
            for key, (aliases, _) in GROUPS.items()
            for alias in aliases
        ),
        key=lambda kv: kv[1],
    )
    return best[0] if best[1] >= GROUP_MIN else None


def match_option(group: str, label: str) -> tuple[str | None, float]:
    """Best option in the group, only if clearly better than the runner-up."""
    options = GROUPS[group][1]
    ranked = process.extract(
        _compact(label), [_compact(o) for o in options], scorer=fuzz.ratio, limit=2
    )
    best, runner = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0, None))
    if best[1] >= OPTION_MIN and best[1] - runner[1] >= OPTION_MARGIN:
        return options[best[2]], best[1]
    return None, best[1]


def row_label(box: Box, lines: list[Line]) -> str:
    """Page-OCR words on the box's row, right of the box (page OCR reads clean scans best)."""
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
    """OCR the strip right of the box as one line, after erasing strikethrough lines.

    Page-level OCR sometimes drops option lines entirely, so each label is read on its own.
    """
    top, bottom = max(0, box.y - box.h // 3), box.y + box.h + box.h // 3
    left, right = box.x + box.w + int(0.5 * MM), box.x + box.w + int(90 * MM)
    strip = gray[top:bottom, left:right]
    ink = cv2.threshold(strip, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1))
    long_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    cleaned = strip.copy()
    cleaned[long_lines > 0] = 255
    # Strikethrough removal helps struck labels but can hurt clean ones: keep the surer read.
    reads = [_read_line(img) for img in (strip, cleaned)]
    return max(reads, key=lambda r: r[1])[0]


def _read_line(image: np.ndarray) -> tuple[str, float]:
    data = pytesseract.image_to_data(
        image, lang="tha+eng", config="--oem 1 --psm 7", output_type=pytesseract.Output.DICT
    )
    words = [
        Word(
            text.strip(),
            data["left"][i],
            data["top"][i],
            data["width"][i],
            data["height"][i],
            float(data["conf"][i]),
        )
        for i, text in enumerate(data["text"])
        if text.strip() and float(data["conf"][i]) >= 0
    ]
    conf = sum(w.conf for w in words) / len(words) if words else 0.0
    return normalize(join_words(words)), conf


def heading_for(box: Box, boxes: list[Box], lines: list[Line]) -> str:
    """Nearest line above the box, further left, that is not itself an option row."""

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
    return re.sub(r"^[\d.\s]+", "", above[-1].text) if above else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, required=True)
    args = parser.parse_args()

    page = pdfium.PdfDocument(args.pdf)[args.page - 1]
    gray = page.render(scale=DPI / 72, grayscale=True).to_numpy()
    boxes = find_boxes(gray)
    data = pytesseract.image_to_data(
        gray, lang="tha+eng", config="--oem 1 --psm 3", output_type=pytesseract.Output.DICT
    )
    lines = build_lines(data)
    print(f"{args.pdf.name} p{args.page}: {len(boxes)} boxes")
    for b in boxes:
        heading = heading_for(b, boxes, lines)
        group = match_group(heading)
        label = row_label(b, lines)
        option, score = match_option(group, label) if group else (None, 0)
        if group and option is None:  # page OCR missed or garbled the row: read the strip
            label = strip_label(b, gray)
            option, score = match_option(group, label)
        verdict = (
            f"{group}={option} ({score:.0f})" if option else f"{group}: no match ({score:.0f})"
        )
        print(f"  y={b.y:5} {b.w}x{b.h}px fill={b.fill:.3f} {b.state:7} {verdict}")


if __name__ == "__main__":
    main()
