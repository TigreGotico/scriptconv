"""Phoneme-notation transcoding — IPA ↔ ARPABET, IPA ↔ X-SAMPA,
IPA ↔ Lexique, IPA ↔ Kirshenbaum, Buckwalter ↔ Arabic script.

All tables are pure Python data; zero runtime dependencies.

ARPABET table derived from chorusai/arpa2ipa
  (https://github.com/chorusai/arpa2ipa), licensed Apache-2.0, with values
  checked against the CMU Pronouncing Dictionary phone set and the ARPABET
  table that dictionary refers to for IPA.
X-SAMPA table from J.C. Wells, "Computer-coding the IPA: a proposed extension
  of SAMPA" (https://www.phon.ucl.ac.uk/home/sampa/x-sampa.htm).
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
    "halabi_to_ipa",
    "iqra_halabi_to_ipa",
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
    HALABI = "halabi"  # Halabi Arabic-Phonetiser phoneme notation (ar)

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
#
# The CMU Pronouncing Dictionary defines each phone by a keyword and points to
# the ARPABET table on Wikipedia for IPA values, so both are the reference:
#   http://www.speech.cs.cmu.edu/cgi-bin/cmudict
#   https://en.wikipedia.org/wiki/ARPABET
# tests/test_notation_sources.py quotes them row by row.
# ---------------------------------------------------------------------------

# Base ARPA→IPA (without stress digit variants; those are added below)
_ARPA_BASE: dict[str, str] = {
    # Monophthongs
    "AO": "ɔ",
    "AA": "ɑ",
    "IY": "i",
    "UW": "u",
    "EH": "ɛ",
    "IH": "ɪ",
    "UH": "ʊ",
    "AH": "ʌ",   # AH0 → ə handled separately
    "AE": "æ",
    "AX": "ə",
    "IX": "ɨ",
    "UX": "ʉ",
    # Diphthongs
    "EY": "eɪ",
    "AY": "aɪ",
    "OW": "oʊ",
    "AW": "aʊ",
    "OY": "ɔɪ",
    # R-colored vowels
    "ER": "ɝ",   # ER0 → ɚ handled separately
    "AXR": "ɚ",
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
    "H": "h",
    # Nasals
    "M": "m",
    "EM": "m̩",
    "N": "n",
    "EN": "n̩",
    "NG": "ŋ",
    "ENG": "ŋ̍",
    # Liquids
    "L": "l",
    "EL": "l̩",
    "R": "ɹ",
    "DX": "ɾ",
    "NX": "ɾ̃",
    # Semivowels
    "W": "w",
    "WH": "ʍ",
    "Y": "j",
    "Q": "ʔ",
}

# CMUdict has no AX or AXR: it spells those two phones as unstressed AH and ER
# (COMMA is AH0, "letter" ends in ER0).
_CMUDICT_UNSTRESSED = {"AH0": "ə", "ER0": "ɚ"}
_CMUDICT_SPELLING = {"AX": "AH", "AXR": "ER"}

# Build full lookup with stress variants
_ARPA_TO_IPA: dict[str, str] = {}
for _arpa, _ipa in _ARPA_BASE.items():
    _ARPA_TO_IPA[_arpa] = _ipa
    for _stress in ("0", "1", "2"):
        _key = _arpa + _stress
        _ARPA_TO_IPA[_key] = _CMUDICT_UNSTRESSED.get(_key, _ipa)

# Reverse: IPA → ARPA (base form, no stress digit).
# Multi-char IPA values are deduplicated; keep first.
_IPA_TO_ARPA: dict[str, str] = {}
for _arpa, _ipa in _ARPA_BASE.items():
    if _ipa not in _IPA_TO_ARPA:
        _IPA_TO_ARPA[_ipa] = _arpa
# Accept ASCII "g" (U+0067) as well as canonical script "ɡ" (U+0261) on input.
_IPA_TO_ARPA.setdefault("g", "G")
# Broader spellings of ARPABET phones, accepted on input only.
_IPA_TO_ARPA.setdefault("e", "EH")
_IPA_TO_ARPA.setdefault("r", "R")
_IPA_TO_ARPA.setdefault("ɜr", "ER")
_IPA_TO_ARPA.setdefault("ər", "AXR")
_IPA_TO_ARPA.setdefault("ɫ̩", "EL")
# The tie bar joins the two symbols of an affricate, above or below the letters.
for _tie in ("\u0361", "\u035C"):
    _IPA_TO_ARPA.setdefault("t" + _tie + "ʃ", "CH")
    _IPA_TO_ARPA.setdefault("d" + _tie + "ʒ", "JH")
# Bare/long NURSE vowel (non-rhotic British ɜ, ɜː) has no dedicated ARPA symbol —
# ARPABET is rhotic-only, so it collapses onto the same "ER" as the r-colored ɝ.
_IPA_TO_ARPA.setdefault("ɜː", "ER")
_IPA_TO_ARPA.setdefault("ɜ", "ER")
# British (SSB) GOAT diphthong: ARPABET is GA-based so OW round-trips as oʊ,
# but əʊ is the same phoneme in RP/SSB transcriptions.
_IPA_TO_ARPA.setdefault("əʊ", "OW")
# British LOT vowel: GA merges it into ɑ (AA); ɒ has no ARPA symbol of its own.
_IPA_TO_ARPA.setdefault("ɒ", "AA")

# Precompiled regex for IPA → ARPA (longest-first)
_IPA_ARPA_KEYS_SORTED = sorted(_IPA_TO_ARPA.keys(), key=len, reverse=True)
_IPA_ARPA_RE = re.compile("|".join(re.escape(s) for s in _IPA_ARPA_KEYS_SORTED))

# ARPABET vowel class — the symbols that carry stress digits.
_ARPA_VOWELS = {"AO", "AA", "IY", "UW", "EH", "IH", "UH", "AH", "AE", "AX",
                "IX", "UX", "EY", "AY", "OW", "AW", "OY", "ER", "AXR"}
# Syllabic consonants: the nucleus of a syllable that has no ARPABET vowel.
_ARPA_SYLLABIC = {"EM", "EN", "ENG", "EL"}
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

# The characters with the Unicode White_Space property (PropList.txt).  A space
# separates words in every notation, so each converter keeps it under every
# policy.  str.isspace() is wider: it also holds U+001C to U+001F.
_WHITE_SPACE = frozenset(
    "\t\n\v\f\r \x85\xa0\u1680" + "".join(map(chr, range(0x2000, 0x200B)))
    + "\u2028\u2029\u202f\u205f\u3000")
_WHITE_SPACE_RE = re.compile("[" + "".join(sorted(_WHITE_SPACE)) + "]+")


def _unknown(symbol: str, position: int, notation: str, errors: str,
             replacement: str = "?") -> str:
    """Resolve one unmapped symbol according to the codecs-style policy."""
    if symbol in _WHITE_SPACE:
        return symbol
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
    tokens = [tok for tok in _WHITE_SPACE_RE.split(arpa_sequence) if tok]
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
    A stress mark stands before the stressed syllable, so with
    ``stress=True`` its digit goes to the next vowel, after any onset.
    ``errors`` selects the unknown-symbol policy (default ``"replace"``,
    preserving the historical behavior of substituting *unknown*, ``"?"``);
    ``unknown=""`` still drops silently.  Under the other policies, combining
    marks and modifier letters qualify the preceding phoneme and are dropped
    rather than treated as unknowns.  ``"strict"`` drops no mark: it raises
    on a mark with no ARPABET value, on a stress mark that no vowel
    follows, and on a stress mark whose syllable has a syllabic consonant
    (``EL``, ``EM``, ``EN``, ``ENG``) and no vowel.  With ``stress=False`` a stress mark is dropped under every
    policy, because the caller asked for no stress digits.  Spaces, the
    characters with the Unicode White_Space property, are dropped too: ARPABET
    tokens are space-separated, so the output keeps no word boundary.

    Examples
    --------
    >>> ipa_to_arpa("həloʊ")
    'HH AX L OW'
    >>> ipa_to_arpa("ɸ")
    '?'
    >>> ipa_to_arpa("ɛ ɛ")
    'EH EH'
    """
    tokens = []
    pending_stress = ""
    stress_pos = 0
    pos = 0
    while pos < len(ipa_string):
        if ipa_string[pos] in _STRESS_MARKS:
            if stress:
                pending_stress = _STRESS_MARKS[ipa_string[pos]]
                stress_pos = pos
            pos += 1
            continue
        m = _IPA_ARPA_RE.match(ipa_string, pos)
        if m:
            tok = _IPA_TO_ARPA[m.group(0)]
            # ARPABET has no stress digit for a syllabic consonant, and the
            # next vowel is in another syllable.
            if pending_stress and errors == "strict" and tok in _ARPA_SYLLABIC:
                raise UnknownSymbolError(ipa_string[stress_pos], stress_pos, "arpa")
            if stress and tok in _ARPA_VOWELS:
                # Stress-aware output follows CMUdict spelling for exact
                # round-trips; extended-ARPABET AX and AXR input normalizes
                # to AH0 and ER0 (documented residue).
                tok = _CMUDICT_SPELLING.get(tok, tok) + (pending_stress or "0")
                pending_stress = ""
            tokens.append(tok)
            pos = m.end()
        else:
            ch = ipa_string[pos]
            if ch in _WHITE_SPACE:
                # A stress mark does not cross into the next word.
                if pending_stress and errors == "strict":
                    raise UnknownSymbolError(ipa_string[stress_pos], stress_pos, "arpa")
                pending_stress = ""
            elif errors != "strict" and unicodedata.category(ch) in ("Mn", "Mc", "Me", "Lm", "Sk"):
                # A diacritic or suprasegmental qualifies the phoneme before
                # it and has no ARPABET token of its own.
                pass
            else:
                effective = "ignore" if (errors == "replace" and not unknown) else errors
                out = _unknown(ch, pos, "arpa", effective, replacement=unknown)
                if out:
                    tokens.append(out)
            pos += 1
    if pending_stress and errors == "strict":
        raise UnknownSymbolError(ipa_string[stress_pos], stress_pos, "arpa")
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# X-SAMPA ↔ IPA
#
# Reference: J.C. Wells, "Computer-coding the IPA: a proposed extension of
# SAMPA", https://www.phon.ucl.ac.uk/home/sampa/x-sampa.htm and its full
# article ipasam-x.pdf.  The Wikipedia table supplies the code points for the
# tone letters.  tests/test_notation_sources.py quotes them row by row.
#
# Multi-character symbols are matched longest-first in both directions.  Where
# Wells allows two spellings, the first key below is his main spelling and the
# reverse table emits it.
# ---------------------------------------------------------------------------

_XSAMPA_TO_IPA: dict[str, str] = {
    # Letters that keep their IPA value
    "a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "f": "f", "g": "ɡ",
    "h": "h", "i": "i", "j": "j", "k": "k", "l": "l", "m": "m", "n": "n",
    "o": "o", "p": "p", "q": "q", "r": "r", "s": "s", "t": "t", "u": "u",
    "v": "v", "w": "w", "x": "x", "y": "y", "z": "z",
    # Pulmonic consonants
    "t`": "ʈ",
    "d`": "ɖ",
    "G\\": "ɢ",
    "?": "ʔ",
    "F": "ɱ",
    "n`": "ɳ",
    "J": "ɲ",
    "N": "ŋ",
    "N\\": "ɴ",
    "B\\": "ʙ",
    "R\\": "ʀ",
    "4": "ɾ",
    "r`": "ɽ",
    "p\\": "ɸ",
    "B": "β",
    "T": "θ",
    "D": "ð",
    "S": "ʃ",
    "Z": "ʒ",
    "s`": "ʂ",
    "z`": "ʐ",
    "C": "ç",
    "j\\": "ʝ",
    "G": "ɣ",
    "X": "χ",
    "R": "ʁ",
    "X\\": "ħ",
    "?\\": "ʕ",
    "h\\": "ɦ",
    "K": "ɬ",
    "K\\": "ɮ",
    "P": "ʋ",
    "v\\": "ʋ",
    "r\\": "ɹ",
    "r\\`": "ɻ",
    "J\\": "ɟ",
    "M\\": "ɰ",
    "l`": "ɭ",
    "L": "ʎ",
    "L\\": "ʟ",
    # Clicks
    "O\\": "ʘ",
    "|\\": "ǀ",
    "!\\": "ǃ",
    "=\\": "ǂ",
    "|\\|\\": "ǁ",
    # Implosives
    "b_<": "ɓ",
    "d_<": "ɗ",
    "J\\_<": "ʄ",
    "g_<": "ɠ",
    "G\\_<": "ʛ",
    # Vowels
    "M": "ɯ",
    "1": "ɨ",
    "}": "ʉ",
    "I": "ɪ",
    "Y": "ʏ",
    "U": "ʊ",
    "I\\": "ᵻ",
    "U\\": "ᵿ",
    "2": "ø",
    "@\\": "ɘ",
    "8": "ɵ",
    "7": "ɤ",
    "@": "ə",
    "@`": "ɚ",
    "E": "ɛ",
    "9": "œ",
    "3": "ɜ",
    "3`": "ɝ",
    "3\\": "ɞ",
    "V": "ʌ",
    "O": "ɔ",
    "{": "æ",
    "6": "ɐ",
    "&": "ɶ",
    "A": "ɑ",
    "Q": "ɒ",
    # Other symbols
    "W": "ʍ",
    "H": "ɥ",
    "H\\": "ʜ",
    "<\\": "ʢ",
    ">\\": "ʡ",
    "s\\": "ɕ",
    "z\\": "ʑ",
    "l\\": "ɺ",
    "x\\": "ɧ",
    "5": "ɫ",
    "_": "\u0361",      # tie bar
    # Suprasegmentals
    '"': "ˈ",
    "%": "ˌ",
    ":": "ː",
    ":\\": "ˑ",
    "_X": "\u0306",     # extra-short
    ".": ".",           # syllable break
    "-\\": "‿",    # linking mark
    "|": "|",           # minor group
    "||": "‖",          # major group
    # Tones and word accents
    "_T": "\u030B",
    "_H": "\u0301",
    "_M": "\u0304",
    "_L": "\u0300",
    "_B": "\u030F",
    "_R": "\u030C",
    "_/": "\u030C",
    "_F": "\u0302",
    "_\\": "\u0302",
    "_H_T": "\u1DC4",
    "_B_L": "\u1DC5",
    "_R_F": "\u1DC8",
    "_L_H": "\u030C",
    "_H_L": "\u0302",
    "_M_H_L": "\u1DC8",
    "_/_\\": "\u1DC8",
    "<T>": "˥",
    "<H>": "˦",
    "<M>": "˧",
    "<L>": "˨",
    "<B>": "˩",
    "<BT>": "˩˥",
    "<TB>": "˥˩",
    "<HT>": "˧˥",
    "<BL>": "˩˧",
    "<HTH>": "˧˥˧",
    "!": "ꜜ",
    "<!>": "ꜜ",
    "^": "ꜛ",
    "<^>": "ꜛ",
    "<R>": "↗",
    "</>": "↗",
    "<F>": "↘",
    "<\\>": "↘",
    # Diacritics
    "_0": "\u0325",     # voiceless
    "_v": "\u032C",     # voiced
    "_h": "ʰ",
    "_O": "\u0339",     # more rounded
    "_c": "\u031C",     # less rounded
    "_+": "\u031F",     # advanced
    "_-": "\u0320",     # retracted
    '_"': "\u0308",     # centralized
    "_x": "\u033D",     # mid-centralized
    "=": "\u0329",      # syllabic
    "_=": "\u0329",
    "_^": "\u032F",     # non-syllabic
    "`": "˞",      # rhoticity
    "_t": "\u0324",     # breathy voiced
    "_k": "\u0330",     # creaky voiced
    "_N": "\u033C",     # linguolabial
    "_w": "ʷ",
    "'": "ʲ",
    "_j": "ʲ",
    "_G": "ˠ",
    "_?\\": "ˤ",
    "_d": "\u032A",     # dental
    "_a": "\u033A",     # apical
    "_m": "\u033B",     # laminal
    "~": "\u0303",      # nasalized
    "_~": "\u0303",
    "_n": "ⁿ",
    "_l": "ˡ",
    "_}": "\u031A",     # no audible release
    "_e": "\u0334",     # velarized or pharyngealized
    "_r": "\u031D",     # raised
    "_o": "\u031E",     # lowered
    "_A": "\u0318",     # advanced tongue root
    "_q": "\u0319",     # retracted tongue root
    "_>": "ʼ",          # ejective
    "_?": "ʼ",
}

# Reverse: IPA → X-SAMPA (first occurrence wins).  Keys are NFD, because
# ipa_to_xsampa() decomposes its input so that ã reaches the table as a + ◌\u0303.
_IPA_TO_XSAMPA: dict[str, str] = {}
for _xs, _ip in _XSAMPA_TO_IPA.items():
    _IPA_TO_XSAMPA.setdefault(unicodedata.normalize("NFD", _ip), _xs)
_IPA_TO_XSAMPA["\u035C"] = "_"  # the tie bar may be written below as well
# A mark below may move above a letter "to avoid a descender or another
# diacritic" (Wikipedia, International Phonetic Alphabet).  The syllabic mark
# above always reads as syllabic.  The voiceless ring above reads as voiceless
# after a letter in _DESCENDERS or after a mark below, and stays unknown
# elsewhere: å is a letter of Nordic orthography, not IPA.  _DESCENDERS holds
# the letters of this table whose glyph reaches more than 0.1 em below the
# baseline in both DejaVu Sans and DejaVu Serif.
_IPA_TO_XSAMPA["\u030D"] = "="
_DESCENDERS = frozenset("jpqyŋɖɟɠɡɣɥɧɭɮɰɱɲɳɸɻɽʂʃʄʈʐʒʝβχ")
_BELOW = (202, 220)  # canonical combining classes: attached below, below

# Longest-first sorted keys for pattern matching
_XS_KEYS_SORTED = sorted(_XSAMPA_TO_IPA.keys(), key=len, reverse=True)
_IPA_KEYS_SORTED = sorted(_IPA_TO_XSAMPA.keys(), key=len, reverse=True)

# Precompiled regexes
# Wells: "we must let \ take priority", so _j\ is the tie bar and j\, not _j
# and a stray backslash.  The lookahead yields to the longer keys such as _?\.
# Wells's "language-specific tone number" (_1 to _6) matches as one symbol with
# no IPA value, so that it stays unknown and does not read as the tie bar and a
# digit.  _7 to _9 are the tie bar and a vowel.  Wells's section 24 also writes
# a falling tone as _`, and calls that set "an embarras de richesses".  It too
# has no IPA value, and a tie before the rhoticity mark would mean nothing.
_XS_RE = re.compile("|".join(
    [re.escape(k) for k in _XS_KEYS_SORTED if len(k) > 2]
    + [r"_(?=[^\\]\\)", "_[1-6]", "_`"]
    + [re.escape(k) for k in _XS_KEYS_SORTED if len(k) <= 2]))
_IPA_XS_RE = re.compile("|".join(re.escape(k) for k in _IPA_KEYS_SORTED))


def xsampa_to_ipa(xsampa: str, errors: str = "pass") -> str:
    """Convert an X-SAMPA string to IPA.

    Multi-character symbols are matched longest-first.  Unknown characters
    are passed through.  A tone number such as ``_1`` has no IPA value, so it
    counts as one unknown symbol.

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
        symbol = m.group(0) if m else xsampa[pos]
        if symbol in _XSAMPA_TO_IPA:
            result.append(_XSAMPA_TO_IPA[symbol])
        else:
            out = _unknown(symbol, pos, "x-sampa", errors)
            if out:
                result.append(out)
        pos += len(symbol)
    return "".join(result)


def ipa_to_xsampa(ipa: str, errors: str = "pass") -> str:
    """Convert an IPA string to X-SAMPA.

    Multi-character IPA symbols are matched longest-first.  Unknown
    characters are passed through.  The input is decomposed first, so a
    precomposed ``ã`` gives the same result as ``a`` plus a combining tilde.

    A tie bar is the underscore, which also opens a diacritic.  Where the next
    symbol would read as one, the tie is dropped: Wells calls it "more
    satisfactory to assume affricate status" than to write it.

    Examples
    --------
    >>> ipa_to_xsampa("ʃ")
    'S'
    >>> ipa_to_xsampa("ə")
    '@'
    >>> ipa_to_xsampa("kʰã")
    'k_ha~'
    >>> ipa_to_xsampa("t\u0361s")
    't_s'
    >>> ipa_to_xsampa("t\u0361θ")
    'tT'
    """
    ipa = unicodedata.normalize("NFD", ipa)
    result = []
    pos = 0
    while pos < len(ipa):
        m = _IPA_XS_RE.match(ipa, pos)
        if m:
            symbol = _IPA_TO_XSAMPA[m.group(0)]
            if result and result[-1] == "_" and _XS_RE.match("_" + symbol).group(0) != "_":
                result.pop()
            result.append(symbol)
            pos = m.end()
        elif ipa[pos] == "\u030A" and pos and (
                ipa[pos - 1] in _DESCENDERS
                or unicodedata.combining(ipa[pos - 1]) in _BELOW):
            result.append("_0")
            pos += 1
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
# Arabic Presentation Forms-A and -B are compatibility characters: one letter,
# or a ligature such as lam-alef, in a contextual shape.  NFKC gives the
# letters, so a presentation form takes their spelling and returns as them.
for _cp in (*range(0xFB50, 0xFE00), *range(0xFE70, 0xFF00)):
    _letters = unicodedata.normalize("NFKC", chr(_cp))
    if _letters != chr(_cp) and all(c in _ARABIC_TO_BW for c in _letters):
        _ARABIC_TO_BW[chr(_cp)] = "".join(_ARABIC_TO_BW[c] for c in _letters)


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
# Halabi → IPA
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
# One-directional: IPA → halabi is not defined.
#
# Naming and lineage: this notation originates in Nawar Halabi's
# Arabic-Phonetiser (2016, CC BY-NC 4.0), written for his Arabic speech
# corpus. The mantoq package wraps that phonetiser (with a diacritizer);
# phoonnx and scriptconv vendor mantoq; the IqraEval shared task generates
# its reference phonemes with the same rules (Interspeech 2025,
# doi:10.21437/Interspeech.2025-2411 — "we employed the phonetizer
# introduced by Nawar Halabi"). One engine, several package names — the
# notation is named for its author, not for any wrapper.
# ---------------------------------------------------------------------------

_HALABI_CONSONANTS: dict[str, str] = {
    "b": "b", "t": "t", "^": "θ", "j": "d͡ʒ", "H": "ħ", "x": "x",
    "d": "d", "*": "ð", "r": "r", "z": "z", "s": "s", "$": "ʃ",
    "S": "sˤ", "D": "dˤ", "T": "tˤ", "Z": "ðˤ", "E": "ʕ", "g": "ɣ",
    "f": "f", "q": "q", "k": "k", "l": "l", "m": "m", "n": "n",
    "h": "h", "w": "w", "y": "j", "v": "v",
}

_HALABI_VOWELS: dict[str, str] = {
    "a": "a", "aa": "aː", "aaaa": "aːː",
    "i": "i", "ii": "iː",
    "u": "u", "uu": "uː",
    # emphatic-context allophones from the RAW (pre-mantoq-simplification)
    # Halabi phonetiser layer — mantoq's own g2p folds these to the plain
    # forms above via ``simplify_phonemes``, but scriptconv's raw
    # ``Phonemizer.HALABI``/``Phonemizer.IQRA`` edges call the phonetiser
    # directly and preserve the distinction (see arbtok's
    # scripts/benchmark_iqraeval.py, verified symbol-by-symbol against the
    # IqraEval/Iqra_train corpus).
    "A": "ɑ", "AA": "ɑː",
    "I": "ɪ", "II": "ɪː",
    "U": "ʊ", "UU": "ʊː",
}

_HALABI_MULTI = ("_dbl_", "_+_", "_sil_", "_eos_", "_pad_",
                 "aaaa", "aa", "ii", "uu", "AA", "II", "UU")


def _tokenize_halabi(text: str) -> list[str]:
    tokens = []
    i = 0
    while i < len(text):
        for sym in _HALABI_MULTI:
            if text.startswith(sym, i):
                tokens.append(sym)
                i += len(sym)
                break
        else:
            tokens.append(text[i])
            i += 1
    return tokens


def halabi_to_ipa(halabi: str | list[str], errors: str = "pass") -> str:
    """Convert a Halabi-notation phoneme string to IPA.

    ``_dbl_`` lengthens/geminates the preceding symbol (``ː``), ``_+_``
    becomes a space, ``<`` is the glottal stop.  Unknown characters follow
    the ``errors`` policy.

    Examples
    --------
    >>> halabi_to_ipa("s a l aa m")
    's a l aː m'
    >>> halabi_to_ipa("b_dbl_a")
    'bːa'

    The inventory's special tokens are honoured: ``_sil_`` becomes a space,
    ``_eos_``/``_pad_`` are dropped.
    """
    # a pre-tokenized sequence (as returned by the mantoq package's g2p)
    # is consumed directly — joining tokens into a string is ambiguous
    # ("a"+"aa" and "aa"+"a" both join to "aaa")
    tokens = _tokenize_halabi(halabi) if isinstance(halabi, str) else halabi
    out: list[str] = []
    last_tok = None
    for pos, tok in enumerate(tokens):
        if tok == "_dbl_":
            # upstream emits _dbl_ only by splitting a doubled CONSONANT
            # (mantoq buck/tokenization.py: `phon not in vowels and
            # phon[0] == phon[1]`); geminate it with a length mark.  A
            # vowel+_dbl_ sequence does not occur in genuine mantoq output
            # and is left unchanged.
            if out and last_tok in _HALABI_CONSONANTS \
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
        if tok in _HALABI_VOWELS:
            out.append(_HALABI_VOWELS[tok])
        elif tok in _HALABI_CONSONANTS:
            out.append(_HALABI_CONSONANTS[tok])
        elif tok in _WHITE_SPACE or tok in ".,;:!?()[]{}\"'":
            out.append(tok)
            last_tok = None
            continue
        else:
            res = _unknown(tok, pos, "halabi", errors)
            if res:
                out.append(res)
            last_tok = None
            continue
        last_tok = tok
    return "".join(out)


# ---------------------------------------------------------------------------
# IqraEval phoneme_ref -> IPA
#
# The IqraEval shared task (Interspeech 2025, doi:10.21437/Interspeech.2025-2411
# — "we employed the phonetizer introduced by Nawar Halabi") scores against a
# space-separated ``phoneme_ref`` column that is the raw Halabi phonetiser
# output with the stress/vowel-realization digits, the ``+`` word separator
# and the ``sil`` pause token stripped — but, unlike mantoq's own
# ``simplify_phonemes``, keeping the emphatic-allophone uppercase vowels
# (``A``/``AA``/``I``/``II``/``U``/``UU``) and gemination as a literal doubled
# consonant letter (``bb``, ``nn``, …) rather than a ``_dbl_`` marker. Table
# verified symbol-by-symbol against a 5,050-row IqraEval/Iqra_train sample by
# TigreGotico/arbtok's ``scripts/benchmark_iqraeval.py``; reproduced here
# (same license posture as ``halabi_to_ipa`` above: a factual symbol table,
# not the CC BY-NC phonetiser code).
# ---------------------------------------------------------------------------

_IQRA_CONSONANTS: dict[str, str] = {
    "b": "b", "t": "t", "^": "θ", "j": "dʒ", "H": "ħ", "x": "x", "d": "d",
    "*": "ð", "r": "r", "z": "z", "s": "s", "$": "ʃ", "S": "sˤ", "D": "dˤ",
    "T": "tˤ", "Z": "ðˤ", "E": "ʕ", "g": "ɣ", "f": "f", "q": "q", "k": "k",
    "l": "l", "m": "m", "n": "n", "h": "h", "w": "w", "y": "j", "<": "ʔ",
}
_IQRA_VOWELS: dict[str, str] = {
    "a": "a", "aa": "aː", "A": "ɑ", "AA": "ɑː",
    "i": "i", "ii": "iː", "I": "ɪ", "II": "ɪː",
    "u": "u", "uu": "uː", "U": "ʊ", "UU": "ʊː",
}
_IQRA_NOTATION: dict[str, str] = dict(_IQRA_VOWELS)
for _sym, _ipa in _IQRA_CONSONANTS.items():
    _IQRA_NOTATION[_sym] = _ipa
    _IQRA_NOTATION[_sym * 2] = _ipa + "ː"  # gemination: doubled token, shadda


def iqra_halabi_to_ipa(tokens: str, errors: str = "pass") -> str:
    """Convert IqraEval-flavored (already digit/separator/sil-stripped)
    space-separated Halabi tokens to IPA.

    Unlike :func:`halabi_to_ipa` (which targets mantoq's own simplified,
    lowercase-only inventory), this keeps the emphatic-allophone uppercase
    vowels distinct and reads gemination off a literal doubled consonant
    letter — the ``phoneme_ref`` convention.  Unknown tokens follow the
    ``errors`` policy (``"pass"`` by default: passed through verbatim).
    A space separates two phones, and ``phoneme_ref`` has no word boundary,
    so the output has no space.

    Examples
    --------
    >>> iqra_halabi_to_ipa("f ii h i x A y r aa t u n")
    'fiːhixɑjraːtun'
    """
    out = []
    for pos, tok in enumerate(t for t in _WHITE_SPACE_RE.split(tokens) if t):
        ipa = _IQRA_NOTATION.get(tok)
        if ipa is not None:
            out.append(ipa)
        else:
            res = _unknown(tok, pos, "halabi", errors, replacement=f"{{{{{tok}}}}}")
            if res:
                out.append(res)
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
    Notation.HALABI: halabi_to_ipa,
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

    A conversion is **lossless** when it passes this test for every symbol of
    its source inventory.  Both converters run with ``errors="strict"`` and
    with their other options at the defaults:

    1. The symbol converts, and every output symbol is in the target
       inventory.  An unmapped symbol passed through does not count, and
       neither does a table row whose output is not in that inventory.
    2. The reverse conversion returns the input.  Where the notation's
       reference gives two spellings of one symbol, the first spelling counts
       as the input.

    The source inventory of ``lossless_to_ipa`` is the notation's own symbol
    set.  The source inventory of ``lossless_from_ipa`` is the 1993 IPA Chart
    as X-SAMPA lists it, each symbol taken alone, so a flag makes no claim about
    a sequence of symbols.  A notation with no converter in the direction under
    test is not lossless in that direction.

    The conversion graph gives each IPA edge the flag of its direction.  The
    Buckwalter and Arabic-script edges pass the same test, so they are
    lossless too.  For them, an Arabic presentation form is a second spelling
    of the letters that NFKC gives.

    Attributes
    ----------
    notation:
        The :class:`Notation` this describes.
    lossless_to_ipa:
        ``<notation> → IPA`` is lossless.
    lossless_from_ipa:
        ``IPA → <notation>`` is lossless.
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
        reference="http://www.speech.cs.cmu.edu/cgi-bin/cmudict; "
                  "https://en.wikipedia.org/wiki/ARPABET",
    ),
    Notation.XSAMPA: NotationInfo(
        Notation.XSAMPA, lossless_to_ipa=True, lossless_from_ipa=True,
        token_separated=False,
        reference="Wells, Computer-coding the IPA: a proposed extension of "
                  "SAMPA, https://www.phon.ucl.ac.uk/home/sampa/x-sampa.htm",
    ),
    Notation.LEXIQUE: NotationInfo(
        Notation.LEXIQUE, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=False,
        reference="New & Pallier, Manuel de Lexique 3 v3.11, Tableau 2 (CC BY-SA 4.0)",
    ),
    Notation.KIRSHENBAUM: NotationInfo(
        Notation.KIRSHENBAUM, lossless_to_ipa=False, lossless_from_ipa=False,
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
    Notation.HALABI: NotationInfo(
        Notation.HALABI, lossless_to_ipa=False, lossless_from_ipa=False,
        token_separated=False,
        reference="Phonetic alphabet of Nawar Halabi's Arabic-Phonetiser "
                  "(mantoq G2P inventory); one-directional to IPA",
    ),
    Notation.BUCKWALTER: NotationInfo(
        Notation.BUCKWALTER, lossless_to_ipa=False, lossless_from_ipa=False,
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
