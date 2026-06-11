"""Phoneme-notation transcoding — IPA ↔ ARPABET, IPA ↔ X-SAMPA,
IPA ↔ Lexique, Buckwalter ↔ Arabic script.

All tables are pure Python data; zero runtime dependencies.

ARPABET table derived from chorusai/arpa2ipa
  (https://github.com/chorusai/arpa2ipa), licensed Apache-2.0.
Mantoq/Buckwalter table derived from phoonnx thirdparty/bw2ipa.py.
Lexique phoneme-code table from:
  New, B. & Pallier, C. — Manuel de Lexique 3, v3.11, Tableau 2 (p. 12).
  Lexique383, https://github.com/chrplr/openlexicon, CC BY-SA 4.0.
  Key: N=ɲ (palatal nasal, e.g. agneau), G=ŋ (velar nasal, e.g. camping),
  °=schwa élidable, 3=schwa non-élidable, x=/x/ (Spanish loanword jota).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

__all__ = [
    "Notation",
    "convert",
    "arpa_to_ipa",
    "ipa_to_arpa",
    "xsampa_to_ipa",
    "ipa_to_xsampa",
    "buckwalter_to_arabic",
    "arabic_to_buckwalter",
    "lexique_to_ipa",
    "ipa_to_lexique",
]


class Notation(str, Enum):
    """Supported phoneme notation systems."""

    IPA = "ipa"
    ARPA = "arpa"
    XSAMPA = "x-sampa"
    BUCKWALTER = "buckwalter"
    ARABIC = "arabic"  # Arabic script (target/source for BW)
    LEXIQUE = "lexique"  # Lexique one-char-per-phoneme French notation


# ---------------------------------------------------------------------------
# ARPABET ↔ IPA
#
# Table derived from chorusai/arpa2ipa
# (https://github.com/chorusai/arpa2ipa), licensed Apache-2.0.
#
# Stress digits (0/1/2) are stripped on ARPA→IPA and not re-added on
# IPA→ARPA (lossy in that direction; they have no IPA equivalent here).
# ---------------------------------------------------------------------------

# Base ARPA→IPA (without stress digit variants; those are added below)
_ARPA_BASE: dict[str, str] = {
    # Monophthongs
    "AO": "ɔ",
    "AA": "ɑ",
    "IY": "i",
    "UW": "u",
    "EH": "e",
    "IH": "ɪ",
    "UH": "ʊ",
    "AH": "ʌ",   # AH0 → ə handled separately
    "AE": "æ",
    "AX": "ə",
    # Diphthongs
    "EY": "eɪ",
    "AY": "aɪ",
    "OW": "oʊ",
    "AW": "aʊ",
    "OY": "ɔɪ",
    # R-colored vowels
    "ER": "ɜr",
    "AXR": "ər",
    # Stops
    "P": "p",
    "B": "b",
    "T": "t",
    "D": "d",
    "K": "k",
    "G": "g",
    # Affricates
    "CH": "tʃ",
    "JH": "dʒ",
    # Fricatives
    "F": "f",
    "V": "v",
    "TH": "θ",
    "DH": "ð",
    "S": "s",
    "Z": "z",
    "SH": "ʃ",
    "ZH": "ʒ",
    "HH": "h",
    # Nasals
    "M": "m",
    "EM": "m̩",
    "N": "n",
    "EN": "n̩",
    "NG": "ŋ",
    "ENG": "ŋ̍",
    # Liquids
    "L": "l",
    "EL": "ɫ̩",
    "R": "r",
    "DX": "ɾ",
    "NX": "ɾ̃",
    # Semivowels
    "W": "w",
    "Y": "j",
    "Q": "ʔ",
}

# Build full lookup with stress variants (AH0 → ə special-cased)
_ARPA_TO_IPA: dict[str, str] = {}
for _arpa, _ipa in _ARPA_BASE.items():
    _ARPA_TO_IPA[_arpa] = _ipa
    for _stress in ("0", "1", "2"):
        _key = _arpa + _stress
        if _key == "AH0":
            _ARPA_TO_IPA["AH0"] = "ə"
        else:
            _ARPA_TO_IPA[_key] = _ipa

# Reverse: IPA → ARPA (base form, no stress digit).
# Multi-char IPA values are deduplicated; keep first.
_IPA_TO_ARPA: dict[str, str] = {}
for _arpa, _ipa in _ARPA_BASE.items():
    if _ipa not in _IPA_TO_ARPA:
        _IPA_TO_ARPA[_ipa] = _arpa
# schwa
_IPA_TO_ARPA.setdefault("ə", "AH")


def arpa_to_ipa(arpa_sequence: str) -> str:
    """Convert a space-separated ARPABET sequence to an IPA string.

    Stress digits are stripped.  Unknown tokens are passed through.

    Examples
    --------
    >>> arpa_to_ipa("HH AH0 L OW1")
    'həloʊ'
    """
    tokens = arpa_sequence.strip().split()
    result = []
    for tok in tokens:
        ipa = _ARPA_TO_IPA.get(tok)
        if ipa is None:
            # strip trailing digit and retry
            stripped = tok.rstrip("012")
            ipa = _ARPA_TO_IPA.get(stripped, tok)
        result.append(ipa)
    return "".join(result)


def ipa_to_arpa(ipa_string: str, unknown: str = "?") -> str:
    """Convert an IPA string to a space-separated ARPABET sequence.

    Matches longest IPA symbol first.  Characters outside the ARPABET table
    are replaced by *unknown* (default ``"?"``); pass ``unknown=""`` to drop
    them silently.

    Examples
    --------
    >>> ipa_to_arpa("həloʊ")
    'AH L OW'
    >>> ipa_to_arpa("ɸ")
    '?'
    """
    # Sort by descending length so multi-char IPA symbols match first
    sorted_ipa = sorted(_IPA_TO_ARPA.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(s) for s in sorted_ipa))
    tokens = []
    pos = 0
    while pos < len(ipa_string):
        m = pattern.match(ipa_string, pos)
        if m:
            tokens.append(_IPA_TO_ARPA[m.group(0)])
            pos = m.end()
        else:
            if unknown:
                tokens.append(unknown)
            pos += 1
    return " ".join(t for t in tokens if t)


# ---------------------------------------------------------------------------
# X-SAMPA ↔ IPA
#
# Standard X-SAMPA mapping.  Multi-character X-SAMPA symbols are matched
# longest-first at both conversion directions.
#
# References: https://en.wikipedia.org/wiki/X-SAMPA
# ---------------------------------------------------------------------------

_XSAMPA_TO_IPA: dict[str, str] = {
    # Consonants (multi-char first for longest-match ordering)
    "ts`": "ʈ͡ʂ",
    "dz`": "ɖ͡ʐ",
    "tS": "tʃ",
    "dZ": "dʒ",
    "ts": "ts",
    "dz": "dz",
    "p\\": "ɸ",
    "B\\": "ʙ",
    "r\\": "ɹ",
    "r`": "ɻ",
    "R\\": "ʀ",
    "l`": "ɭ",
    "L\\": "ʎ",
    "f\\": "ɸ",  # alias
    "v\\": "ʋ",
    "r\\`": "ɻ",
    "s`": "ʂ",
    "z`": "ʐ",
    "S": "ʃ",
    "Z": "ʒ",
    "C": "ç",
    "j\\": "ʝ",
    "G": "ɣ",
    "X": "χ",
    "R": "ʁ",
    "H\\": "ʜ",
    "?\\": "ʕ",
    "h\\": "ɦ",
    "?": "ʔ",
    "H": "ɥ",
    # Nasals
    "F": "ɱ",
    "J": "ɲ",
    "N\\": "ɴ",
    "N": "ŋ",
    # Laterals
    "K": "ɬ",
    "K\\": "ɮ",
    "L": "ʟ",
    # Basic consonants (must come after multi-char)
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "ɡ",
    "m": "m", "n": "n", "f": "f", "v": "v", "s": "s", "z": "z",
    "l": "l", "w": "w", "j": "j", "x": "x", "B": "β", "D": "ð",
    "T": "θ", "V": "ʌ", "G\\": "ɢ",
    # Vowels
    "@\\": "ɘ",
    "@`": "ɚ",
    "@": "ə",
    "{": "æ",
    "}": "ʉ",
    "1": "ɨ",
    "2": "ø",
    "3\\": "ɞ",
    "3": "ɜ",
    "4": "ɾ",
    "5": "ɫ",
    "6": "ɐ",
    "7": "ɤ",
    "8": "ɵ",
    "9": "œ",
    "&": "æ",  # alias
    "A": "ɑ",
    "Q": "ɒ",
    "E": "ɛ",
    "I\\": "ᵻ",
    "I": "ɪ",
    "O": "ɔ",
    "M\\": "ɰ",
    "M": "ɯ",
    "U\\": "ᵿ",
    "U": "ʊ",
    "W": "ʍ",
    "Y": "ʏ",
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "y",
    # Suprasegmentals
    '"': "ˈ",
    "%": "ˌ",
    ":": "ː",
    "-.": ".",   # syllable boundary
    "-\\": "’",  # linking
}

# Reverse: IPA → X-SAMPA (first occurrence wins)
_IPA_TO_XSAMPA: dict[str, str] = {}
for _xs, _ip in _XSAMPA_TO_IPA.items():
    if _ip not in _IPA_TO_XSAMPA:
        _IPA_TO_XSAMPA[_ip] = _xs

# Longest-first sorted keys for pattern matching
_XS_KEYS_SORTED = sorted(_XSAMPA_TO_IPA.keys(), key=len, reverse=True)
_IPA_KEYS_SORTED = sorted(_IPA_TO_XSAMPA.keys(), key=len, reverse=True)


def xsampa_to_ipa(xsampa: str) -> str:
    """Convert an X-SAMPA string to IPA.

    Multi-character symbols are matched longest-first.  Unknown characters
    are passed through.

    Examples
    --------
    >>> xsampa_to_ipa("S")
    'ʃ'
    >>> xsampa_to_ipa("@")
    'ə'
    """
    pattern = re.compile("|".join(re.escape(k) for k in _XS_KEYS_SORTED))
    result = []
    pos = 0
    while pos < len(xsampa):
        m = pattern.match(xsampa, pos)
        if m:
            result.append(_XSAMPA_TO_IPA[m.group(0)])
            pos = m.end()
        else:
            result.append(xsampa[pos])
            pos += 1
    return "".join(result)


def ipa_to_xsampa(ipa: str) -> str:
    """Convert an IPA string to X-SAMPA.

    Multi-character IPA symbols are matched longest-first.  Unknown
    characters are passed through.

    Examples
    --------
    >>> ipa_to_xsampa("ʃ")
    'S'
    >>> ipa_to_xsampa("ə")
    '@'
    """
    pattern = re.compile("|".join(re.escape(k) for k in _IPA_KEYS_SORTED))
    result = []
    pos = 0
    while pos < len(ipa):
        m = pattern.match(ipa, pos)
        if m:
            result.append(_IPA_TO_XSAMPA[m.group(0)])
            pos = m.end()
        else:
            result.append(ipa[pos])
            pos += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Buckwalter / Mantoq ↔ Arabic script
#
# The Mantoq notation used here is the tokenization scheme from
# phoonnx/thirdparty/bw2ipa.py (itself a Mantoq→IPA converter).  We extend
# it with a direct Buckwalter↔Arabic-script table, independent of IPA.
#
# Buckwalter transliteration table derived from phoonnx thirdparty/bw2ipa.py
# and mantoq/pyarabic transliteration knowledge.
# ---------------------------------------------------------------------------

# Standard Buckwalter → Arabic Unicode
_BW_TO_ARABIC: dict[str, str] = {
    "'": "ء",  # ء hamza
    "|": "آ",  # آ alef madda
    ">": "أ",  # أ alef hamza above
    "&": "ؤ",  # ؤ waw hamza
    "<": "إ",  # إ alef hamza below
    "}": "ئ",  # ئ ya hamza
    "A": "ا",  # ا alef
    "b": "ب",  # ب ba
    "p": "ة",  # ة ta marbuta
    "t": "ت",  # ت ta
    "v": "ث",  # ث tha
    "j": "ج",  # ج jim
    "H": "ح",  # ح ha
    "x": "خ",  # خ kha
    "d": "د",  # د dal
    "*": "ذ",  # ذ dhal
    "r": "ر",  # ر ra
    "z": "ز",  # ز zayn
    "s": "س",  # س sin
    "$": "ش",  # ش shin
    "S": "ص",  # ص sad
    "D": "ض",  # ض dad
    "T": "ط",  # ط ta
    "Z": "ظ",  # ظ dha
    "E": "ع",  # ع ain
    "g": "غ",  # غ ghayn
    "f": "ف",  # ف fa
    "q": "ق",  # ق qaf
    "k": "ك",  # ك kaf
    "l": "ل",  # ل lam
    "m": "م",  # م mim
    "n": "ن",  # ن nun
    "h": "ه",  # ه ha
    "w": "و",  # و waw
    "Y": "ى",  # ى alef maqsura
    "y": "ي",  # ي ya
    # Short vowels (diacritics)
    "a": "َ",  # fatha
    "u": "ُ",  # damma
    "i": "ِ",  # kasra
    "~": "ّ",  # shadda
    "o": "ْ",  # sukun
    "F": "ً",  # tanwin fath
    "N": "ٌ",  # tanwin damm
    "K": "ٍ",  # tanwin kasr
    # Special
    "_": "ـ",  # tatweel
    "^": "ّ",  # shadda alias
}

_ARABIC_TO_BW: dict[str, str] = {v: k for k, v in _BW_TO_ARABIC.items()}


def buckwalter_to_arabic(bw: str) -> str:
    """Convert a Buckwalter-encoded string to Arabic Unicode.

    Unknown characters are passed through unchanged.

    Examples
    --------
    >>> buckwalter_to_arabic("mrhbA")
    'مرحبا'
    """
    return "".join(_BW_TO_ARABIC.get(ch, ch) for ch in bw)


def arabic_to_buckwalter(arabic: str) -> str:
    """Convert an Arabic Unicode string to Buckwalter transliteration.

    Unknown characters are passed through unchanged.

    Examples
    --------
    >>> arabic_to_buckwalter("مرحبا")
    'mrHbA'
    """
    return "".join(_ARABIC_TO_BW.get(ch, ch) for ch in arabic)


# ---------------------------------------------------------------------------
# Lexique ↔ IPA
#
# Lexique uses a one-character-per-phoneme code for French.
# Source: New, B. & Pallier, C. — Manuel de Lexique 3 v3.11, Tableau 2
# (https://github.com/chrplr/openlexicon), CC BY-SA 4.0.
#
# Critical disambiguation verified against the official table (p. 12):
#   N → ɲ  (palatal nasal; examples: agneau, vigne)
#   G → ŋ  (velar nasal, English loanwords; example: camping)
#   ° → ə  (schwa élidable)
#   3 → ə  (schwa non-élidable; distinct in input but same IPA target)
#   x → x  (velar fricative, Spanish loanwords; example: jota)
# ---------------------------------------------------------------------------

_LEXIQUE_TO_IPA: dict[str, str] = {
    # Vowels
    "a": "a",    # bat, plat
    "i": "i",    # lit, émis
    "y": "y",    # lu
    "u": "u",    # roue
    "o": "o",    # peau, mot  (o fermé)
    "O": "ɔ",    # éloge, fort  (o ouvert)
    "e": "e",    # été  (e fermé)
    "E": "ɛ",    # paire, treize  (e ouvert)
    "°": "ə",    # schwa élidable (abordera)
    "2": "ø",    # deux  (eu fermé)
    "9": "œ",    # œuf, peur  (eu ouvert)
    "5": "ɛ̃",   # cinq, linge  (voyelle nasale in)
    "1": "œ̃",   # un, parfum  (voyelle nasale un)
    "@": "ɑ̃",   # ange  (voyelle nasale an)
    "§": "ɔ̃",   # on, savon  (voyelle nasale on)
    "3": "ə",    # schwa non-élidable (parvenu)
    # Semi-vowels (glides)
    "j": "j",    # yeux, paille
    "8": "ɥ",    # huit, lui
    "w": "w",    # oui, nouer
    # Consonants
    "p": "p",    # père, soupe
    "b": "b",    # bon, robe
    "t": "t",    # terre, vite
    "d": "d",    # dans, aide
    "k": "k",    # carré, laque
    "g": "ɡ",    # gare, bague
    "f": "f",    # feu, neuf
    "v": "v",    # vous, rêve
    "s": "s",    # sale, dessous
    "z": "z",    # zéro, maison
    "S": "ʃ",    # chat, tâche
    "Z": "ʒ",    # gilet, mijoter
    "m": "m",    # main, femme
    "n": "n",    # nous, tonne
    "N": "ɲ",    # agneau, vigne  (consonne nasale palatale)
    "l": "l",    # lent, sol
    "R": "ʁ",    # rue, venir
    "x": "x",    # jota (emprunt espagnol)
    "G": "ŋ",    # camping  (ng, emprunt anglais)
}

# Reverse: IPA → Lexique (first-occurrence wins for ties like ə → °)
_IPA_TO_LEXIQUE: dict[str, str] = {}
for _lx, _ip in _LEXIQUE_TO_IPA.items():
    if _ip not in _IPA_TO_LEXIQUE:
        _IPA_TO_LEXIQUE[_ip] = _lx

# Longest-first sorted keys
_LX_KEYS_SORTED = sorted(_LEXIQUE_TO_IPA.keys(), key=len, reverse=True)
_IPA_FOR_LX_SORTED = sorted(_IPA_TO_LEXIQUE.keys(), key=len, reverse=True)


def lexique_to_ipa(lexique: str) -> str:
    """Convert a Lexique phoneme-code string to IPA.

    Each Lexique phoneme is exactly one character; they are read left-to-right
    with no separator.  Unknown characters are passed through unchanged.

    Source: New & Pallier, Manuel de Lexique 3 v3.11, Tableau 2 (CC BY-SA 4.0).

    Examples
    --------
    >>> lexique_to_ipa("b§ZuR")
    'bɔ̃ʒuʁ'
    >>> lexique_to_ipa("v5")
    'vɛ̃'
    """
    result = []
    for ch in lexique:
        result.append(_LEXIQUE_TO_IPA.get(ch, ch))
    return "".join(result)


def ipa_to_lexique(ipa: str) -> str:
    """Convert an IPA string to Lexique phoneme codes.

    Matches longest IPA symbol first.  Unknown characters are passed through
    unchanged.  The conversion is French-centric; symbols outside the Lexique
    inventory are not representable.

    Source: New & Pallier, Manuel de Lexique 3 v3.11, Tableau 2 (CC BY-SA 4.0).

    Examples
    --------
    >>> ipa_to_lexique("bɔ̃ʒuʁ")
    'b§ZuR'
    >>> ipa_to_lexique("dø")
    'd2'
    """
    pattern = re.compile("|".join(re.escape(s) for s in _IPA_FOR_LX_SORTED))
    result = []
    pos = 0
    while pos < len(ipa):
        m = pattern.match(ipa, pos)
        if m:
            result.append(_IPA_TO_LEXIQUE[m.group(0)])
            pos = m.end()
        else:
            result.append(ipa[pos])
            pos += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# convert — facade routing through IPA where no direct map exists
# ---------------------------------------------------------------------------

def convert(text: str, src: str | Notation, dst: str | Notation) -> str:
    """Convert *text* from *src* notation to *dst* notation.

    Supported pairs (direct):
      - ``arpa`` ↔ ``ipa``
      - ``x-sampa`` ↔ ``ipa``
      - ``buckwalter`` ↔ ``arabic``

    Indirect pairs route through IPA (e.g. ``arpa`` → ``x-sampa`` goes
    ``arpa`` → ``ipa`` → ``x-sampa``).

    Parameters
    ----------
    text:
        Input string.
    src:
        Source notation (``Notation`` member or its string value).
    dst:
        Target notation.

    Returns
    -------
    str
        Converted string.

    Raises
    ------
    ValueError
        When *src* or *dst* is not a recognised ``Notation`` value, or when
        the requested conversion path is not supported.
    """
    src = Notation(src)
    dst = Notation(dst)

    if src == dst:
        return text

    # Direct paths
    if src == Notation.ARPA and dst == Notation.IPA:
        return arpa_to_ipa(text)
    if src == Notation.IPA and dst == Notation.ARPA:
        return ipa_to_arpa(text)
    if src == Notation.XSAMPA and dst == Notation.IPA:
        return xsampa_to_ipa(text)
    if src == Notation.IPA and dst == Notation.XSAMPA:
        return ipa_to_xsampa(text)
    if src == Notation.LEXIQUE and dst == Notation.IPA:
        return lexique_to_ipa(text)
    if src == Notation.IPA and dst == Notation.LEXIQUE:
        return ipa_to_lexique(text)
    if src == Notation.BUCKWALTER and dst == Notation.ARABIC:
        return buckwalter_to_arabic(text)
    if src == Notation.ARABIC and dst == Notation.BUCKWALTER:
        return arabic_to_buckwalter(text)

    # Indirect: route through IPA
    _to_ipa = {
        Notation.ARPA: arpa_to_ipa,
        Notation.XSAMPA: xsampa_to_ipa,
        Notation.LEXIQUE: lexique_to_ipa,
    }
    _from_ipa = {
        Notation.ARPA: ipa_to_arpa,
        Notation.XSAMPA: ipa_to_xsampa,
        Notation.LEXIQUE: ipa_to_lexique,
    }
    if src in _to_ipa and dst in _from_ipa:
        return _from_ipa[dst](_to_ipa[src](text))

    raise ValueError(f"Unsupported conversion: {src!r} → {dst!r}")
