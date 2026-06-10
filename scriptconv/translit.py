"""Grapheme-to-IPA transliteration for table-driven scripts.

Currently provides Hangul → IPA, ported from stannam/hangul_to_ipa
(https://github.com/stannam/hangul_to_ipa).

All conversion tables are inlined as Python dicts/tuples — no external
files or runtime dependencies.

Attribution: Hangul jamo tables and phonological rule ordering derived
from stannam/hangul_to_ipa.
"""
from __future__ import annotations

import math
import re
from typing import List

__all__ = ["hangul_to_ipa"]


# ---------------------------------------------------------------------------
# Hangul Unicode constants
# ---------------------------------------------------------------------------

_GA_CODE = 44032   # first Hangul syllable block (가)
_G_CODE = 12593    # first Hangul jamo (ㄱ)
_ONSET = 588
_CODA = 28

# 19 onsets
_ONSET_LIST = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ",
    "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)

# 21 vowels
_VOWEL_LIST = (
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
)

# 28 codas (index 0 = empty)
_CODA_LIST = (
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ",
    "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ",
    "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)

# ---------------------------------------------------------------------------
# IPA conversion table  (jamo → IPA symbol)
# Derived from stannam/hangul_to_ipa ipa.csv
# ---------------------------------------------------------------------------

_C_TO_IPA: dict[str, str] = {
    "ㅂ": "p",   "ㄷ": "t",   "ㅌ": "tʰ",  "ㅈ": "tɕ",  "ㅉ": "tɕ*",
    "ㅊ": "tɕʰ", "ㄱ": "k",   "ㅎ": "h",   "ㄲ": "k*",  "ㅋ": "kʰ",
    "ㄹ": "l",   "ㅁ": "m",   "ㄴ": "n",   "ㅇ": "ŋ",   "ㄸ": "t*",
    "ㅃ": "p*",  "ㅍ": "pʰ",  "ㅅ": "s",   "ㅆ": "s*",  "#": "#",  "$": "$",
}

_V_TO_IPA: dict[str, str] = {
    "ㅏ": "ä",   "ㅔ": "e",   "ㅐ": "ɛ",   "ㅣ": "i",   "ㅗ": "o",
    "ㅚ": "wɛ",  "ㅜ": "u",   "ㅓ": "ʌ̹",  "ㅡ": "ɯ",   "ㅢ": "ɰi",
    "ㅛ": "jo",  "ㅠ": "ju",  "ㅑ": "ja",  "ㅕ": "jʌ̹", "ㅖ": "je",
    "ㅒ": "jɛ",  "ㅘ": "wa",  "ㅝ": "wʌ̹", "ㅟ": "wi",  "ㅙ": "wɛ",
    "ㅞ": "we",
}

_CONSONANTS = tuple(k for k in _C_TO_IPA if k not in ("#", "$"))
_VOWELS = tuple(_V_TO_IPA.keys())
_SONORANT_JAMO = ("ㄴ", "ㄹ", "ㅇ", "ㅁ")
_OBSTRUENTS = tuple(c for c in _CONSONANTS if c not in _SONORANT_JAMO)
_SONORANTS = _VOWELS + _SONORANT_JAMO

# ---------------------------------------------------------------------------
# Phonological rule tables (inlined from ko_tables CSV files)
# ---------------------------------------------------------------------------

# Coda neutralization: maps coda jamo → its neutralized form
_NEUTRALIZATION: dict[str, str] = {
    "ㄲ": "ㄱ", "ㅋ": "ㄱ",
    "ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅊ": "ㄷ", "ㅌ": "ㄷ", "ㅎ": "ㄷ",
    "ㅂ": "ㅂ", "ㅍ": "ㅂ",
}

# Aspiration: jamo bigram → output jamo (simple string substitution)
_ASPIRATION_SUBST: list[tuple[str, str]] = [
    ("ㅎㄱ", "ㅋ"), ("ㅎㅋ", "ㅋ"), ("ㅎㄷ", "ㅌ"), ("ㅎㅌ", "ㅌ"),
    ("ㅎㅈ", "ㅊ"), ("ㅎㅊ", "ㅊ"), ("ㅎㅎ", "ㅌ"),
    ("ㄱㅎ", "ㅋ"), ("ㅋㅎ", "ㅋ"), ("ㄷㅎ", "ㅌ"), ("ㅌㅎ", "ㅌ"),
    ("ㅂㅎ", "ㅍ"), ("ㅍㅎ", "ㅍ"), ("ㅈㅎ", "ㅊ"), ("ㅊㅎ", "ㅌ"),
    ("ㅅㅎ", "ㅆ"),
]

# Assimilation: jamo bigram → output jamo pair
_ASSIMILATION_SUBST: list[tuple[str, str]] = [
    ("ㄱㄴ", "ㅇㄴ"), ("ㄲㄴ", "ㅇㄴ"), ("ㅋㄴ", "ㅇㄴ"),
    ("ㄱㅁ", "ㅇㅁ"), ("ㄲㅁ", "ㅇㅁ"), ("ㅋㅁ", "ㅇㅁ"),
    ("ㄷㄴ", "ㄴㄴ"), ("ㅅㄴ", "ㄴㄴ"), ("ㅆㄴ", "ㄴㄴ"),
    ("ㅈㄴ", "ㄴㄴ"), ("ㅊㄴ", "ㄴㄴ"), ("ㅌㄴ", "ㄴㄴ"), ("ㅎㄴ", "ㄴㄴ"),
    ("ㄷㅁ", "ㄴㅁ"), ("ㅅㅁ", "ㄴㅁ"), ("ㅆㅁ", "ㄴㅁ"),
    ("ㅈㅁ", "ㄴㅁ"), ("ㅊㅁ", "ㄴㅁ"), ("ㅌㅁ", "ㄴㅁ"), ("ㅎㅁ", "ㄴㅁ"),
    ("ㅂㄴ", "ㅁㄴ"), ("ㅍㄴ", "ㅁㄴ"), ("ㅂㅁ", "ㅁㅁ"), ("ㅍㅁ", "ㅁㅁ"),
    ("ㅁㄹ", "ㅁㄴ"), ("ㅇㄹ", "ㅇㄴ"), ("ㄱㄹ", "ㅇㄴ"),
    ("ㅂㄹ", "ㅁㄴ"), ("ㄴㄹ", "ㄹㄹ"), ("ㄹㄴ", "ㄹㄹ"),
]

# Tensification: jamo bigram → output jamo pair
_TENSIFICATION_SUBST: list[tuple[str, str]] = [
    ("ㄱㄱ", "ㄱㄲ"), ("ㄲㄱ", "ㄲㄲ"), ("ㅋㄱ", "ㅋㄲ"),
    ("ㄱㄷ", "ㄱㄸ"), ("ㄲㄷ", "ㄲㄸ"), ("ㅋㄷ", "ㅋㄸ"),
    ("ㄱㅂ", "ㄱㅃ"), ("ㄲㅂ", "ㄲㅃ"), ("ㅋㅂ", "ㅋㅃ"),
    ("ㄱㅅ", "ㄱㅆ"), ("ㄲㅅ", "ㄲㅆ"), ("ㅋㅅ", "ㅋㅆ"),
    ("ㄱㅈ", "ㄱㅉ"), ("ㄲㅈ", "ㄲㅉ"), ("ㅋㅈ", "ㅋㅉ"),
    ("ㄷㄱ", "ㄷㄲ"), ("ㅅㄱ", "ㅅㄲ"), ("ㅆㄱ", "ㅆㄲ"),
    ("ㅈㄱ", "ㅈㄲ"), ("ㅊㄱ", "ㅊㄲ"), ("ㅌㄱ", "ㅌㄲ"),
    ("ㄷㄷ", "ㄷㄸ"), ("ㅅㄷ", "ㅅㄸ"), ("ㅆㄷ", "ㅆㄸ"),
    ("ㅈㄷ", "ㅈㄸ"), ("ㅊㄷ", "ㅊㄸ"), ("ㅌㄷ", "ㅌㄸ"),
    ("ㄷㅂ", "ㄷㅃ"), ("ㅅㅂ", "ㅅㅃ"), ("ㅆㅂ", "ㅆㅃ"),
    ("ㅈㅂ", "ㅈㅃ"), ("ㅊㅂ", "ㅊㅃ"), ("ㅌㅂ", "ㅌㅃ"),
    ("ㄷㅅ", "ㄷㅆ"), ("ㅅㅅ", "ㅅㅆ"), ("ㅆㅅ", "ㅆㅆ"),
    ("ㅈㅅ", "ㅈㅆ"), ("ㅊㅅ", "ㅊㅆ"), ("ㅌㅅ", "ㅌㅆ"),
    ("ㄷㅈ", "ㄷㅉ"), ("ㅅㅈ", "ㅅㅉ"), ("ㅆㅈ", "ㅆㅉ"),
    ("ㅈㅈ", "ㅈㅉ"), ("ㅊㅈ", "ㅊㅉ"), ("ㅌㅈ", "ㅌㅉ"),
    ("ㅂㄱ", "ㅂㄲ"), ("ㅍㄱ", "ㅍㄲ"), ("ㅂㄷ", "ㅂㄸ"), ("ㅍㄷ", "ㅍㄸ"),
    ("ㅂㅂ", "ㅂㅃ"), ("ㅍㅂ", "ㅍㅃ"), ("ㅂㅅ", "ㅂㅆ"), ("ㅍㅅ", "ㅍㅆ"),
    ("ㅂㅈ", "ㅂㅉ"), ("ㅍㅈ", "ㅍㅉ"),
]

# Double coda: compound jamo → (separated, simplified) pairs
_DOUBLE_CODA: dict[str, tuple[str, str]] = {
    "ㄳ": ("ㄱㅅ", "ㄱ"), "ㄵ": ("ㄴㅈ", "ㄴ"), "ㄼ": ("ㄹㅂ", "ㄹ"),
    "ㄽ": ("ㄹㅅ", "ㄹ"), "ㄾ": ("ㄹㅌ", "ㄹ"), "ㅄ": ("ㅂㅅ", "ㅂ"),
    "ㄺ": ("ㄹㄱ", "ㄱ"), "ㄻ": ("ㄹㅁ", "ㅁ"), "ㄿ": ("ㄹㅍ", "ㅂ"),
    "ㄶ": ("ㄴㅎ", "ㄴ"), "ㅀ": ("ㄹㅎ", "ㄹ"),
}

# ---------------------------------------------------------------------------
# Helper: decompose a Hangul syllable block to (onset, vowel, coda) jamo
# ---------------------------------------------------------------------------

def _syllable_to_jamo(ch: str) -> str:
    """Decompose one Hangul syllable block into onset+vowel+coda jamo.

    Non-syllable characters are returned unchanged.
    """
    if not ("가" <= ch <= "힣"):
        return ch
    code = ord(ch) - _GA_CODE
    onset_idx = math.floor(code / _ONSET)
    vowel_idx = math.floor((code - _ONSET * onset_idx) / _CODA)
    coda_idx = code - _ONSET * onset_idx - _CODA * vowel_idx
    return _ONSET_LIST[onset_idx] + _VOWEL_LIST[vowel_idx] + _CODA_LIST[coda_idx]


def _word_to_jamo(word: str, no_empty_onset: bool = True) -> str:
    """Convert a Hangul word to a flat jamo string."""
    syllables = [_syllable_to_jamo(ch) for ch in word]
    jamo = "".join(syllables)
    # Remove soundless syllable-initial ㅇ
    if no_empty_onset:
        result = []
        i = 0
        while i < len(syllables):
            syl = syllables[i]
            if syl and syl[0] == "ㅇ":
                result.append(syl[1:])
            else:
                result.append(syl)
            i += 1
        jamo = "".join(result)
    return jamo


# ---------------------------------------------------------------------------
# CV marking
# ---------------------------------------------------------------------------

def _mark_cv(jamo: str) -> str:
    result = ""
    for j in jamo:
        if j in _V_TO_IPA:
            result += "V"
        elif j in _C_TO_IPA:
            result += "C"
    return result


# ---------------------------------------------------------------------------
# Phonological rules
# ---------------------------------------------------------------------------

def _apply_subst_list(jamo: str, subst: list[tuple[str, str]]) -> str:
    for src, dst in subst:
        jamo = jamo.replace(src, dst)
    return jamo


def _separate_double_codas(jamo: str) -> str:
    result = []
    for ch in jamo:
        if ch in _DOUBLE_CODA:
            result.append(_DOUBLE_CODA[ch][0])
        else:
            result.append(ch)
    return "".join(result)


def _simplify_coda_clusters(jamo: str) -> str:
    """Reduce CCC sequences and word-final CC."""
    cv = _mark_cv(jamo)
    # Repeat until stable
    while True:
        # Find VCCC patterns
        m = re.search("(?<=V)CC(?=C)", cv)
        if not m:
            break
        # Find position in jamo corresponding to cc_start
        jamo_chars = list(jamo)
        cv_chars = list(cv)
        # Rebuild from scratch after substitution
        jamo, cv = _reduce_one_vccc(jamo, cv)

    # Word-final CC
    if cv.endswith("CC"):
        jamo_chars = list(jamo)
        cv_chars = list(cv)
        # Find the two trailing consonant positions in jamo
        c_positions = [i for i, c in enumerate(cv_chars) if c == "C"]
        if len(c_positions) >= 2:
            cc_start = c_positions[-2]
            double = jamo[cc_start:cc_start + 2]
            simplified = _DOUBLE_CODA.get(double, ("", double[0]))[1]
            jamo_chars[cc_start] = simplified
            jamo_chars[cc_start + 1] = ""
            jamo = "".join(jamo_chars)
            cv = _mark_cv(jamo)
    return jamo


def _reduce_one_vccc(jamo: str, cv: str) -> tuple[str, str]:
    """Reduce the leftmost VCCC in *jamo*."""
    jamo_chars = list(jamo)
    cv_chars = list(cv)
    # Map CV positions to jamo indices
    j_to_cv: list[int] = []
    for i, ch in enumerate(jamo):
        if ch in _V_TO_IPA or ch in _C_TO_IPA:
            j_to_cv.append(i)
    for idx in range(len(cv) - 3):
        if cv[idx:idx+4] == "VCCC":
            # idx is the V; idx+1, idx+2 = CC to simplify; idx+3 = next C
            cc_pos = j_to_cv[idx + 1]
            double = jamo[cc_pos:cc_pos + 2]
            simplified = _DOUBLE_CODA.get(double, ("", double[0]))[1]
            jamo_chars[cc_pos] = simplified
            jamo_chars[cc_pos + 1] = ""
            jamo = "".join(jamo_chars)
            cv = _mark_cv(jamo)
            return jamo, cv
    return jamo, cv


def _neutralize_codas(jamo: str) -> str:
    cv = _mark_cv(jamo)
    chars = list(jamo)
    for i, ch in enumerate(jamo):
        if ch not in _C_TO_IPA:
            continue
        # Is this jamo in coda position? It is if it's the last C/V or
        # followed by another C.
        cv_i = len(_mark_cv(jamo[:i + 1])) - 1
        cv_rest = _mark_cv(jamo[i + 1:])
        if cv_rest == "" or cv_rest[0] == "C":
            chars[i] = _NEUTRALIZATION.get(ch, ch)
    return "".join(chars)


def _delete_h(jamo: str) -> str:
    chars = list(jamo)
    sonorant_ipa = set(_V_TO_IPA.keys()) | set(_SONORANT_JAMO)
    for i in range(1, len(chars) - 1):
        if chars[i] == "ㅎ":
            if chars[i - 1] in sonorant_ipa and chars[i + 1] in sonorant_ipa:
                chars[i] = ""
    return "".join(chars)


def _non_coronalize(jamo: str) -> str:
    velars = set("ㄱㅋㄲ")
    bilabials = set("ㅂㅍㅃㅁ")
    non_velar_nasals = {"ㅁ", "ㄴ"}
    chars = list(jamo)
    for i in range(len(chars) - 1):
        if chars[i] in non_velar_nasals:
            nxt = chars[i + 1]
            if nxt in velars:
                chars[i] = "ㅇ"
            elif nxt in bilabials:
                chars[i] = "ㅁ"
    return "".join(chars)


def _palatalize(jamo: str) -> str:
    chars = list(jamo)
    pal_map = {"ㄷ": "ㅈ", "ㅌ": "ㅊ"}
    for i in range(len(chars) - 1):
        if chars[i] in pal_map and chars[i + 1] == "ㅣ":
            chars[i] = pal_map[chars[i]]
    return "".join(chars)


# ---------------------------------------------------------------------------
# Phonetic level rules (IPA symbols)
# ---------------------------------------------------------------------------

def _inter_v(symbols: List[str]) -> List[str]:
    voicing = {"p": "b", "t": "d", "k": "ɡ", "tɕ": "dʑ"}
    ipa_sonorants = set(_V_TO_IPA.values()) | {
        _C_TO_IPA[j] for j in _SONORANT_JAMO if j in _C_TO_IPA
    }
    res = list(symbols)
    for i in range(1, len(symbols) - 1):
        if symbols[i] in voicing:
            if symbols[i - 1] in ipa_sonorants and symbols[i + 1] in ipa_sonorants:
                res[i] = voicing[symbols[i]]
            elif symbols[i - 1] in ipa_sonorants and symbols[i + 1] == "ɕ":
                res[i] = voicing[symbols[i]]
                res[i + 1] = "ʑ"
    return res


def _alternate_lr(symbols: List[str]) -> List[str]:
    ipa_vowels = set(_V_TO_IPA.values())
    res = list(symbols)
    for i in range(1, len(symbols) - 1):
        if res[i] == "l" and res[i - 1] in ipa_vowels and res[i + 1] in ipa_vowels:
            res[i] = "ɾ"
    return res


# ---------------------------------------------------------------------------
# Core transcription
# ---------------------------------------------------------------------------

def _transcribe_jamo(jamo: str) -> List[str]:
    result = []
    for j in jamo:
        if j in _V_TO_IPA:
            result.append(_V_TO_IPA[j])
        elif j in _C_TO_IPA and j not in ("#", "$"):
            result.append(_C_TO_IPA[j])
    return result


def _apply_rules(jamo: str) -> str:
    """Apply Korean phonological rules to a jamo string."""
    # Palatalization
    if "ㄷㅣ" in jamo or "ㅌㅣ" in jamo:
        jamo = _palatalize(jamo)
    # Aspiration
    if "ㅎ" in jamo:
        jamo = _apply_subst_list(jamo, _ASPIRATION_SUBST)
    # Assimilation
    jamo = _apply_subst_list(jamo, _ASSIMILATION_SUBST)
    # Tensification
    if any(ob in jamo for ob in _OBSTRUENTS):
        jamo = _apply_subst_list(jamo, _TENSIFICATION_SUBST)
    # Coda cluster simplification
    jamo = _separate_double_codas(jamo)
    jamo = _simplify_coda_clusters(jamo)
    # Coda neutralization
    jamo = _neutralize_codas(jamo)
    # H-deletion (word-internal)
    if "ㅎ" in jamo[1:-1]:
        jamo = _delete_h(jamo)
    # Non-coronalization
    jamo = _non_coronalize(jamo)
    return jamo


def _convert_word(hangul: str) -> str:
    """Convert one Hangul word to IPA."""
    if not hangul:
        return ""
    # Decompose to jamo
    jamo = _word_to_jamo(hangul)
    # Apply phonological rules
    jamo = _apply_rules(jamo)
    # Transcribe to IPA
    symbols = _transcribe_jamo(jamo)
    # Phonetic rules
    symbols = _inter_v(symbols)
    if "l" in symbols:
        symbols = _alternate_lr(symbols)
    return "".join(symbols)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hangul_to_ipa(text: str) -> str:
    """Convert a Hangul string to IPA.

    Words are split on whitespace and converted independently.

    Attribution: phonological rule pipeline derived from
    stannam/hangul_to_ipa (https://github.com/stannam/hangul_to_ipa).

    Examples
    --------
    >>> hangul_to_ipa("안녕하세요")
    'annjʌ̹ɦäse̞jo'
    """
    results = []
    for word in text.split():
        results.append(_convert_word(word))
    return " ".join(results)
