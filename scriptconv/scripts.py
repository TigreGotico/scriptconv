"""Writing-system identification and metadata.

Provides ISO-15924 script codes, character-range detection, per-language
default script, normalisation of free-form script labels, and bulk text
analysis (dominant-script detection, script distribution, base direction).

The ``Latn`` registry entry covers the IPA Extensions block (U+0250–U+02AF)
and Latin Extended Additional (U+1E00–U+1EFF) in addition to the core Latin
and Latin Extended blocks.  This means IPA characters like ``ɑ``, ``ʃ``,
``ŋ`` are classified as Latin-script by :func:`char_script` and
:func:`detect_script`, which is correct per Unicode but may surprise callers
who expect phonetic symbols to be unrecognised.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from typing import Optional

__all__ = [
    "Script",
    "SCRIPT_REGISTRY",
    "char_script",
    "detect_script",
    "script_distribution",
    "script_runs",
    "base_direction",
    "lang_to_script",
    "script_to_langs",
    "normalize_script_tag",
]


# ---------------------------------------------------------------------------
# Script dataclass
# ---------------------------------------------------------------------------

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
        predominantly belong to this script (e.g. ``((0x0041, 0x005A),)``).
    script_type:
        Typological class of the writing system — one of ``"alphabet"``,
        ``"abjad"``, ``"abugida"``, ``"syllabary"``, ``"logographic"``,
        ``"featural"``, or ``"other"``. Describes how the script encodes
        sounds structurally; it is not a pronunciation claim.
    """

    iso15924: str
    name: str
    direction: str  # "ltr" | "rtl"
    char_ranges: tuple[tuple[int, int], ...]
    script_type: str = "other"


# ---------------------------------------------------------------------------
# Registry — the supported writing systems
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
            (0x0250, 0x02AF),  # IPA Extensions
            (0x1E00, 0x1EFF),  # Latin Extended Additional
            (0x2C60, 0x2C7F),  # Latin Extended-C
            (0xA720, 0xA7FF),  # Latin Extended-D
            (0xAB30, 0xAB6F),  # Latin Extended-E
            (0x10780, 0x107BF),  # Latin Extended-F
            (0x1DF00, 0x1DFFF),  # Latin Extended-G
        ),
    ),
    "Cyrl": Script(
        iso15924="Cyrl",
        name="Cyrillic",
        direction="ltr",
        char_ranges=(
            (0x0400, 0x04FF),
            (0x0500, 0x052F),
            (0x1C80, 0x1C8F),  # Cyrillic Extended-C
            (0x2DE0, 0x2DFF),  # Cyrillic Extended-A
            (0xA640, 0xA69F),  # Cyrillic Extended-B
            (0x1E030, 0x1E08F),  # Cyrillic Extended-D
        ),
    ),
    "Arab": Script(
        iso15924="Arab",
        name="Arabic",
        direction="rtl",
        char_ranges=(
            (0x0600, 0x06FF),
            (0x0750, 0x077F),
            (0x0870, 0x089F),  # Arabic Extended-B
            (0x08A0, 0x08FF),
            (0xFB50, 0xFDFF),
            (0xFE70, 0xFEFC),
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
        char_ranges=((0x0900, 0x097F), (0xA8E0, 0xA8FF)),
    ),
    "Hang": Script(
        iso15924="Hang",
        name="Hangul",
        direction="ltr",
        char_ranges=(
            (0xAC00, 0xD7AF),  # Hangul Syllables
            (0x1100, 0x11FF),  # Hangul Jamo
            (0x3130, 0x318F),  # Hangul Compatibility Jamo
            (0xA960, 0xA97C),  # Hangul Jamo Extended-A
            (0xD7B0, 0xD7FF),  # Hangul Jamo Extended-B
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
        char_ranges=(
            (0x30A0, 0x30FF),
            (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
        ),
    ),
    "Hani": Script(
        iso15924="Hani",
        name="Han",
        direction="ltr",
        char_ranges=(
            (0x4E00, 0x9FFF),    # CJK Unified Ideographs
            (0x3400, 0x4DBF),    # CJK Extension A
            (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
            (0x20000, 0x2A6DF),  # CJK Extension B
            (0x2A700, 0x2B73F),  # CJK Extension C
            (0x2B740, 0x2B81F),  # CJK Extension D
            (0x2B820, 0x2CEAF),  # CJK Extension E
            (0x2CEB0, 0x2EBEF),  # CJK Extension F
            (0x2F800, 0x2FA1F),  # CJK Compatibility Ideographs Supplement
            (0x30000, 0x3134F),  # CJK Extension G
            (0x31350, 0x323AF),  # CJK Extension H
            (0x323B0, 0x3347F),  # CJK Extension J
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
        char_ranges=((0x10A0, 0x10FF), (0x2D00, 0x2D2F), (0x1C90, 0x1CBF)),
    ),
    "Ethi": Script(
        iso15924="Ethi",
        name="Ethiopic",
        direction="ltr",
        char_ranges=(
            (0x1200, 0x137F),
            (0x1380, 0x139F),
            (0x2D80, 0x2DDF),   # Ethiopic Extended
            (0xAB00, 0xAB2F),   # Ethiopic Extended-A
            (0x1E7E0, 0x1E7FF),  # Ethiopic Extended-B
        ),
    ),
    "Khmr": Script(
        iso15924="Khmr",
        name="Khmer",
        direction="ltr",
        char_ranges=(
            (0x1780, 0x17FF),
            (0x19E0, 0x19FF),  # Khmer Symbols
        ),
    ),
    "Telu": Script(
        iso15924="Telu",
        name="Telugu",
        direction="ltr",
        char_ranges=((0x0C00, 0x0C7F),),
    ),
    "Knda": Script(
        iso15924="Knda",
        name="Kannada",
        direction="ltr",
        char_ranges=((0x0C80, 0x0CFF),),
    ),
    "Mlym": Script(
        iso15924="Mlym",
        name="Malayalam",
        direction="ltr",
        char_ranges=((0x0D00, 0x0D7F),),
    ),
    "Orya": Script(
        iso15924="Orya",
        name="Odia",
        direction="ltr",
        char_ranges=((0x0B00, 0x0B7F),),
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
        char_ranges=(
            (0x0B80, 0x0BFF),
            (0x11FC0, 0x11FFF),  # Tamil Supplement
        ),
    ),
    "Sinh": Script(
        iso15924="Sinh",
        name="Sinhala",
        direction="ltr",
        char_ranges=(
            (0x0D80, 0x0DFF),
            (0x111E0, 0x111FF),  # Sinhala Archaic Numbers
        ),
    ),
    "Mymr": Script(
        iso15924="Mymr",
        name="Myanmar",
        direction="ltr",
        char_ranges=(
            (0x1000, 0x109F),
            (0xA9E0, 0xA9FF),   # Myanmar Extended-B
            (0xAA60, 0xAA7F),   # Myanmar Extended-A
            (0x116D0, 0x116FF),  # Myanmar Extended-C
        ),
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
        char_ranges=((0x1681, 0x169C),),
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

# Typological class per script (Daniels & Bright, *The World's Writing
# Systems*, 1996). Kept as a compact map so the registry literal above stays
# focused on codepoint ranges; applied to each entry below.
_SCRIPT_TYPES: dict[str, str] = {
    "Latn": "alphabet", "Cyrl": "alphabet", "Grek": "alphabet",
    "Armn": "alphabet", "Geor": "alphabet", "Glag": "alphabet",
    "Runr": "alphabet", "Ogam": "alphabet", "Tfng": "alphabet",
    "Arab": "abjad", "Hebr": "abjad", "Phnx": "abjad",
    "Deva": "abugida", "Beng": "abugida", "Guru": "abugida",
    "Gujr": "abugida", "Orya": "abugida", "Taml": "abugida",
    "Telu": "abugida", "Knda": "abugida", "Mlym": "abugida",
    "Sinh": "abugida", "Thai": "abugida", "Laoo": "abugida",
    "Mymr": "abugida", "Tibt": "abugida", "Khmr": "abugida",
    "Ethi": "abugida", "Cans": "abugida",
    "Hira": "syllabary", "Kana": "syllabary", "Cprt": "syllabary",
    "Hani": "logographic",
    "Hang": "featural",
}
for _code, _stype in _SCRIPT_TYPES.items():
    if _code in SCRIPT_REGISTRY:
        SCRIPT_REGISTRY[_code] = replace(SCRIPT_REGISTRY[_code], script_type=_stype)


# ---------------------------------------------------------------------------
# Optimised char_script — flat sorted interval list with bisect
#
# Instead of iterating every script × every range on each call, we build a
# single sorted list of (start, script_code) and use ``bisect_right`` to
# find the last range that starts at or before the codepoint.  This is
# O(log n) per character instead of O(n × ranges).
# ---------------------------------------------------------------------------

# Build flat interval list: [(start, code), ...] sorted by start.
# For each codepoint we bisect to find the last interval that starts ≤ cp,
# then check if cp ≤ that interval's end (stored separately).
_INTERVAL_STARTS: list[int] = []
_INTERVAL_ENDS: list[int] = []
_INTERVAL_SCRIPTS: list[str] = []

for _code, _script in SCRIPT_REGISTRY.items():
    for _lo, _hi in _script.char_ranges:
        _INTERVAL_STARTS.append(_lo)
        _INTERVAL_ENDS.append(_hi)
        _INTERVAL_SCRIPTS.append(_code)

# Sort all three lists by start codepoint
_SORTED_INDICES = sorted(range(len(_INTERVAL_STARTS)), key=lambda i: _INTERVAL_STARTS[i])
_SORTED_STARTS = [_INTERVAL_STARTS[i] for i in _SORTED_INDICES]
_SORTED_ENDS = [_INTERVAL_ENDS[i] for i in _SORTED_INDICES]
_SORTED_SCRIPTS = [_INTERVAL_SCRIPTS[i] for i in _SORTED_INDICES]


def char_script(ch: str) -> Optional[str]:
    """Return the ISO-15924 code for a single character, or ``None``.

    Uses O(log n) binary search over the precomputed interval list.
    Characters in the IPA Extensions block (U+0250–U+02AF) and Latin
    Extended Additional (U+1E00–U+1EFF) are classified as ``"Latn"``.

    Examples
    --------
    >>> char_script("A")
    'Latn'
    >>> char_script("ɑ")  # IPA Extension — classified as Latin
    'Latn'
    >>> char_script(" ")
    >>> # None
    """
    if len(ch) != 1:
        return None
    cp = ord(ch)
    # Only the interval immediately at-or-before cp (idx) is ever checked —
    # correct only because SCRIPT_REGISTRY's char_ranges are non-overlapping,
    # so at most one interval can ever contain cp. If ranges ever overlapped,
    # this single-candidate check would silently miss matches.
    idx = bisect_right(_SORTED_STARTS, cp) - 1
    if idx >= 0 and cp <= _SORTED_ENDS[idx]:
        return _SORTED_SCRIPTS[idx]
    return None


# ---------------------------------------------------------------------------
# detect_script — dominant script in a text
# ---------------------------------------------------------------------------

def detect_script(text: str) -> Optional[str]:
    """Return the ISO-15924 code of the dominant script in *text*.

    Counts script-bearing characters only (skips ASCII digits, spaces,
    punctuation, combining marks).  Returns ``None`` for empty or purely
    non-alphabetic input.

    IPA characters (U+0250–U+02AF) are classified as Latin script.
    Combining marks (U+0300–U+036F) are not assigned to any script and
    are skipped.

    Examples
    --------
    >>> detect_script("Hello world")
    'Latn'
    >>> detect_script("ɑɛɔ")  # IPA — classified as Latin
    'Latn'
    >>> detect_script("")
    """
    counts: dict[str, int] = {}
    for ch in text:
        s = char_script(ch)
        if s is not None:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: (counts[k], k))


def script_distribution(text: str) -> dict[str, int]:
    """Return character counts per script in *text*.

    Only characters assigned to a registered script are counted.  The
    result is sorted by count descending.

    Parameters
    ----------
    text:
        Input string (may contain any Unicode characters).

    Returns
    -------
    dict[str, int]
        Mapping of ISO-15924 code to character count, sorted by
        count descending.  Empty dict for empty or purely
        non-alphabetic input.

    Examples
    --------
    >>> script_distribution("Hello Привет мир")
    {'Cyrl': 9, 'Latn': 5}
    >>> script_distribution("日本語ひらがなカタカナ")
    {'Hira': 4, 'Kana': 4, 'Hani': 3}
    """
    counts: dict[str, int] = {}
    for ch in text:
        s = char_script(ch)
        if s is not None:
            counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def script_runs(text: str) -> list[tuple[Optional[str], str]]:
    """Segment *text* into contiguous runs of a single script.

    Returns a list of ``(script, substring)`` pairs in text order, where
    *script* is an ISO-15924 code or ``None``. Script-neutral characters
    (spaces, punctuation, digits, combining marks — anything
    :func:`char_script` maps to ``None``) attach to the preceding run
    rather than starting a new one, following the resolution model of
    Unicode UAX #24; a run of leading neutrals carries ``None``.

    Unlike :func:`detect_script` (which flattens to one dominant script),
    this preserves the structure of mixed-script text — e.g. a Cyrillic
    word embedded in a Latin sentence.

    Examples
    --------
    >>> script_runs("привет hello")
    [('Cyrl', 'привет '), ('Latn', 'hello')]
    >>> script_runs("")
    []
    """
    runs: list[list] = []
    for ch in text:
        s = char_script(ch)
        if runs and (s is None or s == runs[-1][0]):
            runs[-1][1] += ch
        else:
            runs.append([s, ch])
    return [(s, t) for s, t in runs]


def base_direction(text: str) -> str:
    """Detect the base text direction of *text*.

    Returns ``"ltr"`` if the majority of script-bearing characters belong
    to left-to-right scripts, ``"rtl"`` for right-to-left, or ``"mixed"``
    when counts are equal or the input has no script-bearing characters.

    Parameters
    ----------
    text:
        Input string.

    Returns
    -------
    str
        ``"ltr"``, ``"rtl"``, or ``"mixed"``.

    Examples
    --------
    >>> base_direction("Hello world")
    'ltr'
    >>> base_direction("مرحبا بالعالم")
    'rtl'
    >>> base_direction("Hello مرحبا")
    'mixed'
    """
    ltr = 0
    rtl = 0
    for ch in text:
        s = char_script(ch)
        if s is None:
            continue
        script = SCRIPT_REGISTRY.get(s)
        if script is None:
            continue
        if script.direction == "rtl":
            rtl += 1
        else:
            ltr += 1
    if ltr > rtl:
        return "ltr"
    if rtl > ltr:
        return "rtl"
    return "mixed"


# ---------------------------------------------------------------------------
# lang_to_script — default script per language primary subtag
#
# Default script per language, from ISO 15924 / BCP-47 conventions and
# the language coverage of Meta's MMS (Massively Multilingual Speech).
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
    "ug": "Arab", "ku": "Arab", "ckb": "Arab",
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
    "am": "Ethi", "ti": "Ethi",
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
    # Kannada
    "kn": "Knda",
    # Malayalam
    "ml": "Mlym",
    # Odia (Oriya)
    "or": "Orya",
    # Myanmar
    "my": "Mymr",
    # Tibetan
    "bo": "Tibt",
    # Lao
    "lo": "Laoo",
    # Additional Latin-script languages
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
    # Languages with no ISO 639-1 code (keyed by their 639-3 code directly)
    "kjh": "Cyrl",  # Khakas
    "xal": "Cyrl",  # Kalmyk (Cyrillic since 1938)
    "kbd": "Cyrl",  # Kabardian
    "erz": "Cyrl",  # Erzya
    "mdf": "Cyrl",  # Moksha
}

# ISO 639-2/3 (incl. bibliographic variants) -> the 639-1 key used above.
# Reference: Library of Congress ISO 639-2 code list.
_ISO639_ALIASES: dict[str, str] = {
    "rus": "ru", "ukr": "uk", "bel": "be", "bul": "bg", "srp": "sr",
    "mkd": "mk", "mac": "mk", "kaz": "kk", "kir": "ky", "tgk": "tg",
    "mon": "mn", "tat": "tt", "bak": "ba", "chv": "cv", "oss": "os",
    "che": "ce", "hye": "hy", "arm": "hy", "kat": "ka", "geo": "ka",
    "aze": "az", "uzb": "uz", "tuk": "tk", "eng": "en", "deu": "de",
    "ger": "de", "fra": "fr", "fre": "fr", "spa": "es", "por": "pt",
    "ita": "it", "nld": "nl", "dut": "nl", "ell": "el", "gre": "el",
    "ara": "ar", "heb": "he", "zho": "zh", "chi": "zh", "jpn": "ja",
    "kor": "ko", "tur": "tr", "fas": "fa", "per": "fa", "urd": "ur",
    "hin": "hi", "tha": "th", "vie": "vi", "pol": "pl", "ces": "cs",
    "cze": "cs", "slk": "sk", "slo": "sk", "ron": "ro", "rum": "ro",
    "hun": "hu", "fin": "fi", "swe": "sv", "nor": "no", "dan": "da",
    "isl": "is", "ice": "is", "mya": "my", "bur": "my", "khm": "km",
    "lao": "lo", "amh": "am", "tam": "ta", "tel": "te", "ben": "bn",
    "guj": "gu", "kan": "kn", "mal": "ml", "mar": "mr", "pan": "pa",
    "sin": "si", "nep": "ne", "eus": "eu", "baq": "eu", "cat": "ca",
    "glg": "gl", "cym": "cy", "wel": "cy", "gle": "ga", "epo": "eo",
}


def lang_to_script(lang: str) -> Optional[str]:
    """Return the ISO-15924 code of the default script for *lang*.

    *lang* may be a BCP-47 tag or bare ISO 639 code.  An explicit ISO-15924
    script subtag is authoritative and is honoured when present
    (``"sr-Latn"`` → ``"Latn"``, ``"uz-Cyrl"`` → ``"Cyrl"``); otherwise the
    default script for the primary subtag is returned (``"pt-BR"`` → ``"pt"``).
    Returns ``None`` when the language is unknown.

    Examples
    --------
    >>> lang_to_script("pt-BR")
    'Latn'
    >>> lang_to_script("ru")
    'Cyrl'
    >>> lang_to_script("sr-Latn")
    'Latn'
    """
    subtags = lang.replace("_", "-").split("-")
    # An explicit script subtag overrides the language's default script:
    # 4-letter ISO-15924 codes ("sr-Latn"), and the widespread informal
    # 3-letter forms "cyr"/"lat" ("uzb_cyr", "aze_lat").
    for sub in subtags[1:]:
        low = sub.lower()
        if len(sub) == 4 and sub.isalpha():
            resolved = normalize_script_tag(sub)
            if resolved is not None:
                return resolved
        elif low in ("cyr", "lat"):
            return "Cyrl" if low == "cyr" else "Latn"
    key = subtags[0].lower()
    if key in _LANG_TO_SCRIPT:
        return _LANG_TO_SCRIPT[key]
    return _LANG_TO_SCRIPT.get(_ISO639_ALIASES.get(key, ""))


# ---------------------------------------------------------------------------
# script_to_langs — reverse of lang_to_script
# ---------------------------------------------------------------------------

_SCRIPT_TO_LANGS: dict[str, list[str]] = {}
for _lang, _script in _LANG_TO_SCRIPT.items():
    _SCRIPT_TO_LANGS.setdefault(_script, []).append(_lang)


def script_to_langs(code: str) -> list[str]:
    """Return the languages whose default script is *code*.

    Parameters
    ----------
    code:
        ISO-15924 script code (e.g. ``"Latn"``).

    Returns
    -------
    list[str]
        Sorted list of ISO 639 language codes.  Empty list for
        unknown scripts.

    Examples
    --------
    >>> script_to_langs("Cyrl")
    ['av', 'ba', 'be', 'bg', 'bxr', 'ce', 'cv', 'kk', 'ky', 'mk', ...]
    >>> script_to_langs("Latn")  # doctest: +SKIP
    ['af', 'ast', 'az', ...]
    """
    return sorted(_SCRIPT_TO_LANGS.get(code, []))


# ---------------------------------------------------------------------------
# normalize_script_tag — free-form labels → ISO-15924
#
# Free-form and MMS-style labels mapped to ISO 15924.
# ---------------------------------------------------------------------------

_LABEL_MAP: dict[str, str] = {
    # MMS-style lowercase labels
    "latin": "Latn",
    "cyrillic": "Cyrl",
    "arabic": "Arab",
    "syllabics": "Cans",
    "tifinagh": "Tfng",
    "devanagari": "Deva",
    "ethiopic": "Ethi",
    "khmer": "Khmr",
    "telugu": "Telu",
    "kannada": "Knda",
    "malayalam": "Mlym",
    "odia": "Orya",
    "oriya": "Orya",
    "persian": "Arab",
    "farsi": "Arab",
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
    # Additional common labels
    "japanese": "Hira",
    "jamo": "Hang",
    "hangul jamo": "Hang",
    "devanagari extended": "Deva",
    "ipa": "Latn",
    "cjk": "Hani",
    "chinese characters": "Hani",
    "han characters": "Hani",
    "hangeul": "Hang",
    "bangla": "Beng",
    "punjabi": "Guru",
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
    >>> normalize_script_tag("japanese")
    'Hira'
    >>> normalize_script_tag("jamo")
    'Hang'
    """
    normalised = label.strip().lower()
    # Direct label lookup
    if normalised in _LABEL_MAP:
        return _LABEL_MAP[normalised]
    # ISO-15924 code (case-insensitive)
    if normalised in _ISO_LOWER:
        return _ISO_LOWER[normalised]
    return None
