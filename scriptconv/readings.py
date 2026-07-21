"""Dictionary-backed script respelling (Japanese kanji → kana).

Unlike the table-driven modules (:mod:`scriptconv.translit`,
:mod:`scriptconv.notation`), converting kanji to kana is not a codepoint
mapping: a kanji's kana spelling is a *lexical* property resolved against a
reading dictionary, and genuinely ambiguous readings are decided by the
dictionary's segmentation.  This is still orthography — the output is how the
word is written in kana, exactly as an IME or furigana would render it — not
phonemization; no sound rules are applied.

Because it needs a reading dictionary, this module requires the optional
``pykakasi`` dependency (``pip install scriptconv[ja]``).  Importing the
module is always safe; the dependency is resolved on first conversion and a
missing dictionary raises :class:`ImportError` rather than silently returning
unconverted text.
"""
from __future__ import annotations

__all__ = ["to_hiragana", "to_katakana"]

_kakasi = None

_HIRA = range(0x3040, 0x30A0)
_KANA = range(0x30A0, 0x3100)


def _converter():
    global _kakasi
    if _kakasi is None:
        try:
            import pykakasi
        except ImportError:
            raise ImportError(
                "kanji→kana conversion needs the reading dictionary from "
                "pykakasi — install with `pip install scriptconv[ja]`"
            ) from None
        _kakasi = pykakasi.kakasi()
    return _kakasi


def to_hiragana(text: str, keep_katakana: bool = False) -> str:
    """Respell Japanese text in hiragana.

    Kanji are resolved to their dictionary reading; existing kana and any
    non-Japanese characters pass through.  With ``keep_katakana=True``,
    katakana tokens keep their original script (useful when katakana marks
    loanwords deliberately) instead of being folded into hiragana.
    """
    out = []
    for token in _converter().convert(text):
        orig = token["orig"]
        if keep_katakana and orig and all(ord(c) in _KANA or not _is_japanese(c)
                                          for c in orig):
            out.append(orig)
        else:
            out.append(token["hira"])
    return "".join(out)


def to_katakana(text: str) -> str:
    """Respell Japanese text in katakana.

    Kanji are resolved to their dictionary reading; existing kana are
    transposed to katakana and any non-Japanese characters pass through.
    """
    return "".join(token["kana"] for token in _converter().convert(text))


def _is_japanese(ch: str) -> bool:
    cp = ord(ch)
    return cp in _HIRA or cp in _KANA or 0x4E00 <= cp <= 0x9FFF
