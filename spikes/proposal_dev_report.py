"""Score `dbresearch.autofill.proposal` on the proposal-development samples (Phase 7).

Replays the OCR cache from `proposal_dev_ocr.py` (no OCR, no DB) and compares with the
research office's spreadsheet (`sheet.csv`) and file names.

    docker compose exec -T worker python - /samples/proposal_dev [--detail] [--year 2569] \\
        < spikes/proposal_dev_report.py

Default output is counts only. `--detail` prints document values: confidential, terminal only.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz

from dbresearch.autofill import proposal, thai
from dbresearch.autofill.page import Page
from dbresearch.ocr_layout import Line, Word

ROOT = Path(sys.argv[1])
DETAIL = "--detail" in sys.argv
YEAR = sys.argv[sys.argv.index("--year") + 1] if "--year" in sys.argv else None


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def to_pages(record: dict) -> list[Page]:
    pages = []
    for number, cached in enumerate(record["pages"], 1):
        lines = [
            Line(ln["text"], (Word(ln["text"], 0, ln["top"], 0, 0, ln["conf"]),), ln["conf"])
            for ln in cached["lines"]
        ]
        pages.append(Page(number, cached["width"], cached["height"], lines))
    return pages


def label_from_name(name: str) -> str:
    """What the research office's file name says (the reference)."""
    if re.search(r"เวียน|ขออนุมัติโครงการ(?:ทุน|สนับสนุน)|มติที่ประชุม|Research Hangout", name):
        return "programme"
    if "ยกเลิก" in name:
        return "cancel"
    if "หมวดค่าใช้จ่าย" in name:
        return "budget_change"
    if re.search(r"เปลี่ยนแปลงหัวข้อ|ปป\.โครงการ", name):
        return "title_change"
    if re.search(r"ปิดท|ปิดโครงการ", name):
        return "close"
    return "request"


def sheet_rows() -> list[dict]:
    with (ROOT / "sheet.csv").open() as f:
        return [
            {"no": i, "name": name, "title": compact(title), "year": year, "remark": remark}
            for i, (_no, name, title, year, remark) in enumerate(csv.reader(f), 1)
        ]


RANKS = ("ผู้ช่วยศาสตราจารย์", "รองศาสตราจารย์", "ศาสตราจารย์", "ดร.", "นางสาว", "นาย", "นาง")


def first_name(name: str) -> str:
    """'ผศ.ดร.รัตนา การุญ…' → 'รัตนา'."""
    for rank in RANKS:
        name = (name or "").replace(rank, "")
    name = re.sub(r"^(?:\S*\.)+", "", name.strip())
    return name.split()[0] if name.split() else ""


records = [json.loads(line) for line in (ROOT / "ocr.jsonl").open() if line.strip()]
sheet = sheet_rows()
files = []
for rec in records:
    year = m[1] if (m := re.search(r"งปม\.(25\d\d)", rec["file"])) else "top"
    if YEAR and year != YEAR:
        continue
    result = proposal.extract(to_pages(rec))
    files.append(
        {
            "file": rec["file"],
            "year": year,
            "name_label": label_from_name(rec["file"]),
            "kind": result["kind"],
            "fields": {k: v["value"] for k, v in result["fields"].items()},
        }
    )

# 1. Paper type
print(f"files: {len(files)}" + (f" (folder {YEAR})" if YEAR else ""))
agree: dict[str, list[int]] = defaultdict(lambda: [0, 0])
for f in files:
    agree[f["year"]][0] += f["kind"] == f["name_label"]
    agree[f["year"]][1] += 1
print("1. paper type = file name:", {y: f"{a}/{n}" for y, (a, n) in sorted(agree.items())})
for (a, b), n in sorted(Counter((f["name_label"], str(f["kind"])) for f in files).items()):
    if a != b:
        print(f"   name={a:14} read={b:14} {n}")

# 2. Field coverage per type
KEYS = [
    "memo_ref", "document_date", "fiscal_year", "owner", "department", "title", "new_title",
    "budget_total", "effective_from", "kpi_target", "kpi_due", "kpi_result", "spent_total",
    "cancel_reason", "research_area", "funding_source",
]  # fmt: skip
print("\n2. fields found:")
for label in proposal.PAPER_TYPES:
    group = [f for f in files if f["name_label"] == label]
    if group:
        cells = " ".join(
            f"{k}={sum(k in f['fields'] for f in group)}"
            for k in KEYS
            if any(k in f["fields"] for f in group)
        )
        print(f"   {label:13} n={len(group):3}  {cells}")

# 3. Correctness against the spreadsheet (best row by title)
title_ok = name_ok = year_ok = checked = 0
for f in files:
    if f["name_label"] == "programme":
        continue
    title = compact(f["fields"].get("title", ""))
    best, best_score = None, 0.0
    for row in sheet:
        score = fuzz.partial_ratio(title, row["title"]) if title else 0.0
        if score > best_score:
            best, best_score = row, score
    f["row"], f["score"] = (best["no"] if best else None), best_score
    if not best or best_score < 90:
        continue
    checked += 1
    title_ok += fuzz.ratio(title, best["title"]) >= 85
    name_ok += first_name(best["name"]) in compact(f["fields"].get("owner", ""))
    fy = f["fields"].get("fiscal_year")
    year_ok += fy is not None and str(fy + thai.BE_OFFSET) == best["year"]
print("\n3. against the spreadsheet:")
print(f"   papers matched to a row (title ≥ 90): {checked}")
print(f"   whole title ≈ row (≥ 85): {title_ok}/{checked}")
print(f"   researcher's first name in owner: {name_ok}/{checked}")
print(f"   fiscal year = row year: {year_ok}/{checked}  (closings/cancels may be filed later)")

if DETAIL:
    print("\n── detail (confidential) ──")
    for f in sorted(files, key=lambda f: f["file"]):
        flag = "" if f["kind"] == f["name_label"] else "  <-- TYPE"
        score = f"{f.get('score', 0):.0f}"
        print(f"{f['file'][:60]}  {f['name_label']}/{f['kind']} row={f.get('row')}:{score}{flag}")
        for k in KEYS:
            if k in f["fields"]:
                print(f"    {k:15} {str(f['fields'][k])[:100]}")

if "--misses" in sys.argv:
    print("\n── owner / title misses (confidential) ──")
    for f in files:
        if f["name_label"] == "programme" or f.get("score", 0) < 90:
            continue
        row = sheet[f["row"] - 1]
        owner = compact(f["fields"].get("owner", ""))
        if first_name(row["name"]) not in owner:
            print(f"  owner  {f['file'][:40]:40} read={owner[:40]!r} sheet={row['name']!r}")
        if fuzz.ratio(compact(f["fields"].get("title", "")), row["title"]) < 85:
            print(f"  title  {f['file'][:40]:40} read={f['fields'].get('title', '')[:60]!r}")
            print(f"         {'':40} sheet={row['title'][:60]!r}")
