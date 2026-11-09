"""OCR the first pages of every PDF under a folder, one JSON line per file (Phase 7 step 1).

    docker compose exec -T worker python - /samples/proposal_dev [--pages 4] [--jobs 3] \\
        [--done /samples/proposal_dev/ocr.jsonl] \\
        < spikes/proposal_dev_ocr.py >> samples/proposal_dev/ocr.jsonl

Output holds document text: confidential. Redirect it into `samples/` (gitignored) on the
server, never into git. `--done` skips files already in an earlier output (resume).
"""

import argparse
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import pypdfium2 as pdfium

from dbresearch.autofill.page import DPI, ocr_lines


def ocr_file(args: tuple[Path, Path, int]) -> dict:
    path, root, max_pages = args
    pdf = pdfium.PdfDocument(path)
    try:
        pages = []
        for index in range(min(len(pdf), max_pages)):
            gray = pdf[index].render(scale=DPI / 72, grayscale=True).to_numpy()
            if gray.ndim == 3:
                gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
            lines = ocr_lines(gray)
            pages.append(
                {
                    "width": gray.shape[1],
                    "height": gray.shape[0],
                    "lines": [
                        {"text": ln.text, "top": ln.top, "conf": round(ln.conf, 1)} for ln in lines
                    ],
                }
            )
        return {
            "file": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "page_count": len(pdf),
            "pages": pages,
        }
    finally:
        pdf.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--pages", type=int, default=4)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--done", type=Path)
    args = parser.parse_args()

    done = set()
    if args.done and args.done.exists():
        done = {json.loads(line)["file"] for line in args.done.open() if line.strip()}
    files = sorted(p for p in args.root.rglob("*.pdf") if str(p.relative_to(args.root)) not in done)
    print(f"{len(files)} files to OCR ({len(done)} done)", file=sys.stderr)
    with Pool(args.jobs) as pool:
        work = [(p, args.root, args.pages) for p in files]
        for n, result in enumerate(pool.imap_unordered(ocr_file, work), 1):
            print(json.dumps(result, ensure_ascii=False), flush=True)
            print(f"{n}/{len(files)} {result['file']}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
