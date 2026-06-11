"""Script-level decomposition utilities.

Hangul syllable blocks decompose arithmetically into their jamo
letters (Unicode Hangul Syllables, U+AC00–U+D7A3) — a property of the
WRITING SYSTEM, independent of pronunciation. Jamo tables derived from
stannam/hangul_to_ipa.

This module deliberately contains no phonology: mapping scripts to
SOUNDS (grapheme-to-phoneme with contextual rules) is phonemization
and lives outside scriptconv's scope.
"""
from __future__ import annotations

__all__ = ["decompose_hangul"]

_ONSETS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_CODAS = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ",
          "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
          "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")

_BASE = 0xAC00
_LAST = 0xD7A3


def decompose_hangul(text: str) -> str:
    """Decompose Hangul syllable blocks into their jamo letters.

    Non-Hangul characters pass through unchanged. Joining behaviour is
    purely orthographic — no sound rules are applied.
    """
    out = []
    for ch in text:
        code = ord(ch)
        if _BASE <= code <= _LAST:
            idx = code - _BASE
            onset = _ONSETS[idx // 588]
            vowel = _VOWELS[(idx % 588) // 28]
            coda = _CODAS[idx % 28]
            out.append(onset + vowel + coda)
        else:
            out.append(ch)
    return "".join(out)
