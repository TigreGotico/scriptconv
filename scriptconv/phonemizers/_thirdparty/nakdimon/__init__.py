"""Hebrew niqqud from the Nakdimon ONNX model.

Nakdimon (Gershuni and Pinter, "Restoring Hebrew Diacritics Without a
Dictionary", Findings of NAACL 2022) predicts, for each letter, a vowel
point, a dagesh and a shin or sin dot.

Adapted from https://github.com/elazarg/nakdimon at commit
5b73cdd6a43ad465faabc8c1118933592df356c8, Copyright 2022 Elazar Gershuni,
under the MIT License (the ``LICENSE`` file in this directory). The character
tables, :func:`normalize`, :func:`remove_niqqud` and the ``can_*`` tests come
from ``nakdimon/hebrew.py``. The tables with their mask entry come from
``CharacterTable`` in ``nakdimon/dataset.py``, and the order in which
:meth:`Nakdimon.diacritize` writes the marks comes from ``merge`` in the same
file. Unlike ``nakdimon/predict.py``, the model reads the whole text as one
sequence, with no padding and no split into lines. Upstream ``normalize`` also
maps each final letter to its regular form, after the test for a valid
letter; the final letters are valid letters, so that map is left out.

The loop of :meth:`Nakdimon.diacritize` over the letters and the tuple form of
the tests in :func:`normalize` follow the port in ``src/piper/hebrew/__init__.py``
of https://github.com/OHF-Voice/piper1-gpl at commit
d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, by Michael Hansen, which its
directory ships under the same MIT License.
"""
import re
from typing import List

import numpy as np

__all__ = ["Nakdimon", "remove_niqqud"]

# A letter that could take a mark of a class but takes none.
RAFE = "\u05BF"
HEBREW_LETTERS = [chr(c) for c in range(0x05D0, 0x05EA + 1)]
NIQQUD = [RAFE] + [chr(c) for c in range(0x05B0, 0x05BC + 1)] + ["\u05B7"]
NIQQUD_SIN = [RAFE, "\u05C1", "\u05C2"]
DAGESH = [RAFE, "\u05BC"]
VALID_LETTERS = [" ", "!", '"', "'", "(", ")", ",", "-", ".", ":", ";", "?"] + HEBREW_LETTERS
SPECIAL_TOKENS = ["H", "O", "5"]

# Each class table starts with the mask entry, so a model class is an index.
_LETTER_IDS = {c: i for i, c in enumerate([""] + SPECIAL_TOKENS + VALID_LETTERS)}
_NIQQUD = [""] + NIQQUD
_SIN = [""] + NIQQUD_SIN
_DAGESH = [""] + DAGESH

_NIQQUD_MARKS = re.compile("[\u05B0-\u05BC\u05C1\u05C2\u05C7\u05BF]")


def remove_niqqud(text: str) -> str:
    """*text* without its vowel points, dagesh, shin and sin dots, and rafe."""
    return _NIQQUD_MARKS.sub("", text)


def normalize(c: str) -> str:
    """The character of the model's alphabet that stands for *c*."""
    if c in VALID_LETTERS:
        return c
    if c in ("\n", "\t"):
        return " "
    if c in ("־", "‒", "–", "—", "―", "−"):
        return "-"
    if c == "[":
        return "("
    if c == "]":
        return ")"
    if c in ("´", "‘", "’"):
        return "'"
    if c in ("“", "”", "״"):
        return '"'
    if c.isdigit():
        return "5"
    if c == "…":
        return ","
    if c in ("ײ", "װ", "ױ"):
        return "H"
    return "O"


def can_dagesh(letter: str) -> bool:
    return letter in "בגדהוזטיכלמנספצקשת" + "ךף"


def can_sin(letter: str) -> bool:
    return letter == "ש"


def can_niqqud(letter: str) -> bool:
    return letter in "אבגדהוזחטיכלמנסעפצקרשת" + "ךן"


class Nakdimon:
    """Restores niqqud with one Nakdimon ONNX model.

    Args:
        session: an ``onnxruntime.InferenceSession`` of a Nakdimon model. The
            model reads the letter ids as its input type, int32 or float.
    """

    def __init__(self, session):
        self.session = session
        model_input = session.get_inputs()[0]
        self._input_name = model_input.name
        self._input_type = np.float32 if model_input.type == "tensor(float)" else np.int32

    def diacritize(self, text: str) -> str:
        """*text* with niqqud. The model reads the letters without the marks they had."""
        letters = list(remove_niqqud(text))
        if not letters:
            return ""
        ids = np.array([[_LETTER_IDS[normalize(c)] for c in letters]], dtype=self._input_type)
        niqqud, dagesh, sin = (np.argmax(out[0], axis=-1)
                               for out in self.session.run(None, {self._input_name: ids}))
        out: List[str] = []
        for letter, n, d, s in zip(letters, niqqud, dagesh, sin):
            out.append(letter)
            if can_dagesh(letter):
                out.append(_DAGESH[d])
            if can_sin(letter):
                out.append(_SIN[s])
            if can_niqqud(letter):
                out.append(_NIQQUD[n])
        return "".join(out).replace(RAFE, "")
