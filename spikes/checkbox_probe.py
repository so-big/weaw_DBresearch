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

from dbresearch.ocr_layout import Line, Word, build_lines, join_words
from dbresearch.textnorm import normalize

DPI = 300
MM = DPI / 25.4
MIN_SIDE, MAX_SIDE = 2.0 * MM, 7.0 * MM  # printed checkboxes are ~3–5 mm
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


def label_for(box: Box, gray: np.ndarray) -> str:
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
    data = pytesseract.image_to_data(
        cleaned, lang="tha+eng", config="--oem 1 --psm 7", output_type=pytesseract.Output.DICT
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
    return normalize(join_words(words))


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
        print(
            f"  y={b.y:5} x={b.x:5} {b.w}x{b.h}px fill={b.fill:.3f} {b.state:7} "
            f"label='{label_for(b, gray)[:40]}'  heading='{heading_for(b, boxes, lines)[:30]}'"
        )


if __name__ == "__main__":
    main()
