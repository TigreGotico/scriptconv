"""Vendored Kabyle grapheme-to-phoneme rules from agbalu/Matoub-82M.

Source: https://huggingface.co/agbalu/Matoub-82M, file ``tokenization_matoub.py``
at revision ``3d00056f3663d4d1d364e9b12c21230685a0ba9a``, sha256
``c95fdf4bd23efa649287662a0059d9053d17c8cab4fade383784e084cc422416``, the value
the model's own ``export.stats.json`` records for that file. Licence Apache-2.0,
the same licence this repository uses. See ``LICENSE.md`` beside this file.

Only the rule functions are kept. The upstream ``MatoubTokenizer`` class is
dropped: it subclasses ``transformers.PreTrainedTokenizer``, and scriptconv
emits phoneme strings, not model ids. The ``vocab.json`` constant goes with it.
The rules themselves are unchanged, because a caller that feeds Matoub-82M needs
the exact string that model was fitted on.

The upstream file states that these rules are a copy of ``agbalu.tts.g2p`` and
``agbalu.tts.kokoro``, kept in step by a test in that project. This copy is one
step further away, so ``tests/test_phonemizers_matoub_kab.py`` holds it to
measured outputs.
"""

from __future__ import annotations

import re
from typing import Final


VOWELS: Final = frozenset("aeiou")

BACKING_TRIGGERS: Final = frozenset("ḍṣṭẓṛqɣx")

SPIRANTS: Final[dict[str, tuple[str, str]]] = {
    "b": ("β", "b"),
    "d": ("ð", "d"),
    "g": ("ʝ", "ɡ"),
    "k": ("ç", "k"),
    "t": ("θ", "t"),
    "ḍ": ("ðˤ", "dˤ"),
}

PLAIN: Final[dict[str, str]] = {
    "a": "æ",
    "c": "ʃ",
    "e": "ə",
    "f": "f",
    "h": "h",
    "i": "i",
    "j": "ʒ",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "o",
    "p": "p",
    "q": "q",
    "r": "r",
    "s": "s",
    "u": "u",
    "v": "v",
    "w": "w",
    "x": "χ",
    "y": "j",
    "z": "z",
    "č": "t͡ʃ",
    "ǧ": "d͡ʒ",
    "ɛ": "ʕ",
    "ɣ": "ʁ",
    "ḥ": "ħ",
    "ṛ": "rˤ",
    "ṣ": "sˤ",
    "ṭ": "tˤ",
    "ẓ": "zˤ",
}

NASAL_ASSIMILATION: Final[dict[str, str]] = {"f": "m", "m": "m", "y": "ɲ", "q": "ŋ", "x": "ŋ"}

FOLD: Final[dict[str, str]] = {"t͡ʃ": "ʧ", "d͡ʒ": "ʤ"}
"""Tie-bar sequences the base model already carries as single symbols."""

LEGACY_TENSE_T: Final = "ţ"
LENGTH: Final = "ː"
BOUNDARY: Final = " "

_SPLIT: Final = re.compile(r"[\s\-]+")
_STRIP: Final = "«»\"'“”‘’.,;:!?()[]{}…"


class PhonemeError(ValueError):
    """A character with no rule."""


def _segment(word: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    index = 0
    while index < len(word):
        char = word[index]
        paired = index + 1 < len(word) and word[index + 1] == char and char not in VOWELS
        segments.append((char, paired))
        index += 2 if paired else 1
    return segments


def _backed(chars: list[str], position: int) -> bool:
    before = chars[position - 1] if position > 0 else ""
    after = chars[position + 1] if position + 1 < len(chars) else ""
    return before in BACKING_TRIGGERS or after in BACKING_TRIGGERS


def phonemize_word(word: str) -> str:
    """One orthographic word to IPA. Raises on any character without a rule."""
    segments = _segment(word.casefold())
    chars = [char for char, _ in segments]
    out: list[str] = []
    for position, (char, geminate) in enumerate(segments):
        if char == LEGACY_TENSE_T:
            out.append(SPIRANTS["t"][1] + LENGTH)
            continue
        if char in SPIRANTS:
            short, stop = SPIRANTS[char]
            out.append(stop + LENGTH if geminate else short)
            continue
        if char not in PLAIN:
            message = f"no rule for {char!r} (U+{ord(char):04X}) in {word!r}"
            raise PhonemeError(message)
        if char == "a" and _backed(chars, position):
            symbol = "ɑ"
        elif char == "n" and not geminate and position + 1 < len(chars):
            symbol = NASAL_ASSIMILATION.get(chars[position + 1], PLAIN["n"])
        else:
            symbol = PLAIN[char]
        out.append(symbol + LENGTH if geminate else symbol)
    return "".join(out)


def fold(ipa: str) -> str:
    """Rewrite tie-bar affricates onto the base model's own single symbols."""
    for sequence, symbol in FOLD.items():
        ipa = ipa.replace(sequence, symbol)
    return ipa


def phonemize(text: str) -> str:
    """A Kabyle sentence to the phoneme string the model was fitted on."""
    words = [token.strip(_STRIP) for token in _SPLIT.split(text) if token.strip(_STRIP)]
    return fold(BOUNDARY.join(phonemize_word(word) for word in words))
