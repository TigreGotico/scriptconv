"""Writing-system identification and metadata.

Provides ISO-15924 script codes, character-range detection, per-language
default script, and normalisation of free-form script labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = [
    "Script",
    "SCRIPT_REGISTRY",
    "char_script",
    "detect_script",
    "lang_to_script",
    "normalize_script_tag",
]


@dataclass(frozen=True)
class Script:
    """Metadata for a single writing system.

    Attributes
    ----------
    iso15924:
        Four-letter ISO-15924 script code (e.g. ``"Latn"``).
    name:
        Human-readable English name (e.g. ``"Latin"``).
    direction:
        Primary text direction: ``"ltr"`` or ``"rtl"``.
    char_ranges:
        Tuple of ``(start, end)`` inclusive Unicode codepoint ranges that
        predominantly belong to this script.
    """

    iso15924: str
    name: str
    direction: str  # "ltr" | "rtl"
    char_ranges: Tuple[Tuple[int, int], ...]


# ---------------------------------------------------------------------------
# Registry — the scripts the org actually handles
# ---------------------------------------------------------------------------

SCRIPT_REGISTRY: dict[str, Script] = {
    "Latn": Script(
        iso15924="Latn",
        name="Latin",
        direction="ltr",
        char_ranges=(
            (0x0041, 0x005A),  # A-Z
            (0x0061, 0x007A),  # a-z
            (0x00C0, 0x024F),  # Latin Extended
        ),
    ),
    "Cyrl": Script(
        iso15924="Cyrl",
        name="Cyrillic",
        direction="ltr",
        char_ranges=(
            (0x0400, 0x04FF),
            (0x0500, 0x052F),
        ),
    ),
    "Arab": Script(
        iso15924="Arab",
        name="Arabic",
        direction="rtl",
        char_ranges=(
            (0x0600, 0x06FF),
            (0x0750, 0x077F),
            (0xFB50, 0xFDFF),
            (0xFE70, 0xFEFF),
        ),
    ),
    "Hebr": Script(
        iso15924="Hebr",
        name="Hebrew",
        direction="rtl",
        char_ranges=(
            (0x0590, 0x05FF),
            (0xFB1D, 0xFB4F),
        ),
    ),
    "Deva": Script(
        iso15924="Deva",
        name="Devanagari",
        direction="ltr",
        char_ranges=((0x0900, 0x097F),),
    ),
    "Hang": Script(
        iso15924="Hang",
        name="Hangul",
        direction="ltr",
        char_ranges=(
            (0xAC00, 0xD7AF),  # Hangul syllables
            (0x1100, 0x11FF),  # Hangul Jamo
            (0x3130, 0x318F),  # Hangul Compatibility Jamo
        ),
    ),
    "Hira": Script(
        iso15924="Hira",
        name="Hiragana",
        direction="ltr",
        char_ranges=((0x3040, 0x309F),),
    ),
    "Kana": Script(
        iso15924="Kana",
        name="Katakana",
        direction="ltr",
        char_ranges=((0x30A0, 0x30FF),),
    ),
    "Hani": Script(
        iso15924="Hani",
        name="Han",
        direction="ltr",
        char_ranges=(
            (0x4E00, 0x9FFF),
            (0x3400, 0x4DBF),
            (0x20000, 0x2A6DF),
        ),
    ),
    "Grek": Script(
        iso15924="Grek",
        name="Greek",
        direction="ltr",
        char_ranges=((0x0370, 0x03FF), (0x1F00, 0x1FFF)),
    ),
    "Armn": Script(
        iso15924="Armn",
        name="Armenian",
        direction="ltr",
        char_ranges=((0x0530, 0x058F),),
    ),
    "Geor": Script(
        iso15924="Geor",
        name="Georgian",
        direction="ltr",
        char_ranges=((0x10A0, 0x10FF),),
    ),
    "Ethi": Script(
        iso15924="Ethi",
        name="Ethiopic",
        direction="ltr",
        char_ranges=((0x1200, 0x137F), (0x1380, 0x139F)),
    ),
    "Khmr": Script(
        iso15924="Khmr",
        name="Khmer",
        direction="ltr",
        char_ranges=((0x1780, 0x17FF),),
    ),
    "Telu": Script(
        iso15924="Telu",
        name="Telugu",
        direction="ltr",
        char_ranges=((0x0C00, 0x0C7F),),
    ),
    "Cans": Script(
        iso15924="Cans",
        name="Unified Canadian Aboriginal Syllabics",
        direction="ltr",
        char_ranges=((0x1400, 0x167F), (0x18B0, 0x18FF)),
    ),
    "Tfng": Script(
        iso15924="Tfng",
        name="Tifinagh",
        direction="ltr",
        char_ranges=((0x2D30, 0x2D7F),),
    ),
    "Thai": Script(
        iso15924="Thai",
        name="Thai",
        direction="ltr",
        char_ranges=((0x0E00, 0x0E7F),),
    ),
    "Beng": Script(
        iso15924="Beng",
        name="Bengali",
        direction="ltr",
        char_ranges=((0x0980, 0x09FF),),
    ),
    "Guru": Script(
        iso15924="Guru",
        name="Gurmukhi",
        direction="ltr",
        char_ranges=((0x0A00, 0x0A7F),),
    ),
    "Gujr": Script(
        iso15924="Gujr",
        name="Gujarati",
        direction="ltr",
        char_ranges=((0x0A80, 0x0AFF),),
    ),
    "Taml": Script(
        iso15924="Taml",
        name="Tamil",
        direction="ltr",
        char_ranges=((0x0B80, 0x0BFF),),
    ),
    "Sinh": Script(
        iso15924="Sinh",
        name="Sinhala",
        direction="ltr",
        char_ranges=((0x0D80, 0x0DFF),),
    ),
    "Mymr": Script(
        iso15924="Mymr",
        name="Myanmar",
        direction="ltr",
        char_ranges=((0x1000, 0x109F),),
    ),
    "Tibt": Script(
        iso15924="Tibt",
        name="Tibetan",
        direction="ltr",
        char_ranges=((0x0F00, 0x0FFF),),
    ),
    "Laoo": Script(
        iso15924="Laoo",
        name="Lao",
        direction="ltr",
        char_ranges=((0x0E80, 0x0EFF),),
    ),
    "Glag": Script(
        iso15924="Glag",
        name="Glagolitic",
        direction="ltr",
        char_ranges=((0x2C00, 0x2C5F),),
    ),
    "Runr": Script(
        iso15924="Runr",
        name="Runic",
        direction="ltr",
        char_ranges=((0x16A0, 0x16FF),),
    ),
    "Ogam": Script(
        iso15924="Ogam",
        name="Ogham",
        direction="ltr",
        char_ranges=((0x1680, 0x169F),),
    ),
    "Cprt": Script(
        iso15924="Cprt",
        name="Cypriot",
        direction="rtl",
        char_ranges=((0x10800, 0x1083F),),
    ),
    "Phnx": Script(
        iso15924="Phnx",
        name="Phoenician",
        direction="rtl",
        char_ranges=((0x10900, 0x1091F),),
    ),
}

# ---------------------------------------------------------------------------
# char_script — map one character to its ISO-15924 code
# ---------------------------------------------------------------------------

def char_script(ch: str) -> Optional[str]:
    """Return the ISO-15924 code for a single character, or ``None``."""
    cp = ord(ch)
    for code, script in SCRIPT_REGISTRY.items():
        for lo, hi in script.char_ranges:
            if lo <= cp <= hi:
                return code
    return None


# ---------------------------------------------------------------------------
# detect_script — dominant script in a text
# ---------------------------------------------------------------------------

def detect_script(text: str) -> Optional[str]:
    """Return the ISO-15924 code of the dominant script in *text*.

    Counts script-bearing characters only (skips ASCII digits, spaces,
    punctuation).  Returns ``None`` for empty or purely non-alphabetic input.
    """
    counts: dict[str, int] = {}
    for ch in text:
        s = char_script(ch)
        if s is not None:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


# ---------------------------------------------------------------------------
# lang_to_script — default script per language primary subtag
#
# Seeded from:
#   - stressonnx LANG_SCRIPT mapping
#   - phoonnx _MMS_SCRIPTS knowledge + general BCP-47 defaults
# ---------------------------------------------------------------------------

_LANG_TO_SCRIPT: dict[str, str] = {
    # Latin
    "en": "Latn", "de": "Latn", "fr": "Latn", "es": "Latn", "pt": "Latn",
    "it": "Latn", "nl": "Latn", "sv": "Latn", "no": "Latn", "da": "Latn",
    "fi": "Latn", "pl": "Latn", "cs": "Latn", "sk": "Latn", "hr": "Latn",
    "sl": "Latn", "ro": "Latn", "hu": "Latn", "lt": "Latn", "lv": "Latn",
    "et": "Latn", "mt": "Latn", "sq": "Latn", "eu": "Latn", "ca": "Latn",
    "gl": "Latn", "cy": "Latn", "ga": "Latn", "af": "Latn", "sw": "Latn",
    "id": "Latn", "ms": "Latn", "tl": "Latn", "tr": "Latn", "az": "Latn",
    "uz": "Latn", "la": "Latn", "is": "Latn", "fo": "Latn", "lb": "Latn",
    "oc": "Latn", "br": "Latn", "ast": "Latn", "mwl": "Latn",
    "crk": "Cans",  # Cree — default syllabics (MMS label "syllabics")
    # Cyrillic
    "ru": "Cyrl", "uk": "Cyrl", "be": "Cyrl", "bg": "Cyrl", "sr": "Cyrl",
    "mk": "Cyrl", "kk": "Cyrl", "ky": "Cyrl", "tg": "Cyrl", "mn": "Cyrl",
    "tt": "Cyrl", "ba": "Cyrl", "cv": "Cyrl", "os": "Cyrl", "ce": "Cyrl",
    "av": "Cyrl", "udm": "Cyrl", "sah": "Cyrl", "bxr": "Cyrl",
    # Arabic
    "ar": "Arab", "fa": "Arab", "ur": "Arab", "ps": "Arab", "sd": "Arab",
    "ug": "Arab", "ku": "Arab",
    # Hebrew
    "he": "Hebr", "yi": "Hebr",
    # Devanagari
    "hi": "Deva", "mr": "Deva", "ne": "Deva", "sa": "Deva", "kok": "Deva",
    # Hangul
    "ko": "Hang",
    # Japanese (mixed but hiragana is the base syllabary)
    "ja": "Hira",
    # Han
    "zh": "Hani", "yue": "Hani",
    # Greek
    "el": "Grek",
    # Armenian
    "hy": "Armn",
    # Georgian
    "ka": "Geor",
    # Ethiopic
    "am": "Ethi", "ti": "Ethi", "om": "Ethi", "so": "Latn",
    # Khmer
    "km": "Khmr",
    # Telugu
    "te": "Telu",
    # Tifinagh
    "tzm": "Tfng", "shi": "Tfng",
    # Thai
    "th": "Thai",
    # Bengali
    "bn": "Beng", "as": "Beng",
    # Gurmukhi
    "pa": "Guru",
    # Gujarati
    "gu": "Gujr",
    # Tamil
    "ta": "Taml",
    # Sinhala
    "si": "Sinh",
    # Myanmar
    "my": "Mymr",
    # Tibetan
    "bo": "Tibt",
    # Lao
    "lo": "Laoo",
    # Latin-script languages shipped by orthography2ipa
    "vi": "Latn",   # Vietnamese
    "ha": "Latn",   # Hausa
    "ig": "Latn",   # Igbo
    "yo": "Latn",   # Yoruba
    "zu": "Latn",   # Zulu
    "xh": "Latn",   # Xhosa
    "so": "Latn",   # Somali
    "om": "Latn",   # Oromo (Latin orthography)
    "rw": "Latn",   # Kinyarwanda
    "tk": "Latn",   # Turkmen (Latin since 1993)
    "eo": "Latn",   # Esperanto
}


def lang_to_script(lang: str) -> Optional[str]:
    """Return the ISO-15924 code of the default script for *lang*.

    *lang* may be a BCP-47 tag or bare ISO 639 code.  Only the primary
    subtag is used (``"pt-BR"`` → ``"pt"``).  Returns ``None`` when the
    language is unknown.
    """
    primary = lang.split("-")[0].split("_")[0].lower()
    return _LANG_TO_SCRIPT.get(primary)


# ---------------------------------------------------------------------------
# normalize_script_tag — free-form labels → ISO-15924
#
# Ported from phoonnx._MMS_SCRIPTS and extended.
# ---------------------------------------------------------------------------

_LABEL_MAP: dict[str, str] = {
    # MMS labels (phoonnx._MMS_SCRIPTS)
    "latin": "Latn",
    "cyrillic": "Cyrl",
    "arabic": "Arab",
    "syllabics": "Cans",
    "tifinagh": "Tfng",
    "devanagari": "Deva",
    "ethiopic": "Ethi",
    "khmer": "Khmr",
    "telugu": "Telu",
    # Common aliases
    "hebrew": "Hebr",
    "hangul": "Hang",
    "korean": "Hang",
    "hiragana": "Hira",
    "katakana": "Kana",
    "han": "Hani",
    "hanzi": "Hani",
    "chinese": "Hani",
    "kanji": "Hani",
    "greek": "Grek",
    "armenian": "Armn",
    "georgian": "Geor",
    "thai": "Thai",
    "bengali": "Beng",
    "gurmukhi": "Guru",
    "gujarati": "Gujr",
    "tamil": "Taml",
    "sinhala": "Sinh",
    "myanmar": "Mymr",
    "burmese": "Mymr",
    "tibetan": "Tibt",
    "lao": "Laoo",
    "glagolitic": "Glag",
    "runic": "Runr",
    "ogham": "Ogam",
    "phoenician": "Phnx",
    "cans": "Cans",
    "unified canadian aboriginal syllabics": "Cans",
    "canadian syllabics": "Cans",
}

# Also accept the ISO-15924 codes themselves (case-insensitive)
_ISO_LOWER: dict[str, str] = {k.lower(): k for k in SCRIPT_REGISTRY}


def normalize_script_tag(label: str) -> Optional[str]:
    """Map a free-form script label to its ISO-15924 code.

    Accepts MMS-style labels (``"latin"``, ``"syllabics"``), common English
    names (``"Arabic"``, ``"Hangul"``), and existing ISO-15924 codes in any
    case (``"latn"`` → ``"Latn"``).  Returns ``None`` when unrecognised.

    Examples
    --------
    >>> normalize_script_tag("latin")
    'Latn'
    >>> normalize_script_tag("Cyrillic")
    'Cyrl'
    >>> normalize_script_tag("syllabics")
    'Cans'
    """
    normalised = label.strip().lower()
    # Direct label lookup
    if normalised in _LABEL_MAP:
        return _LABEL_MAP[normalised]
    # ISO-15924 code (case-insensitive)
    if normalised in _ISO_LOWER:
        return _ISO_LOWER[normalised]
    return None
