"""Dictionary-backed script respelling (Japanese kanji → kana, Chinese hanzi → pinyin/bopomofo).

Unlike the table-driven modules (:mod:`scriptconv.translit`,
:mod:`scriptconv.notation`), converting kanji to kana is not a codepoint
mapping: a kanji's kana spelling is a *lexical* property resolved against a
reading dictionary, and genuinely ambiguous readings are decided by the
dictionary's segmentation.  This is still orthography — the output is how the
word is written in kana, exactly as an IME or furigana would render it — not
phonemization; no sound rules are applied.

The same reasoning covers Chinese: a hanzi's pinyin or bopomofo spelling is a
lexical property with genuinely ambiguous readings (heteronyms such as 行
xíng/háng) resolved by a phrase dictionary — standard orthographic respelling,
not phonemization.

Because it needs reading dictionaries, this module requires optional
dependencies: ``pykakasi`` for Japanese (``pip install scriptconv[ja]``) and
``pypinyin`` for Chinese (``pip install scriptconv[zh]``).  Importing the
module is always safe; the dependency is resolved on first conversion and a
missing dictionary raises :class:`ImportError` rather than silently returning
unconverted text.

pykakasi is GPL-3.0-or-later, so the Japanese functions (:func:`tokens`,
:func:`to_hiragana`, :func:`to_katakana` and :class:`ReadingToken`) are in the
scriptconv-copyleft package, which the ``ja`` extra installs.  The names here
import from it on first use.
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
