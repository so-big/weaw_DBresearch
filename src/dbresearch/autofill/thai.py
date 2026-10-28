"""Parsing helpers for Thai document values: dates, B.E. years, amounts, names."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz, process

BE_OFFSET = 543

MONTHS = {
    "มกราคม": 1,
    "กุมภาพันธ์": 2,
    "มีนาคม": 3,
    "เมษายน": 4,
    "พฤษภาคม": 5,
    "มิถุนายน": 6,
    "กรกฎาคม": 7,
    "สิงหาคม": 8,
    "กันยายน": 9,
    "ตุลาคม": 10,
    "พฤศจิกายน": 11,
    "ธันวาคม": 12,
}
MONTH_ABBR = {
    "ม.ค.": 1,
    "ก.พ.": 2,
    "มี.ค.": 3,
    "เม.ย.": 4,
    "พ.ค.": 5,
    "มิ.ย.": 6,
    "ก.ค.": 7,
    "ส.ค.": 8,
    "ก.ย.": 9,
    "ต.ค.": 10,
    "พ.ย.": 11,
    "ธ.ค.": 12,
}
# A Thai date as written in contracts: "1 กันยายน 2568", "3 ก.พ. 68", "1/9/2568".
DATE_RE = r"\d{1,2}\s*(?:[฀-๿.]{2,12}|/\s*\d{1,2}\s*/)\s*(?:25\d\d|\d{2})"
_WORDY = re.compile(r"(\d{1,2})\s*([฀-๿.]{2,12}?)\s*(25\d\d|\d{2})$")
_NUMERIC = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(25\d\d|\d{2})$")

PERSON_PREFIXES = (
    "ผู้ช่วยศาสตราจารย์",
    "รองศาสตราจารย์",
    "ศาสตราจารย์",
    "อาจารย์",
    "ผศ.",
    "รศ.",
    "ศ.",
    "ดร.",
    "นางสาว",
    "นาง",
    "นาย",
    "Prof.",
    "Dr.",
    "Mr.",
    "Ms.",
    "Mrs.",
)
_LEADERS = re.compile(r"[.…_]{2,}")


def be_to_gregorian(year_be: int) -> int:
    return year_be - BE_OFFSET


def _full_year(text: str) -> int:
    year = int(text)
    return year + 2500 if year < 100 else year  # "68" → 2568


def _month(token: str) -> int | None:
    token = token.strip()
    if token in MONTH_ABBR:
        return MONTH_ABBR[token]
    match = process.extractOne(token, MONTHS.keys(), scorer=fuzz.ratio, score_cutoff=75)
    return MONTHS[match[0]] if match else None


def parse_thai_date(text: str) -> date | None:
    """'1 กันยายน 2568' → date(2025, 9, 1). Tolerates small OCR errors in the month name."""
    text = text.strip()
    if m := _NUMERIC.search(text):
        day, month, year = int(m[1]), int(m[2]), _full_year(m[3])
    elif m := _WORDY.search(text):
        day, month, year = int(m[1]), _month(m[2]), _full_year(m[3])
        if month is None:
            return None
    else:
        return None
    try:
        return date(be_to_gregorian(year), month, day)
    except ValueError:
        return None


def fiscal_year_of(day: date) -> int:
    """Thai fiscal year (Oct–Sep) in Gregorian terms: 1 Oct 2024 → FY 2025 (= พ.ศ. 2568)."""
    return day.year + 1 if day.month >= 10 else day.year


def parse_money(text: str) -> Decimal | None:
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


def words_to_amount(text: str) -> int | None:
    """'หนึ่งหมื่นบาทถ้วน' → 10000. None when OCR garbled the words."""
    from pythainlp.util import thaiword_to_num  # heavy import: worker only

    words = re.sub(r"[()\s]|บาท|ถ้วน", "", text)
    if "สตางค์" in words:
        return None
    try:
        return int(thaiword_to_num(words)) if words else None
    except (ValueError, KeyError, IndexError):
        return None


def strip_leaders(text: str) -> str:
    """Remove dotted fill-in leaders ('.นางสาวรุ่งนภา.........') and stray quotes."""
    text = _LEADERS.sub(" ", text)
    junk = " .…_:,;“”\"'"
    return re.sub(r"\s+", " ", text.strip(junk)).strip(junk)


def split_person(text: str) -> tuple[str | None, str]:
    """'ผศ.ดร. สมชาย ใจดี' → ('ผศ.ดร.', 'สมชาย ใจดี'). Prefixes may repeat and touch the name."""
    text = strip_leaders(text)
    prefix = ""
    changed = True
    while changed:
        changed = False
        for candidate in PERSON_PREFIXES:
            if text.startswith(candidate):
                prefix += candidate
                text = text[len(candidate) :].lstrip(" .")
                changed = True
                break
    return (prefix or None), text.strip()


def is_thai(text: str) -> bool:
    return bool(re.search(r"[฀-๿]", text))
