"""Script-level decomposition and transliteration utilities.

Hangul syllable blocks decompose arithmetically into their jamo
letters (Unicode Hangul Syllables, U+AC00–U+D7A3) — a property of the
WRITING SYSTEM, independent of pronunciation. Jamo tables derived from
stannam/hangul_to_ipa.

Hiragana and Katakana are two encodings of the same kana syllabary,
separated by a fixed U+0060 codepoint offset (Unicode Hiragana U+3040
and Katakana U+30A0 blocks); swapping between them is pure orthography.

This module deliberately contains no phonology: mapping scripts to
SOUNDS (grapheme-to-phoneme with contextual rules) is phonemization
and lives outside scriptconv's scope.
"""
from __future__ import annotations

__all__ = ["decompose_hangul", "hira_to_kana", "kana_to_hira"]

# Modern jamo in Unicode order.  The 19 leads, 21 vowels and 27 non-empty
# tails line up index-for-index with both the compatibility jamo block
# (U+3130) and the conjoining jamo blocks (L U+1100, V U+1161, T U+11A8).
_ONSETS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_CODAS = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ",
          "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
          "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")

_BASE = 0xAC00
_LAST = 0xD7A3

# Conjoining jamo block anchors (Unicode 3.0, "Hangul Jamo").
_L_BASE = 0x1100  # leading consonants
_V_BASE = 0x1161  # medial vowels
_T_BASE = 0x11A8  # trailing consonants (index 0 == first non-empty tail)

_SILENT_INITIAL = 11  # onset index of ㅇ (ieung), a placeholder in onset position


def decompose_hangul(
    text: str,
    form: str = "compatibility",
    drop_silent_initial: bool = False,
) -> str:
    """Decompose Hangul syllable blocks into their jamo letters.

    Non-Hangul characters pass through unchanged. Joining behaviour is
    purely orthographic — no sound rules are applied.

    Parameters
    ----------
    text:
        Input string.
    form:
        A style of the ``jamo-form`` convention
        (:mod:`scriptconv.conventions`);
        ``"compatibility"`` (default) emits Hangul Compatibility Jamo
        (U+3130 block, e.g. ``ㄱ``); ``"conjoining"`` emits conjoining
        jamo (U+1100/1161/11A8 blocks) that recombine into syllables.
    drop_silent_initial:
        When True, omit the placeholder onset ``ㅇ`` (ieung) in
        syllable-initial position — useful when the initial carries no
        consonant. Applies to both forms.

    Returns
    -------
    str
        The decomposed string.

    Examples
    --------
    >>> decompose_hangul("가")
    'ㄱㅏ'
    >>> decompose_hangul("안", drop_silent_initial=True)
    'ㅏㄴ'
    """
    if form not in ("compatibility", "conjoining"):
        raise ValueError(
            f"form must be 'compatibility' or 'conjoining', not {form!r}"
        )
    conjoining = form == "conjoining"
    out = []
    for ch in text:
        code = ord(ch)
        if _BASE <= code <= _LAST:
            idx = code - _BASE
            o = idx // 588
            v = (idx % 588) // 28
            t = idx % 28
            if drop_silent_initial and o == _SILENT_INITIAL:
                onset = ""
            elif conjoining:
                onset = chr(_L_BASE + o)
            else:
                onset = _ONSETS[o]
            if conjoining:
                vowel = chr(_V_BASE + v)
                coda = chr(_T_BASE + t - 1) if t else ""
            else:
                vowel = _VOWELS[v]
                coda = _CODAS[t]
            out.append(onset + vowel + coda)
        else:
            out.append(ch)
    return "".join(out)


# Hiragana ↔ Katakana are separated by a fixed +0x60 offset.  The ranges
# below cover the letters (small + full kana) and the iteration marks that
# have a counterpart in both blocks; katakana-only signs (long-vowel mark
# U+30FC, the U+30F7–30FA v-kana, U+30FF) have no hiragana form and pass
# through unchanged.
_HIRA_MIN, _HIRA_MAX = 0x3041, 0x3096
_KANA_MIN, _KANA_MAX = 0x30A1, 0x30F6
_ITER_HIRA = (0x309D, 0x309E)
_ITER_KANA = (0x30FD, 0x30FE)
_OFFSET = 0x60


def hira_to_kana(text: str) -> str:
    """Transliterate Hiragana to Katakana. Other characters pass through.

    Examples
    --------
    >>> hira_to_kana("ひらがな")
    'ヒラガナ'
    """
    out = []
    for ch in text:
        o = ord(ch)
        if _HIRA_MIN <= o <= _HIRA_MAX or o in _ITER_HIRA:
            out.append(chr(o + _OFFSET))
        else:
            out.append(ch)
    return "".join(out)


def kana_to_hira(text: str) -> str:
    """Transliterate Katakana to Hiragana. Other characters pass through.

    The katakana-only long-vowel mark ``ー`` (U+30FC) has no hiragana
    counterpart and is left unchanged.

    Examples
    --------
    >>> kana_to_hira("カタカナ")
    'かたかな'
    """
    out = []
    for ch in text:
        o = ord(ch)
        if _KANA_MIN <= o <= _KANA_MAX or o in _ITER_KANA:
            out.append(chr(o - _OFFSET))
        else:
            out.append(ch)
    return "".join(out)
