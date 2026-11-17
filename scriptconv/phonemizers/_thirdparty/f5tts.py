"""The text tokens of F5-TTS: hanzi as pinyin syllables, every other character as itself.

:func:`convert_char_to_pinyin` follows ``convert_char_to_pinyin`` in
``src/f5_tts/model/utils.py`` of SWivid/F5-TTS at commit 600e5fd, under the
MIT licence in ``LICENSE.f5tts``. F5-TTS runs it on every text that it speaks
and on its training text, so a model trained with the F5-TTS code reads these
tokens.
"""
from typing import List

# Upstream maps these marks before the segmentation, to reduce unknown tokens.
_CUSTOM_TRANS = str.maketrans({";": ",", "“": '"', "”": '"', "‘": "'", "’": "'"})


def is_chinese(char: str) -> bool:
    """Whether *char* is in the range that upstream reads as Chinese: U+3100 to U+9FFF."""
    return "㄀" <= char <= "鿿"


def convert_char_to_pinyin(text: str, polyphone: bool = True) -> List[str]:
    """The F5-TTS tokens of *text*.

    rjieba cuts the text into segments. A segment of ASCII characters gives
    its characters, after a space when it holds more than one character and
    the last token is not a space, ``:``, ``'`` or ``"``. A segment of
    three-byte characters gives a space and a pinyin syllable for each hanzi,
    in the TONE3 style with tone sandhi, and each other character as itself.
    In a mixed segment, each hanzi gives a space and its own syllable.
    """
    import rjieba
    from pypinyin import Style, lazy_pinyin

    tokens: List[str] = []
    for segment in rjieba.cut(text.translate(_CUSTOM_TRANS)):
        size = len(segment.encode("utf-8"))
        if size == len(segment):
            if tokens and size > 1 and tokens[-1] not in " :'\"":
                tokens.append(" ")
            tokens.extend(segment)
            continue
        if polyphone and size == 3 * len(segment):
            syllables = lazy_pinyin(segment, style=Style.TONE3, tone_sandhi=True)
            for index, char in enumerate(segment):
                if is_chinese(char):
                    tokens.append(" ")
                tokens.append(syllables[index])
            continue
        for char in segment:
            if ord(char) < 256:
                tokens.append(char)
            elif is_chinese(char):
                tokens.append(" ")
                tokens.extend(lazy_pinyin(char, style=Style.TONE3, tone_sandhi=True))
            else:
                tokens.append(char)
    return tokens
