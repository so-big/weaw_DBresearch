"""OCR spike: how well does Tesseract (tha+eng) read our documents?

Runs inside the worker container against confidential samples:

    docker compose exec worker python spikes/ocr_probe.py /samples/<file>.pdf

For every page and preprocessing variant it prints word count, mean confidence, time, and
which auto-fill anchor labels (DESIGN §6) were found. OCR text goes to /tmp/work (tmpfs) only;
the output printed here contains no document text unless --show is given.
"""

import argparse
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract

from dbresearch.textnorm import normalize

ANCHORS = {
    "contract_no_label": r"สัญญาเลขที่",
    "contract_no": r"R\s?\d{4}\s?[A-Z]\s?\d{2,}",
    "attachment_marker": r"เอกสารแนบ\s*(หมายเลข)?\s*(ที่)?\s*\d",
    "project_label": r"โครงการ",
    "title_th_label": r"ชื่อโครงการวิจัย",
    "budget_total_label": r"งบประมาณรวม",
    "amount": r"\d{1,3}(,\d{3})+(\.\d{2})?\s*บาท",
    "fiscal_year": r"ประจำปี(งบประมาณ)?\s*พ\.?\s?ศ\.?\s*\d{4}",
    "contract_header": r"สัญญารับทุนอุดหนุนการวิจัย",
    "research_type_heading": r"ประเภท(การ)?วิจัย",
    "research_group_heading": r"กลุ่มการวิจัย",
    "installment": r"งวดที่\s*\d",
    "page_footer": r"หน้า\s*\d+",
}
THAI = r"฀-๿"


def squash_thai_spaces(text: str) -> str:
    """Remove spaces between two Thai characters (Tesseract often splits Thai words)."""
    return re.sub(rf"(?<=[{THAI}]) +(?=[{THAI}])", "", text)


def render(pdf: pdfium.PdfDocument, index: int, dpi: int) -> np.ndarray:
    image = pdf[index].render(scale=dpi / 72, grayscale=True).to_numpy()
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def clean(gray: np.ndarray) -> np.ndarray:
    """Flatten uneven lighting (photo shadows, faint watermark) then binarise with Otsu."""
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), 31)
    flat = cv2.divide(gray, background, scale=255)
    _, binary = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def ocr(image: np.ndarray) -> tuple[str, int, float]:
    data = pytesseract.image_to_data(
        image,
        lang="tha+eng",
        config="--oem 1 --psm 3 -c preserve_interword_spaces=1",
        output_type=pytesseract.Output.DICT,
    )
    lines: dict[tuple[int, int, int], list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confs.append(float(data["conf"][i]))
    text = "\n".join(" ".join(words) for words in lines.values())
    return text, len(confs), (sum(confs) / len(confs) if confs else 0.0)


def found_anchors(text: str) -> set[str]:
    squashed = squash_thai_spaces(text)
    return {name for name, rx in ANCHORS.items() if re.search(rx, squashed)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--show", action="store_true", help="print OCR text (confidential!)")
    parser.add_argument("--out", type=Path, default=Path("/tmp/work"))
    args = parser.parse_args()

    print(f"tesseract {pytesseract.get_tesseract_version()}  file={args.pdf.name}  dpi={args.dpi}")
    pdf = pdfium.PdfDocument(args.pdf)
    for index in range(len(pdf)):
        layer = normalize(pdf[index].get_textpage().get_text_range())
        print(
            f"\n== page {index + 1}: text layer {len(layer)} chars, anchors "
            f"{sorted(found_anchors(layer)) if layer else '-'}"
        )
        gray = render(pdf, index, args.dpi)
        for variant, image in (("gray", gray), ("clean", clean(gray))):
            start = time.perf_counter()
            raw, words, conf = ocr(image)
            text = normalize(raw)
            elapsed = time.perf_counter() - start
            anchors = found_anchors(text)
            print(
                f"  {variant:5} words={words:4} conf={conf:5.1f} time={elapsed:5.1f}s "
                f"anchors={len(anchors):2}/{len(ANCHORS)} {sorted(anchors)}"
            )
            out = args.out / f"{args.pdf.stem}_p{index + 1}_{variant}.txt"
            out.write_text(text, encoding="utf-8")
            if args.show:
                print(
                    "  ---\n" + "\n".join("  | " + line for line in text.splitlines()) + "\n  ---"
                )


if __name__ == "__main__":
    main()
