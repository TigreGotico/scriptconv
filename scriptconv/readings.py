"""Dictionary-backed script respelling (Japanese kanji → kana, Chinese hanzi → pinyin/bopomofo).

The kana or pinyin spelling of a kanji or hanzi is a lexical property, so a
reading dictionary resolves it, ambiguous readings (行 xíng/háng) included.
The output is orthography, as an IME or furigana writes it; no sound rules
apply.

The dictionaries are optional: ``pykakasi`` for Japanese (``scriptconv[ja]``)
and ``pypinyin`` for Chinese (``scriptconv[zh]``).  Importing the module is
always safe; the first conversion without its dictionary raises
:class:`ImportError`.  pykakasi is GPL-3.0-or-later, so the Japanese names
(:func:`tokens`, :func:`to_hiragana`, :func:`to_katakana`,
:class:`ReadingToken`) live in scriptconv-copyleft and import from it on first
use.
"""
from __future__ import annotations

__all__ = ["to_pinyin", "to_bopomofo"]

_JAPANESE = frozenset({"ReadingToken", "tokens", "to_hiragana", "to_katakana"})


def __getattr__(name: str):
    if name not in _JAPANESE:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        from scriptconv_copyleft import readings
    except ImportError:
        raise ImportError(
            f"scriptconv.readings.{name} is in scriptconv-copyleft, with the "
            "pykakasi reading dictionary — install with `pip install scriptconv[ja]`"
        ) from None
    return getattr(readings, name)


_PINYIN_STYLES = None


def _pinyin(text: str, style_name: str) -> str:
    global _PINYIN_STYLES
    if _PINYIN_STYLES is None:
        try:
            from pypinyin import Style, lazy_pinyin
        except ImportError:
            raise ImportError(
                "hanzi→pinyin/bopomofo conversion needs the phrase dictionary "
                "from pypinyin — install with `pip install scriptconv[zh]`"
            ) from None
        _PINYIN_STYLES = {"mark": Style.TONE, "number": Style.TONE3,
                          "none": Style.NORMAL, "bopomofo": Style.BOPOMOFO,
                          "_fn": lazy_pinyin}
    if style_name not in _PINYIN_STYLES:
        raise ValueError(f"tone must be one of 'mark', 'number', 'none' — got {style_name!r}")
    tokens = _PINYIN_STYLES["_fn"](text, style=_PINYIN_STYLES[style_name])
    return " ".join(" ".join(tokens).split())


def to_pinyin(text: str, tone: str = "mark") -> str:
    """Respell Chinese text in pinyin, syllables space-separated.

    Hanzi are resolved to their dictionary reading (heteronyms decided by
    pypinyin's phrase dictionary); non-Chinese characters pass through.
    ``tone`` selects the tone spelling: ``"mark"`` (``zhōng``, default),
    ``"number"`` (``zhong1``) or ``"none"`` (``zhong``) — the styles of the
    ``pinyin-tone`` convention (:mod:`scriptconv.conventions`); use
    :func:`scriptconv.restyle` to convert existing pinyin between them
    without the ``zh`` extra.
    """
    return _pinyin(text, tone)


def to_bopomofo(text: str) -> str:
    """Respell Chinese text in bopomofo (zhuyin), syllables space-separated.

    Hanzi are resolved to their dictionary reading; non-Chinese characters
    pass through.  Tone marks follow zhuyin convention (first tone unmarked).
    """
    return _pinyin(text, "bopomofo")
