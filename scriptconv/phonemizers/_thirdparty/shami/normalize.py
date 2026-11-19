"""Unicode cleanup for the Levantine/English code-switching front-end.

Ported from hams_tts.text.normalize (Apache-2.0). The upstream module also
read numbers, money, percentages and clock times; in scriptconv text2spoken
reads them before the text reaches a backend (the frontend's ``normalizer``
hook), so this module only cleans the Unicode.
"""

from __future__ import annotations

import re
import unicodedata

TATWEEL = "ـ"
ZWJ = "‍"
ZWNJ = "‌"
ARABIC_DIATRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")

_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

_PUNCT_MAP = {
    "،": ",", "؍": ",", "٫": ".", "٬": ",",
    "؛": ";", "؟": "?", "٪": "%", "−": "-",
    "“": '"', "”": '"', "„": '"', "‟": '"', "’": "'", "‘": "'",
    "–": "—", "―": "—", "‒": "—",
    " ": " ", " ": " ", "\t": " ",
}
_PUNCT_TABLE = {ord(k): v for k, v in _PUNCT_MAP.items()}


def normalize_unicode(text: str) -> str:
    """NFC + cosmetic cleanup that is safe for TTS."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(TATWEEL, "").replace(ZWJ, "").replace(ZWNJ, "")
    text = text.translate(_PUNCT_TABLE)
    text = text.translate(_DIGIT_MAP)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_diacritics(text: str) -> str:
    """Remove Arabic tashkeel."""
    return ARABIC_DIATRITICS.sub("", text)
