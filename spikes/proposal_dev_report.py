"""Phase 7 step 1: classify proposal-development papers, read key fields, group them into
projects, and compare with the research office's spreadsheet. Reads the OCR cache from
`proposal_dev_ocr.py`; no OCR, no DB.

    docker compose exec -T worker python - /samples/proposal_dev [--detail] \\
        < spikes/proposal_dev_report.py

Default output is counts only. `--detail` prints document values: confidential, terminal only.
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz

from dbresearch.autofill import thai
from dbresearch.autofill.thai import is_noise
from dbresearch.ocr_layout import MIN_LINE_CONFIDENCE
from dbresearch.textnorm import normalize

ROOT = Path(sys.argv[1])
DETAIL = "--detail" in sys.argv
FOOTER = 0.88


# ───────────── Text ─────────────
def body(page: dict) -> list[str]:
    return [
        normalize(line["text"])
        for line in page["lines"]
        if line["conf"] >= MIN_LINE_CONFIDENCE
        and line["top"] < page["height"] * FOOTER
        and not is_noise(line["text"])
    ]


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ───────────── Labels ─────────────
def label_from_name(name: str) -> str:
    """What the research office's file name says (the reference to check against)."""
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


SUBJECT = re.compile(r"เร[ื]?[อ่]?ง(.{10,160})")


def subject_of(lines: list[str]) -> str:
    """The `เรื่อง …` line of the memo (plus the next line: subjects wrap)."""
    for i, line in enumerate(lines[:25]):
        c = compact(line)
        if re.match(r"^เร\S?\S?ง", c) and not c.startswith("เรียน"):
            return c + (compact(lines[i + 1]) if i + 1 < len(lines) else "")
    return ""


def label_from_text(subject: str, text: str) -> str:
    """Subject line first; the memo body as a fallback (OCR often garbles `เรื่อง`)."""
    for source in (subject, text[:1500]):
        if not source:
            continue
        if re.search(
            r"เวียนแจ้ง|อนุเคราะห์เวียน|ขออนุมัติโครงการสนับสนุน|ระเบียบวาระ|มติที่ประชุม|ResearchHangout", source
        ):
            return "programme"
        if re.search(r"ขอ(?:อนุมัติ)?ยกเลิก", source):
            return "cancel"
        if "หมวดค่าใช้จ่าย" in source:
            return "budget_change"
        if re.search(r"เปลี่ยนแปลง(?:หัวข้อ|ชื่อ)", source):
            return "title_change"
        if re.search(
            r"ปิด(?:โครงการ|ทุน)|ขอส่งข้อเสนอ|ขอนำส่งข้อเสนอ|ข้อเสนอโครงการวิจัยเรียบร้อยแล้ว", source
        ):
            return "close"
        if re.search(r"ขออนุมัติ\S{0,6}ทุนพัฒนา|ขอรับทุนพัฒนา|พัฒนาข้อเสนอ", source):
            return "request"
    return "unknown"


# ───────────── Fields ─────────────
MEMO_NO = re.compile(
    r"(อว\.?\s*0?6\d{2}\s*\.\s*\d{2}(?:\s*\.\s*\d{1,2})?\s*(?:\(\d\))?\s*/\s*\d{1,5})"
)
FISCAL = re.compile(r"ปีงบประมาณ(?:พ\.?ศ\.?)?(25\d\d)")
RESEARCHER = re.compile(r"(?:ด้วย|ตามที\S?)ข้าพเจ้า(.{4,60}?)(?:ตำแหน่ง|สังกัด)")
DEPARTMENT = re.compile(r"สังกัด(ภาควิชา.{3,40}?)(?:คณะ|ได้|มี|ขอ)")
_TOPIC = r"เร[ื่ิ]{0,2}อ[่]?ง"  # OCR drops or swaps the vowel/tone marks: เรือง, เร่ือง
TITLE_QUOTED = re.compile(rf"{_TOPIC}[“\"](?!ขอ)(.{{8,250}}?)[”\"]")
TITLE = re.compile(
    rf"{_TOPIC}[“\"']?(?!ขอ)(.{{8,250}}?)[”\"']?"
    r"(?:พร้อม|เป็นจำนวนเงิน|เป็นเงิน|ในวงเงิน|โดย|ภายใต้|ซึ่ง|นั้น)"
)
_DATE = r"\d{1,2}[฀-๿.]{2,12}(?:25\d\d|\d{2})"
PERIOD = re.compile(rf"ตั้งแต่(?:วันที่)?({_DATE})ถึง(?:วันที่)?({_DATE})")
AMOUNT = re.compile(r"(?:เป็นเงิน|วงเงิน|จำนวนเงิน|จำนวน)([\d,]{5,9})(?:\.00)?บาท")
KPI_CLOSE = re.compile(r"ตัวชี้วัด\S{0,12}?คือ(.{5,160}?)(?:รายละเอียด|จึงเรียน|$)")
KPI_REQUEST = re.compile(r"ต้อง(?:ดำเนินการ)?(จัดทำ.{5,160}?)(?:ให้แล้วเสร็จ|นั้น)")
FUNDING = (
    ("faculty_income", re.compile(r"รายได้\S{0,4}คณะ")),
    ("nu_income", re.compile(r"รายได้\S{0,4}มหาวิทยาลัย")),
    ("ff", re.compile(r"Fundamental|FF|กองทุนส่งเสริมวิทยาศาสตร์")),
    ("external", re.compile(r"แหล่งทุนภายนอก")),
)


def fields(text: str, raw: str = "") -> dict:
    """`raw` = all confident lines: the memo-no. line has no long word, so `body` drops it."""
    c = compact(text)
    out: dict = {}
    if m := MEMO_NO.search(raw or text):
        out["memo_no"] = re.sub(r"\s+", "", m[1])
    if m := FISCAL.search(c):
        out["fiscal_year"] = int(m[1])
    if m := RESEARCHER.search(c):
        out["researcher"] = thai.clean_person(m[1])
    if m := DEPARTMENT.search(c):
        out["department"] = m[1]
    if m := TITLE_QUOTED.search(c) or TITLE.search(c):
        out["title"] = m[1]
    if m := PERIOD.search(c):
        out["period"] = (thai.parse_thai_date(m[1]), thai.parse_thai_date(m[2]))
    if m := AMOUNT.search(c):
        out["amount"] = thai.parse_money(m[1])
    if m := KPI_REQUEST.search(c):
        out["kpi"] = m[1]
    if m := KPI_CLOSE.search(c):
        out["kpi_result"] = m[1]
    for name, pattern in FUNDING:
        if pattern.search(c):
            out["funding"] = name
            break
    return out


# ───────────── Spreadsheet ─────────────
def sheet_rows() -> list[dict]:
    rows = []
    with (ROOT / "sheet.csv").open() as f:
        for i, (_no, name, title, year, remark) in enumerate(csv.reader(f), 1):
            rows.append(
                {
                    "no": str(i),
                    "name": name,
                    "title": compact(title),
                    "year": year,
                    "remark": remark,
                }
            )
    return rows


def first_name(name: str) -> str:
    """'ผศ.ดร.รัตนา การุญ…' → 'รัตนา'; 'อ.รัตนา' → 'รัตนา'."""
    name = re.sub(r"^(?:\S*\.)+", "", name.strip())
    return name.split()[0] if name.split() else ""


def name_in_file(path: str) -> str:
    m = re.search(r"อ\s?\.?\s?([฀-๿]+)", Path(path).name)
    return m[1] if m else ""


# ───────────── Run ─────────────
records = [json.loads(line) for line in (ROOT / "ocr.jsonl").open() if line.strip()]
sheet = sheet_rows()
files = []
for rec in records:
    pages = [body(p) for p in rec["pages"]]
    first = " ".join(pages[0]) if pages else ""
    subject = subject_of(pages[0]) if pages else ""
    raw = " ".join(
        normalize(ln["text"]) for p in rec["pages"][:1] for ln in p["lines"] if ln["conf"] >= 50
    )
    found = fields(" ".join(" ".join(p) for p in pages[:2]), raw)
    files.append(
        {
            "file": rec["file"],
            "sha": rec["sha256"],
            "pages": rec["page_count"],
            "folder_year": (m[1] if (m := re.search(r"งปม\.(25\d\d)", rec["file"])) else None),
            "name_label": label_from_name(rec["file"]),
            "text_label": label_from_text(subject, compact(first)),
            "has_subject": bool(subject),
            "fields": found,
        }
    )

print(f"files: {len(files)}   pages total: {sum(f['pages'] for f in files)}")
dups = Counter(f["sha"] for f in files)
print(f"byte-identical duplicates: {sum(n - 1 for n in dups.values() if n > 1)}")

# 1. Classification vs. file name
pairs = Counter((f["name_label"], f["text_label"]) for f in files)
right = sum(n for (a, b), n in pairs.items() if a == b)
print(f"\n1. type from text vs file name: {right}/{len(files)} agree")
for (a, b), n in sorted(pairs.items()):
    print(f"   name={a:14} text={b:14} {n}")
print(f"   subject line found: {sum(f['has_subject'] for f in files)}/{len(files)}")

# 2. Field coverage per type
print("\n2. fields found (pages 1–2):")
keys = [
    "memo_no",
    "fiscal_year",
    "researcher",
    "department",
    "title",
    "amount",
    "period",
    "kpi",
    "kpi_result",
    "funding",
]
for label in ("request", "close", "cancel", "title_change", "budget_change", "programme"):
    group = [f for f in files if f["name_label"] == label]
    if group:
        cells = "  ".join(f"{k}={sum(k in f['fields'] for f in group)}" for k in keys)
        print(f"   {label:14} n={len(group):3}  {cells}")
print("   funding:", Counter(f["fields"].get("funding") for f in files))
print("   amounts:", Counter(str(f["fields"].get("amount")) for f in files).most_common(6))

# 3. Year: text vs folder
year_ok = [f for f in files if f["fields"].get("fiscal_year") and f["folder_year"]]
same = sum(str(f["fields"]["fiscal_year"]) == f["folder_year"] for f in year_ok)
print(f"\n3. fiscal year in text = folder year: {same}/{len(year_ok)}")

# 4. Match papers to spreadsheet rows (title fuzzy, then first name)
print("\n4. spreadsheet match (title similarity, best row):")
matched_rows: dict[str, list] = {}
scores = []
for f in files:
    if f["name_label"] == "programme":
        continue
    title = compact(f["fields"].get("title", ""))
    best, best_score = None, 0.0
    for row in sheet:
        score = fuzz.partial_ratio(title, row["title"]) if title else 0.0
        if first_name(row["name"]) and first_name(row["name"]) == name_in_file(f["file"]):
            score += 10
        if score > best_score:
            best, best_score = row, score
    f["row"], f["score"] = (best["no"] if best else None), best_score
    scores.append(best_score)
    if best and best_score >= 75:
        matched_rows.setdefault(best["no"], []).append(f)
bands = Counter("≥90" if s >= 90 else "75–89" if s >= 75 else "<75" for s in scores)
print(f"   papers: {len(scores)}  {dict(bands)}")
print(f"   sheet rows with ≥1 paper: {len(matched_rows)}/{len(sheet)}")
status_ok = status_n = 0
for row in sheet:
    papers = matched_rows.get(row["no"], [])
    if not papers:
        continue
    labels = {p["name_label"] for p in papers}
    for word, label in (("ปิดทุน", "close"), ("ยกเลิก", "cancel")):
        if word in row["remark"]:
            status_n += 1
            status_ok += label in labels
print(f"   sheet status (ปิดทุนแล้ว/ยกเลิก) backed by a matching paper: {status_ok}/{status_n}")

if DETAIL:
    print("\n── detail (confidential) ──")
    for f in sorted(files, key=lambda f: f["file"]):
        fl = f["fields"]
        print(
            f"{f['file'][:48]:48} {f['name_label'][:6]:6} {f['text_label'][:6]:6} "
            f"y={fl.get('fiscal_year')} amt={fl.get('amount')} fund={fl.get('funding')} "
            f"row={f.get('row')}:{f.get('score', 0):.0f}\n    who={fl.get('researcher', '')[:30]} "
            f"dept={fl.get('department', '')[:30]} memo={fl.get('memo_no')} "
            f"period={fl.get('period')}\n"
            f"    title={fl.get('title', '')[:90]}\n    kpi={fl.get('kpi', '')[:90]}"
        )

if DETAIL:
    print("\n── type disagreements ──")
    for f in files:
        if f["name_label"] != f["text_label"]:
            print(f"  {f['file'][:60]:60} name={f['name_label']} text={f['text_label']}")
    print("\n── sheet rows without a paper / status without its paper ──")
    for row in sheet:
        papers = matched_rows.get(row["no"], [])
        labels = {p["name_label"] for p in papers}
        missing = [
            label
            for word, label in (("ปิดทุน", "close"), ("ยกเลิก", "cancel"))
            if word in row["remark"] and label not in labels
        ]
        if not papers or missing:
            print(
                f"  row {row['no']:>2} {row['year']} {row['name'][:28]:28} {row['remark'][:22]:22} "
                f"papers={sorted(labels)} missing={missing} {row['title'][:40]}"
            )
