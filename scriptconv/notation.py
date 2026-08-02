"""Phoneme-notation transcoding — IPA ↔ ARPABET, IPA ↔ X-SAMPA,
IPA ↔ Lexique, IPA ↔ Kirshenbaum, Buckwalter ↔ Arabic script.

All tables are pure Python data; zero runtime dependencies.

ARPABET table derived from chorusai/arpa2ipa
  (https://github.com/chorusai/arpa2ipa), licensed Apache-2.0.
Buckwalter ↔ Arabic table follows Tim Buckwalter's transliteration scheme.
Lexique phoneme-code table from:
  New, B. & Pallier, C. — Manuel de Lexique 3, v3.11, Tableau 2 (p. 12).
  Lexique383, https://github.com/chrplr/openlexicon, CC BY-SA 4.0.
  Key: N=ɲ (palatal nasal, e.g. agneau), G=ŋ (velar nasal, e.g. camping),
  °=schwa élidable, 3=schwa non-élidable, x=/x/ (Spanish loanword jota).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Notation",
    "NotationInfo",
    "NOTATION_INFO",
    "convert",
    "can_convert",
    "convert_batch",
    "arpa_to_ipa",
    "ipa_to_arpa",
    "xsampa_to_ipa",
    "ipa_to_xsampa",
    "buckwalter_to_arabic",
    "arabic_to_buckwalter",
    "lexique_to_ipa",
    "ipa_to_lexique",
    "kirshenbaum_to_ipa",
    "ipa_to_kirshenbaum",
    "cotovia_to_ipa",
    "ipa_to_cotovia",
    "rfe_to_ipa",
    "ipa_to_rfe",
    "mantoq_to_ipa",
    "looks_like_ipa",
]


class Notation(str, Enum):
    """Supported phoneme notation systems."""

    IPA = "ipa"
    ARPA = "arpa"
    XSAMPA = "x-sampa"
    BUCKWALTER = "buckwalter"
    ARABIC = "arabic"  # Arabic script (target/source for BW)
    LEXIQUE = "lexique"  # Lexique one-char-per-phoneme French notation
    KIRSHENBAUM = "kirshenbaum"  # ASCII-IPA (espeak-ng native notation)
    COTOVIA = "cotovia"  # Universidade de Vigo Cotovía TTS notation (gl)
    RFE = "rfe"
    MANTOQ = "mantoq"  # Revista de Filología Española phonetic alphabet

    def __repr__(self) -> str:
        return f"Notation.{self.name}"


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
    "G": "ɡ",   # script g U+0261 — canonical IPA, matches X-SAMPA/Lexique tables
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
# Accept ASCII "g" (U+0067) as well as canonical script "ɡ" (U+0261) on input.
_IPA_TO_ARPA.setdefault("g", "G")
# Bare/long NURSE vowel (non-rhotic British ɜ, ɜː) has no dedicated ARPA symbol —
# ARPABET is rhotic-only, so it collapses onto the same "ER" as the r-colored ɜr.
_IPA_TO_ARPA.setdefault("ɜː", "ER")
_IPA_TO_ARPA.setdefault("ɜ", "ER")

# Precompiled regex for IPA → ARPA (longest-first)
_IPA_ARPA_KEYS_SORTED = sorted(_IPA_TO_ARPA.keys(), key=len, reverse=True)
_IPA_ARPA_RE = re.compile("|".join(re.escape(s) for s in _IPA_ARPA_KEYS_SORTED))

# ARPABET vowel class — the symbols that carry stress digits.
_ARPA_VOWELS = {"AO", "AA", "IY", "UW", "EH", "IH", "UH", "AH", "AE", "AX",
                "EY", "AY", "OW", "AW", "OY", "ER", "AXR"}
_STRESS_MARKS = {"ˈ": "1", "ˌ": "2"}  # IPA primary/secondary stress



class UnknownSymbolError(ValueError):
    """A symbol has no mapping in the requested notation (``errors="strict"``)."""

    def __init__(self, symbol: str, position: int, notation: str):
        self.symbol = symbol
        self.position = position
        self.notation = notation
        super().__init__(
            f"no {notation} mapping for {symbol!r} at position {position}")


_ERROR_POLICIES = ("pass", "replace", "strict", "ignore")


def _unknown(symbol: str, position: int, notation: str, errors: str,
             replacement: str = "?") -> str:
    """Resolve one unmapped symbol according to the codecs-style policy."""
    if errors == "pass":
        return symbol
    if errors == "replace":
        return replacement
    if errors == "ignore":
        return ""
    if errors == "strict":
        raise UnknownSymbolError(symbol, position, notation)
    raise ValueError(f"errors must be one of {_ERROR_POLICIES}, not {errors!r}")


def arpa_to_ipa(arpa_sequence: str, errors: str = "pass",
                stress: bool = False) -> str:
    """Convert a space-separated ARPABET sequence to an IPA string.

    With ``stress=True``, ARPABET stress digits are preserved as IPA stress
    marks placed immediately before the stressed vowel's symbol: ``AH1`` →
    ``ˈʌ``, ``AH2`` → ``ˌʌ``, ``AH0`` → unmarked (a purely notational,
    reversible convention — no syllabification is performed).  The default
    ``stress=False`` keeps the historical behavior of stripping the digits.
    ``errors`` selects the unknown-token policy: ``"pass"`` (default) keeps
    the token, ``"replace"`` substitutes ``?``, ``"ignore"`` drops it,
    ``"strict"`` raises :class:`UnknownSymbolError`.

    Examples
    --------
    >>> arpa_to_ipa("HH AH0 L OW1")
    'həloʊ'
    """
    tokens = arpa_sequence.strip().split()
    result = []
    for i, tok in enumerate(tokens):
        mark = ""
        if stress and tok[-1:] in ("1", "2") and tok[:-1] in _ARPA_VOWELS:
            mark = "ˈ" if tok[-1] == "1" else "ˌ"
        ipa = _ARPA_TO_IPA.get(tok)
        if ipa is None:
            # strip trailing digit and retry
            stripped = tok.rstrip("012")
            ipa = _ARPA_TO_IPA.get(stripped)
        if ipa is None:
            ipa = _unknown(tok, i, "arpa", errors)
            mark = ""
        result.append(mark + ipa)
    return "".join(result)


def ipa_to_arpa(ipa_string: str, unknown: str = "?",
                errors: str = "replace", stress: bool = False) -> str:
    """Convert an IPA string to a space-separated ARPABET sequence.

    Matches longest IPA symbol first.  With ``stress=True``, IPA stress
    marks (``ˈ``/``ˌ``) preceding a vowel-class symbol are emitted as that
    vowel's stress digit (``1``/``2``) and unmarked vowels receive ``0`` —
    the reverse of :func:`arpa_to_ipa`'s ``stress=True`` convention.
    ``errors`` selects the unknown-symbol policy (default ``"replace"``,
    preserving the historical behavior of substituting *unknown*, ``"?"``);
    ``unknown=""`` still drops silently.  Combining marks and modifier
    letters qualify the preceding phoneme and are always dropped rather
    than treated as unknowns.

    Examples
    --------
    >>> ipa_to_arpa("həloʊ")
    'HH AX L OW'
    >>> ipa_to_arpa("ɸ")
    '?'
    """
    tokens = []
    pending_stress = ""
    pos = 0
    while pos < len(ipa_string):
        if stress and ipa_string[pos] in _STRESS_MARKS:
            pending_stress = _STRESS_MARKS[ipa_string[pos]]
            pos += 1
            continue
        m = _IPA_ARPA_RE.match(ipa_string, pos)
        if m:
            tok = _IPA_TO_ARPA[m.group(0)]
            if stress and tok in _ARPA_VOWELS:
                # CMUdict spells schwa as AH0 (it has no AX), so stress-aware
                # output uses AH for exact round-trips; extended-ARPABET AX
                # input still normalizes to AH0 (documented residue).
                if m.group(0) == "ə":
                    tok = "AH"
                tok += pending_stress or "0"
            pending_stress = ""
            tokens.append(tok)
            pos = m.end()
        else:
            ch = ipa_string[pos]
            # Diacritics and suprasegmentals (combining marks, length/stress
            # modifier letters) have no ARPABET equivalent; they qualify the
            # preceding phoneme rather than standing alone, so drop them
            # instead of emitting a spurious *unknown* token.
            if unicodedata.category(ch) not in ("Mn", "Mc", "Me", "Lm", "Sk"):
                effective = "ignore" if (errors == "replace" and not unknown) else errors
                out = _unknown(ch, pos, "arpa", effective, replacement=unknown)
                if out:
                    tokens.append(out)
            pos += 1
    return " ".join(tokens)


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
    "r": "r",     # plain r = alveolar TRILL in canonical X-SAMPA (tap is "4")
    "r`": "ɽ",    # retroflex FLAP (not approximant)
    "R\\": "ʀ",
    "l`": "ɭ",
    "L\\": "ʎ",
    "f\\": "ɸ",   # alias for p\
    "v\\": "ʋ",
    "r\\`": "ɻ",  # retroflex APPROXIMANT
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
    # Retroflex plosives
    "t`": "ʈ",
    "d`": "ɖ",
    # Palatal plosives
    "c": "c",
    "J\\`": "ɟ",
    # Uvular plosive
    "q": "q",
    # Alveolo-palatal fricatives
    "s\\`": "ɕ",
    "z\\`": "ʑ",
    # Retroflex nasal
    "n\\`": "ɳ",
    # Pharyngeal fricative
    "X\\`": "ħ",
    # Lateral flap
    "l\\`": "ɺ",
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
    "-\\": "\u203F",  # undertie (U+203F)
}

# Reverse: IPA → X-SAMPA (first occurrence wins)
_IPA_TO_XSAMPA: dict[str, str] = {}
for _xs, _ip in _XSAMPA_TO_IPA.items():
    if _ip not in _IPA_TO_XSAMPA:
        _IPA_TO_XSAMPA[_ip] = _xs

# Longest-first sorted keys for pattern matching
_XS_KEYS_SORTED = sorted(_XSAMPA_TO_IPA.keys(), key=len, reverse=True)
_IPA_KEYS_SORTED = sorted(_IPA_TO_XSAMPA.keys(), key=len, reverse=True)

# Precompiled regexes
_XS_RE = re.compile("|".join(re.escape(k) for k in _XS_KEYS_SORTED))
_IPA_XS_RE = re.compile("|".join(re.escape(k) for k in _IPA_KEYS_SORTED))


def xsampa_to_ipa(xsampa: str, errors: str = "pass") -> str:
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
    result = []
    pos = 0
    while pos < len(xsampa):
        m = _XS_RE.match(xsampa, pos)
        if m:
            result.append(_XSAMPA_TO_IPA[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(xsampa[pos], pos, "x-sampa", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


def ipa_to_xsampa(ipa: str, errors: str = "pass") -> str:
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
    result = []
    pos = 0
    while pos < len(ipa):
        m = _IPA_XS_RE.match(ipa, pos)
        if m:
            result.append(_IPA_TO_XSAMPA[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(ipa[pos], pos, "x-sampa", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Buckwalter ↔ Arabic script
#
# A direct Buckwalter ↔ Arabic-script table (independent of IPA) following
# Tim Buckwalter's published Arabic transliteration scheme (a 1:1 factual
# mapping between Arabic letters and ASCII characters).
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
    "{": "ٱ",  # alef wasla
    "`": "ٰ",  # dagger (superscript) alef
}

_ARABIC_TO_BW: dict[str, str] = {v: k for k, v in _BW_TO_ARABIC.items()}
# Pre-composed lam-alef ligatures (single codepoints) → Buckwalter
_ARABIC_TO_BW["\uFEFB"] = "lA"   # لا  lam + alef ligature
_ARABIC_TO_BW["\uFEF9"] = "l<"   # لإ  lam + alef hamza below
_ARABIC_TO_BW["\uFEF7"] = "l>"   # لأ  lam + alef hamza above
_ARABIC_TO_BW["\uFEF8"] = "l|"   # لآ  lam + alef madda


def buckwalter_to_arabic(bw: str, errors: str = "pass") -> str:
    """Convert a Buckwalter-encoded string to Arabic Unicode.

    Unknown characters are passed through unchanged.

    Examples
    --------
    >>> buckwalter_to_arabic("mrHbA")
    'مرحبا'
    """
    return "".join(_BW_TO_ARABIC[ch] if ch in _BW_TO_ARABIC
                   else _unknown(ch, i, "buckwalter", errors)
                   for i, ch in enumerate(bw))


def arabic_to_buckwalter(arabic: str, errors: str = "pass") -> str:
    """Convert an Arabic Unicode string to Buckwalter transliteration.

    Unknown characters are passed through unchanged.

    Examples
    --------
    >>> arabic_to_buckwalter("مرحبا")
    'mrHbA'
    """
    return "".join(_ARABIC_TO_BW[ch] if ch in _ARABIC_TO_BW
                   else _unknown(ch, i, "arabic", errors)
                   for i, ch in enumerate(arabic))


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

# Precompiled regex
_IPA_LX_RE = re.compile("|".join(re.escape(s) for s in _IPA_FOR_LX_SORTED))


def lexique_to_ipa(lexique: str, errors: str = "pass") -> str:
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
    for i, ch in enumerate(lexique):
        mapped = _LEXIQUE_TO_IPA.get(ch)
        result.append(mapped if mapped is not None
                      else _unknown(ch, i, "lexique", errors))
    return "".join(result)


def ipa_to_lexique(ipa: str, errors: str = "pass") -> str:
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
    result = []
    pos = 0
    while pos < len(ipa):
        m = _IPA_LX_RE.match(ipa, pos)
        if m:
            result.append(_IPA_TO_LEXIQUE[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(ipa[pos], pos, "lexique", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Kirshenbaum (ASCII-IPA) ↔ IPA
#
# Kirshenbaum is the ASCII phonetic alphabet defined by Kirshenbaum 1993
# (comp.speech), also used natively by espeak-ng. The single-character map
# below is the factual ASCII → IPA codepoint correspondence of that standard
# (index i → the IPA codepoint for ASCII 0x20+i), cross-checked against the
# espeak-ng ``ipa1[96]`` table.
# ---------------------------------------------------------------------------

# ipa1[96]: IPA codepoint for each printable ASCII char, 0x20..0x7F.
_KIRSHENBAUM_IPA1 = (
    0x20, 0x21, 0x22, 0x2b0, 0x24, 0x25, 0x0e6, 0x2c8, 0x28, 0x29, 0x27e, 0x2b, 0x2cc, 0x2d, 0x2e, 0x2f,
    0x252, 0x31, 0x32, 0x25c, 0x34, 0x35, 0x36, 0x37, 0x275, 0x39, 0x2d0, 0x2b2, 0x3c, 0x3d, 0x3e, 0x294,
    0x259, 0x251, 0x3b2, 0xe7, 0xf0, 0x25b, 0x46, 0x262, 0x127, 0x26a, 0x25f, 0x4b, 0x26b, 0x271, 0x14b, 0x254,
    0x3a6, 0x263, 0x280, 0x283, 0x3b8, 0x28a, 0x28c, 0x153, 0x3c7, 0xf8, 0x292, 0x32a, 0x5c, 0x5d, 0x5e, 0x5f,
    0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x261, 0x68, 0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
    0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x303, 0x7f,
)
# Kirshenbaum symbols that map to an IPA character different from the ASCII
# input carry real phonetic meaning; identity rows (letter → itself) are kept
# so plain ASCII survives a round-trip.
_KIRSHENBAUM_TO_IPA: dict[str, str] = {
    chr(0x20 + _i): chr(_cp) for _i, _cp in enumerate(_KIRSHENBAUM_IPA1)
}
_IPA_TO_KIRSHENBAUM: dict[str, str] = {}
for _k, _ip in _KIRSHENBAUM_TO_IPA.items():
    _IPA_TO_KIRSHENBAUM.setdefault(_ip, _k)


def kirshenbaum_to_ipa(kirshenbaum: str, errors: str = "pass") -> str:
    """Convert a Kirshenbaum (ASCII-IPA) string to IPA.

    Each character is mapped independently. Characters outside the table
    pass through unchanged.

    Examples
    --------
    >>> kirshenbaum_to_ipa("S")
    'ʃ'
    >>> kirshenbaum_to_ipa("N")
    'ŋ'
    """
    return "".join(_KIRSHENBAUM_TO_IPA[ch] if ch in _KIRSHENBAUM_TO_IPA
                   else _unknown(ch, i, "kirshenbaum", errors)
                   for i, ch in enumerate(kirshenbaum))


def ipa_to_kirshenbaum(ipa: str, errors: str = "pass") -> str:
    """Convert an IPA string to Kirshenbaum (ASCII-IPA).

    Characters outside the table pass through unchanged.

    Examples
    --------
    >>> ipa_to_kirshenbaum("ʃ")
    'S'
    >>> ipa_to_kirshenbaum("ŋ")
    'N'
    """
    return "".join(_IPA_TO_KIRSHENBAUM[ch] if ch in _IPA_TO_KIRSHENBAUM
                   else _unknown(ch, i, "kirshenbaum", errors)
                   for i, ch in enumerate(ipa))


# ---------------------------------------------------------------------------
# Cotovía ↔ IPA
#
# Cotovía is the internal phoneme notation of the Universidade de Vigo GTM
# Cotovía TTS system (Galician/Spanish). The table is the phoneme symbol map
# from its ``fonemas.cpp``. Symbols are matched longest-first (``tS``, ``rr``
# before single characters). The silence/pause marker (``#``) is a boundary
# token, not a phoneme, and is intentionally excluded.
# ---------------------------------------------------------------------------

_COTOVIA_TO_IPA: dict[str, str] = {
    # Double-character symbols first (longest-match ordering)
    "tS": "tʃ",
    "rr": "r",    # trill (single "r" is the tap ɾ)
    "jj": "ʎ",
    # Consonants
    "B": "β",
    "D": "ð",
    "G": "ɣ",
    "J": "ɲ",
    "N": "ŋ",
    "S": "ʃ",
    "T": "θ",
    "Z": "ʎ",
    "L": "ʎ",     # canonical Cotovía symbol for the palatal lateral
    "b": "b",
    "d": "d",
    "f": "f",
    "g": "ɡ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "r": "ɾ",     # tap
    "s": "s",
    "t": "t",
    "x": "x",
    "X": "x",
    # Vowels
    "E": "ɛ",
    "O": "ɔ",
    "a": "a",
    "e": "e",
    "i": "i",
    "o": "o",
    "u": "u",
    # Glides
    "j": "j",
    "w": "w",
}

# Reverse: IPA → Cotovía. First-wins deduplicates the symbols that share an IPA
# value; pin ʎ → "L" (the standard Cotovía palatal-lateral symbol) and x → "x".
_IPA_TO_COTOVIA: dict[str, str] = {}
for _cv, _ip in _COTOVIA_TO_IPA.items():
    _IPA_TO_COTOVIA.setdefault(_ip, _cv)
_IPA_TO_COTOVIA["ʎ"] = "L"
_IPA_TO_COTOVIA["x"] = "x"

_CV_KEYS_SORTED = sorted(_COTOVIA_TO_IPA.keys(), key=len, reverse=True)
_CV_RE = re.compile("|".join(re.escape(s) for s in _CV_KEYS_SORTED))
_IPA_CV_KEYS_SORTED = sorted(_IPA_TO_COTOVIA.keys(), key=len, reverse=True)
_IPA_CV_RE = re.compile("|".join(re.escape(s) for s in _IPA_CV_KEYS_SORTED))


def cotovia_to_ipa(cotovia: str, errors: str = "pass") -> str:
    """Convert a Cotovía phoneme string to IPA.

    Multi-character symbols are matched longest-first. Characters outside the
    table pass through unchanged.

    Examples
    --------
    >>> cotovia_to_ipa("tS")
    'tʃ'
    >>> cotovia_to_ipa("karro")
    'karo'
    """
    result = []
    pos = 0
    while pos < len(cotovia):
        m = _CV_RE.match(cotovia, pos)
        if m:
            result.append(_COTOVIA_TO_IPA[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(cotovia[pos], pos, "cotovia", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


def ipa_to_cotovia(ipa: str, errors: str = "pass") -> str:
    """Convert an IPA string to Cotovía notation.

    Multi-character IPA symbols are matched longest-first. Characters outside
    the table pass through unchanged.

    Examples
    --------
    >>> ipa_to_cotovia("tʃ")
    'tS'
    >>> ipa_to_cotovia("ʎ")
    'L'
    """
    result = []
    pos = 0
    while pos < len(ipa):
        m = _IPA_CV_RE.match(ipa, pos)
        if m:
            result.append(_IPA_TO_COTOVIA[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(ipa[pos], pos, "cotovia", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# RFE (Revista de Filología Española) ↔ IPA
#
# The RFE phonetic alphabet (Navarro Tomás, Revista de Filología Española,
# 1915) is the traditional transcription system of Spanish and Romance
# philology. This is its core, well-attested inventory; rare interdental and
# variant diacritic symbols from the full standard are omitted. Symbols are
# matched longest-first (combining-mark symbols before their base letters).
# Reference: RFE Phonetic Alphabet
# (https://en.wikipedia.org/wiki/RFE_Phonetic_Alphabet).
# ---------------------------------------------------------------------------

_RFE_TO_IPA: dict[str, str] = {
    # Combining-mark symbols (longest-match first)
    "r̄": "r",    # r + macron = alveolar trill (plain r = tap ɾ)
    "n̮": "ɲ",   # n + breve below = palatal nasal ɲ
    "l̮": "ʎ",   # l + breve below = palatal lateral ʎ
    # Palatal / postalveolar
    "ĉ": "tʃ",   # ĉ = tʃ
    "š": "ʃ",    # š = ʃ
    "ž": "ʒ",    # ž = ʒ
    "ŷ": "ɟʝ",  # ŷ = ɟʝ (voiced palatal affricate)
    "ñ": "ɲ",    # ñ = ɲ
    "y": "ʝ",         # y = ʝ
    "j": "j",              # j = j
    # Spanish approximant/fricative allophones
    "ƀ": "β",    # ƀ = β
    "đ": "ð",    # đ = ð
    "ǥ": "ɣ",    # ǥ = ɣ
    # Other consonants
    "θ": "θ",    # θ = θ
    "x": "x",
    "ł": "ɫ",    # ł = ɫ (velarized l)
    "ŋ": "ŋ",    # ŋ = ŋ
    "w": "w",
    "h": "h",
    "b": "b",
    "p": "p",
    "t": "t",
    "d": "d",
    "k": "k",
    "g": "ɡ",         # g = ɡ (script g, matching the other tables)
    "f": "f",
    "v": "v",
    "s": "s",
    "z": "z",
    "m": "m",
    "n": "n",
    "l": "l",
    "r": "ɾ",         # r = tap ɾ
    # Vowels
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u",
    "ə": "ə",    # ə = ə
}

# Reverse: IPA → RFE. First-wins deduplicates; pin the canonical RFE spellings
# for the palatal nasal (ñ) and the trill/tap pair.
_IPA_TO_RFE: dict[str, str] = {}
for _rfe, _ip in _RFE_TO_IPA.items():
    _IPA_TO_RFE.setdefault(_ip, _rfe)
_IPA_TO_RFE["ɲ"] = "ñ"   # ɲ → ñ (canonical, not the n̮ variant)

_RFE_KEYS_SORTED = sorted(_RFE_TO_IPA.keys(), key=len, reverse=True)
_RFE_RE = re.compile("|".join(re.escape(x) for x in _RFE_KEYS_SORTED))
_IPA_RFE_KEYS_SORTED = sorted(_IPA_TO_RFE.keys(), key=len, reverse=True)
_IPA_RFE_RE = re.compile("|".join(re.escape(x) for x in _IPA_RFE_KEYS_SORTED))


def rfe_to_ipa(rfe: str, errors: str = "pass") -> str:
    """Convert an RFE (Revista de Filología Española) string to IPA.

    Multi-character symbols are matched longest-first. Characters outside the
    table pass through unchanged.

    Examples
    --------
    >>> rfe_to_ipa("š")
    'ʃ'
    >>> rfe_to_ipa("kaša")
    'kaʃa'
    """
    result = []
    pos = 0
    while pos < len(rfe):
        m = _RFE_RE.match(rfe, pos)
        if m:
            result.append(_RFE_TO_IPA[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(rfe[pos], pos, "rfe", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)


def ipa_to_rfe(ipa: str, errors: str = "pass") -> str:
    """Convert an IPA string to RFE (Revista de Filología Española) notation.

    Multi-character IPA symbols are matched longest-first. Characters outside
    the table pass through unchanged.

    Examples
    --------
    >>> ipa_to_rfe("ʃ")
    'š'
    >>> ipa_to_rfe("ɲ")
    'ñ'
    """
    result = []
    pos = 0
    while pos < len(ipa):
        m = _IPA_RFE_RE.match(ipa, pos)
        if m:
            result.append(_IPA_TO_RFE[m.group(0)])
            pos = m.end()
        else:
            out = _unknown(ipa[pos], pos, "rfe", errors)
            if out:
                result.append(out)
            pos += 1
    return "".join(result)



# ---------------------------------------------------------------------------
# Mantoq → IPA
#
# Mantoq is the phonetic alphabet of Nawar Halabi's Arabic-Phonetiser (the
# inventory emitted by the mantoq G2P pipeline): an ASCII phoneme notation
# with Buckwalter-derived consonant letters (deviating where the phoneme set
# requires — "^" is θ here, "v" a loan phoneme), stress/emphatic-free short
# and long vowels ("a"/"aa"/"aaaa"), a gemination marker ``_dbl_`` and a word
# separator ``_+_``.  The token→IPA mapping below is authored in-house from
# the inventory's phonetic values — the phonetiser CODE is CC BY-NC and lives
# elsewhere; a factual symbol table is not encumbered by it.  Published
# models trained on mantoq sequences make this notation worth transcoding.
# One-directional: IPA → mantoq is not defined.
# ---------------------------------------------------------------------------

_MANTOQ_CONSONANTS: dict[str, str] = {
    "b": "b", "t": "t", "^": "θ", "j": "d͡ʒ", "H": "ħ", "x": "x",
    "d": "d", "*": "ð", "r": "r", "z": "z", "s": "s", "$": "ʃ",
    "S": "sˤ", "D": "dˤ", "T": "tˤ", "Z": "ðˤ", "E": "ʕ", "g": "ɣ",
    "f": "f", "q": "q", "k": "k", "l": "l", "m": "m", "n": "n",
    "h": "h", "w": "w", "y": "j", "v": "v",
}

_MANTOQ_VOWELS: dict[str, str] = {
    "a": "a", "aa": "aː", "aaaa": "aːː",
    "i": "i", "ii": "iː",
    "u": "u", "uu": "uː",
}

_MANTOQ_MULTI = ("_dbl_", "_+_", "_sil_", "_eos_", "_pad_",
                 "aaaa", "aa", "ii", "uu")


def _tokenize_mantoq(text: str) -> list[str]:
    tokens = []
    i = 0
    while i < len(text):
        for sym in _MANTOQ_MULTI:
            if text.startswith(sym, i):
                tokens.append(sym)
                i += len(sym)
                break
        else:
            tokens.append(text[i])
            i += 1
    return tokens


def mantoq_to_ipa(mantoq: str | list[str], errors: str = "pass") -> str:
    """Convert a Mantoq phoneme string to IPA.

    ``_dbl_`` lengthens/geminates the preceding symbol (``ː``), ``_+_``
    becomes a space, ``<`` is the glottal stop.  Unknown characters follow
    the ``errors`` policy.

    Examples
    --------
    >>> mantoq_to_ipa("s a l aa m")
    's a l aː m'
    >>> mantoq_to_ipa("b_dbl_a")
    'bːa'

    The inventory's special tokens are honoured: ``_sil_`` becomes a space,
    ``_eos_``/``_pad_`` are dropped.
    """
    # a pre-tokenized sequence (as returned by the mantoq package's g2p)
    # is consumed directly — joining tokens into a string is ambiguous
    # ("a"+"aa" and "aa"+"a" both join to "aaa")
    tokens = _tokenize_mantoq(mantoq) if isinstance(mantoq, str) else mantoq
    out: list[str] = []
    last_tok = None
    for pos, tok in enumerate(tokens):
        if tok == "_dbl_":
            # upstream emits _dbl_ only by splitting a doubled CONSONANT
            # (mantoq buck/tokenization.py: `phon not in vowels and
            # phon[0] == phon[1]`); geminate it with a length mark.  A
            # vowel+_dbl_ sequence does not occur in genuine mantoq output
            # and is left unchanged.
            if out and last_tok in _MANTOQ_CONSONANTS \
                    and not out[-1].endswith("ː"):
                out[-1] += "ː"
            continue
        if tok == "_sil_":
            out.append(" ")
            last_tok = None
            continue
        if tok in ("_eos_", "_pad_"):
            last_tok = None
            continue
        if tok == "_+_":
            out.append(" ")
            last_tok = None
            continue
        if tok == "<":
            out.append("ʔ")
            last_tok = tok
            continue
        if tok in _MANTOQ_VOWELS:
            out.append(_MANTOQ_VOWELS[tok])
        elif tok in _MANTOQ_CONSONANTS:
            out.append(_MANTOQ_CONSONANTS[tok])
        elif tok.isspace() or tok in ".,;:!?()[]{}\"'":
            out.append(tok)
            last_tok = None
            continue
        else:
            res = _unknown(tok, pos, "mantoq", errors)
            if res:
                out.append(res)
            last_tok = None
            continue
        last_tok = tok
    return "".join(out)


# ---------------------------------------------------------------------------
# convert — facade routing through IPA where no direct map exists
# ---------------------------------------------------------------------------

def convert(text: str, src: str | Notation, dst: str | Notation,
            errors: str = "pass") -> str:
    """Convert *text* from *src* notation to *dst* notation.

    Supported pairs (direct):
      - ``arpa`` ↔ ``ipa``
      - ``x-sampa`` ↔ ``ipa``
      - ``lexique`` ↔ ``ipa``
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

    # Routing lives on the shared conversion graph; the notation tables below
    # are registered there as edges (IPA-pivot pairs route through the "ipa"
    # node, Buckwalter <-> Arabic is a direct edge).
    from scriptconv.graph import DEFAULT_GRAPH
    try:
        return DEFAULT_GRAPH.convert(text, src.value, dst.value, errors=errors)
    except UnknownSymbolError:
        raise
    except ValueError:
        raise ValueError(f"Unsupported conversion: {src!r} → {dst!r}") from None


# ---------------------------------------------------------------------------
# Converter registry — the single source of truth for supported paths.
#
# _TO_IPA / _FROM_IPA hold the IPA-pivot notations; anything registered in
# both can convert to anything else in the other (routed through IPA).
# _DIRECT_PAIRS holds non-IPA pairs (Buckwalter ↔ Arabic script).
# ---------------------------------------------------------------------------

_TO_IPA: dict[Notation, "callable"] = {
    Notation.MANTOQ: mantoq_to_ipa,
    Notation.ARPA: arpa_to_ipa,
    Notation.XSAMPA: xsampa_to_ipa,
    Notation.LEXIQUE: lexique_to_ipa,
    Notation.KIRSHENBAUM: kirshenbaum_to_ipa,
    Notation.COTOVIA: cotovia_to_ipa,
    Notation.RFE: rfe_to_ipa,
}
_FROM_IPA: dict[Notation, "callable"] = {
    Notation.ARPA: ipa_to_arpa,
    Notation.XSAMPA: ipa_to_xsampa,
    Notation.LEXIQUE: ipa_to_lexique,
    Notation.KIRSHENBAUM: ipa_to_kirshenbaum,
    Notation.COTOVIA: ipa_to_cotovia,
    Notation.RFE: ipa_to_rfe,
}
_DIRECT_PAIRS: dict[tuple[Notation, Notation], "callable"] = {
    (Notation.BUCKWALTER, Notation.ARABIC): buckwalter_to_arabic,
    (Notation.ARABIC, Notation.BUCKWALTER): arabic_to_buckwalter,
}


# ---------------------------------------------------------------------------
# can_convert — predicate for supported conversion paths
# ---------------------------------------------------------------------------

_NOTATION_VALUES = {n.value for n in Notation}


def can_convert(src: str | Notation, dst: str | Notation) -> bool:
    """Return ``True`` if a conversion from *src* to *dst* is supported.

    Parameters
    ----------
    src:
        Source notation.
    dst:
        Target notation.

    Examples
    --------
    >>> can_convert("arpa", "ipa")
    True
    >>> can_convert("arpa", "x-sampa")
    True
    >>> can_convert("buckwalter", "ipa")
    False
    """
    src = Notation(src)
    dst = Notation(dst)
    if src == dst:
        # historical contract: identity is not a "conversion" here, unlike
        # graph.ConversionGraph.can_convert (which deliberately returns True
        # for identity — an empty route is a valid, zero-cost conversion there)
        return False
    from scriptconv.graph import DEFAULT_GRAPH
    try:
        route = DEFAULT_GRAPH.route(src.value, dst.value)
    except ValueError:
        return False
    # only notation-to-notation reachability counts here; guard against paths
    # that would leave the notation node set (none exist today, cheap to keep)
    return all(e.src in _NOTATION_VALUES and e.dst in _NOTATION_VALUES
               for e in route)


# ---------------------------------------------------------------------------
# NotationInfo — queryable fidelity metadata (fidelity is data, not prose)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NotationInfo:
    """Fidelity metadata for a phoneme notation, relative to the IPA hub.

    Attributes
    ----------
    notation:
        The :class:`Notation` this describes.
    lossless_to_ipa:
        ``True`` if ``<notation> → IPA → <notation>`` reproduces every input
        symbol exactly (round-trip safe from the notation's side).
    lossless_from_ipa:
        ``True`` if ``IPA → <notation> → IPA`` reproduces every IPA symbol —
        i.e. the notation's inventory covers IPA. ``False`` for
        restricted-inventory notations such as ARPABET.
    token_separated:
        ``True`` when symbols are whitespace-separated tokens (ARPABET) rather
        than a contiguous string (IPA, X-SAMPA, Kirshenbaum, Lexique).
    reference:
        Citation for the mapping table.
    """

    notation: Notation
    lossless_to_ipa: bool
    lossless_from_ipa: bool
    token_separated: bool
    reference: str


NOTATION_INFO: dict[Notation, NotationInfo] = {
    Notation.ARPA: NotationInfo(
        Notation.ARPA, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=True,
        reference="https://github.com/chorusai/arpa2ipa",
    ),
    Notation.XSAMPA: NotationInfo(
        Notation.XSAMPA, lossless_to_ipa=False, lossless_from_ipa=True,
        token_separated=False,
        reference="https://en.wikipedia.org/wiki/X-SAMPA",
    ),
    Notation.LEXIQUE: NotationInfo(
        Notation.LEXIQUE, lossless_to_ipa=False, lossless_from_ipa=True,
        token_separated=False,
        reference="New & Pallier, Manuel de Lexique 3 v3.11, Tableau 2 (CC BY-SA 4.0)",
    ),
    Notation.KIRSHENBAUM: NotationInfo(
        Notation.KIRSHENBAUM, lossless_to_ipa=True, lossless_from_ipa=False,
        token_separated=False,
        reference="Kirshenbaum 1993 ASCII-IPA standard (comp.speech)",
    ),
    Notation.COTOVIA: NotationInfo(
        Notation.COTOVIA, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=False,
        reference="Universidade de Vigo GTM Cotovía TTS (fonemas.cpp)",
    ),
    Notation.RFE: NotationInfo(
        Notation.RFE, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=False,
        reference="RFE phonetic alphabet (Revista de Filología Española, 1915)",
    ),
    Notation.MANTOQ: NotationInfo(
        Notation.MANTOQ, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=False,
        reference="Phonetic alphabet of Nawar Halabi's Arabic-Phonetiser "
                  "(mantoq G2P inventory); one-directional to IPA",
    ),
    Notation.BUCKWALTER: NotationInfo(
        Notation.BUCKWALTER, lossless_to_ipa=True, lossless_from_ipa=False,
        token_separated=False,
        reference="Tim Buckwalter Arabic transliteration scheme",
    ),
}


# ---------------------------------------------------------------------------
# convert_batch — line-by-line generator
# ---------------------------------------------------------------------------


def convert_batch(
    lines: Iterable[str],
    src: str | Notation,
    dst: str | Notation,
) -> Generator[str, None, None]:
    """Convert each line from *src* to *dst* notation, yielding results.

    Blank lines are yielded unchanged (no conversion attempted).

    Parameters
    ----------
    lines:
        Iterable of input strings (e.g. file lines).
    src:
        Source notation.
    dst:
        Target notation.

    Yields
    ------
    str
        Converted string for each input line.

    Examples
    --------
    >>> list(convert_batch(["HH AH0 L OW1", "", "AY1"], "arpa", "ipa"))
    ['həloʊ', '', 'aɪ']
    """
    _src = Notation(src)
    _dst = Notation(dst)
    for line in lines:
        stripped = line.rstrip("\n\r")
        if not stripped:
            yield stripped
        else:
            yield convert(stripped, _src, _dst)


# ---------------------------------------------------------------------------
# looks_like_ipa — heuristic notation detection
# ---------------------------------------------------------------------------

# Unicode blocks/characters that are distinctive to IPA transcription.  Basic
# Latin letters (p, a, t, …) and the Greek letters IPA borrows (β, θ, χ) are
# deliberately excluded: they are indistinguishable from ordinary Latin/Greek
# text, so they carry no signal.
_IPA_DISTINCTIVE_RANGES = (
    (0x0250, 0x02AF),  # IPA Extensions
    (0x02B0, 0x02FF),  # Spacing Modifier Letters (ˈ ˌ ː ˑ ʰ ʲ …)
    (0x0363, 0x036F),  # Combining diacritics used in IPA
    (0x1D00, 0x1D7F),  # Phonetic Extensions
    (0x1D80, 0x1DBF),  # Phonetic Extensions Supplement
)
# Individual combining marks common in IPA (nasalisation, syllabicity, etc.).
_IPA_DISTINCTIVE_CHARS = frozenset("̩̪̥̃̊͜͡")


def _is_ipa_distinctive(ch: str) -> bool:
    cp = ord(ch)
    if ch in _IPA_DISTINCTIVE_CHARS:
        return True
    return any(lo <= cp <= hi for lo, hi in _IPA_DISTINCTIVE_RANGES)


def looks_like_ipa(text: str) -> bool:
    """Heuristically decide whether *text* is an IPA transcription.

    Returns ``True`` when *text* contains at least one character that is
    distinctive to IPA — from the IPA Extensions, Spacing Modifier Letters,
    or Phonetic Extensions blocks, or an IPA combining diacritic (e.g.
    ``ɑ``, ``ʃ``, ``ː``, ``ˈ``, nasalisation).

    This is a positive-signal heuristic, not a classifier: a transcription
    written only with characters IPA shares with the Latin alphabet
    (``"pat"``, ``"bad"``) has no distinctive marker and returns ``False``.
    It cannot be otherwise — those characters are the same codepoints as
    ordinary text. Use it to *guard* against feeding IPA where orthography
    is expected, not to prove a string is not IPA.

    Examples
    --------
    >>> looks_like_ipa("pʰɑtʃ")
    True
    >>> looks_like_ipa("ˈhɛloʊ")
    True
    >>> looks_like_ipa("hello")
    False
    """
    return any(_is_ipa_distinctive(ch) for ch in text)
