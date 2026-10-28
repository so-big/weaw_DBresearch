"""OCR spike: how well does Tesseract (tha+eng) read our documents?

Runs inside the worker container against confidential samples:

    docker compose exec worker python spikes/ocr_probe.py /samples/<file>.pdf

Prints per page: word count, mean confidence, time, and which auto-fill labels/values
(DESIGN §6) were found. OCR text goes to /tmp/work (tmpfs) only; nothing printed contains
document text unless --show is given.
"""

import argparse
import re
import time
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from rapidfuzz import fuzz

from dbresearch.ocr_layout import build_lines, page_text

# Labels are matched fuzzily per line (OCR misreads single characters, e.g. ชื่อ → ขือ).
LABELS = {
    "contract_header": "สัญญารับทุนอุดหนุนการวิจัย",
    "contract_no_label": "สัญญาเลขที่",
    "attachment_marker": "เอกสารแนบ",
    "project_label": "โครงการ",
    "title_th_label": "ชื่อโครงการวิจัย",
    "lang_th_label": "(ภาษาไทย)",
    "lang_en_label": "(ภาษาอังกฤษ)",
    "budget_total_label": "งบประมาณรวม",
    "research_type_heading": "ประเภทการวิจัย",
    "research_group_heading": "กลุ่มการวิจัย",
    "installment_label": "งวดที่",
}
LABEL_THRESHOLD = 85
MONTHS = "มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม"
VALUES = {
    "contract_no": r"R\s?25\d\d\s?[A-Z]\s?\d{2,4}",
    "fiscal_year": r"ประจำปี.{0,25}?25\d\d",
    "amount": r"\d{1,3}(,\d{3})+(\.\d{2})?",
    "thai_date": rf"\d{{1,2}}\s?({MONTHS})\s?25\d\d",
    "page_footer": r"หน้า\s?\d+",
}


def found(lines_text: list[str]) -> list[str]:
    hits = set()
    for line in lines_text:
        compact = line.replace(" ", "")
        for name, label in LABELS.items():
            if fuzz.partial_ratio(label, compact) >= LABEL_THRESHOLD:
                hits.add(name)
    joined = "\n".join(lines_text)
    hits |= {name for name, rx in VALUES.items() if re.search(rx, joined)}
    return sorted(hits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--psm", type=int, default=3)
    parser.add_argument("--show", action="store_true", help="print OCR text (confidential!)")
    parser.add_argument("--out", type=Path, default=Path("/tmp/work"))
    args = parser.parse_args()

    print(f"tesseract {pytesseract.get_tesseract_version()}  {args.pdf.name}  dpi={args.dpi}")
    pdf = pdfium.PdfDocument(args.pdf)
    for index in range(len(pdf)):
        start = time.perf_counter()
        image = pdf[index].render(scale=args.dpi / 72, grayscale=True).to_pil()
        data = pytesseract.image_to_data(
            image,
            lang="tha+eng",
            config=f"--oem 1 --psm {args.psm}",
            output_type=pytesseract.Output.DICT,
        )
        lines = build_lines(data)
        text = page_text(lines)
        elapsed = time.perf_counter() - start
        words = sum(len(line.words) for line in lines)
        conf = sum(line.conf * len(line.words) for line in lines) / max(words, 1)
        kept = text.splitlines()
        hits = found(kept)
        print(
            f"p{index + 1}: lines={len(kept):3}/{len(lines):3} words={words:4} conf={conf:5.1f} "
            f"time={elapsed:4.1f}s  {len(hits):2} found: {' '.join(hits)}"
        )
        (args.out / f"{args.pdf.stem}_p{index + 1}.txt").write_text(text, encoding="utf-8")
        if args.show:
            print("\n".join("   | " + line for line in kept))


if __name__ == "__main__":
    main()
