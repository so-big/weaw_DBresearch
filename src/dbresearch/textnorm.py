"""Thai/English text normalisation applied before storing or searching text (DESIGN §5)."""

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# Thai combining marks: above/below vowels, tone marks, thanthakhat, nikhahit.
_THAI_COMBINING = "ัิ-ฺ็-๎"
_SPACE_BEFORE_MARK = re.compile(rf"\s+(?=[{_THAI_COMBINING}])")
_SPACES = re.compile(r"[ \t ]+")


def normalize(text: str) -> str:
    """Return NFC text with zero-width chars removed, Thai digits as ASCII, and tidy spaces.

    Also repairs two common artefacts of Thai PDF text layers and OCR:
    - a space inserted before a combining mark ("ช ื่อ" → "ชื่อ")
    - SARA AM written as NIKHAHIT + SARA AA ("ํา" → "ำ")
    """
    text = text.translate(_ZERO_WIDTH)
    text = text.replace("ํา", "ำ")
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_THAI_DIGITS)
    text = _SPACE_BEFORE_MARK.sub("", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)
