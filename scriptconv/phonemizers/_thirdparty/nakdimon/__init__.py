"""Hebrew niqqud from the Nakdimon ONNX model.

Nakdimon (Gershuni and Pinter, "Restoring Hebrew Diacritics Without a
Dictionary", Findings of NAACL 2022) predicts, for each letter, a vowel
point, a dagesh and a shin or sin dot.

Adapted from https://github.com/elazarg/nakdimon at commit
5b73cdd6a43ad465faabc8c1118933592df356c8, Copyright 2022 Elazar Gershuni,
under the MIT License (the ``LICENSE`` file in this directory). The character
tables, :func:`normalize`, :func:`remove_niqqud` and the ``can_*`` tests come
from ``nakdimon/hebrew.py``. :class:`CharacterTable` and the four tables come
from ``nakdimon/dataset.py``, and the loop of :meth:`Nakdimon.predict` that
writes the marks is ``merge`` of the same file. Unlike ``predict`` in
``nakdimon/predict.py``, the model reads the whole text as one sequence, with
no padding and no split into lines.
"""
import re

import numpy as np

__all__ = ["Nakdimon", "remove_niqqud"]

# nakdimon/hebrew.py

# "rafe" denotes a letter to which it would have been valid to add a diacritic of some category
# but instead it is decided not to. This makes the metrics less biased.
RAFE = '\u05BF'

HEBREW_LETTERS = [chr(c) for c in range(0x05d0, 0x05ea + 1)]

NIQQUD = [RAFE] + [chr(c) for c in range(0x05b0, 0x05bc + 1)] + ['\u05b7']

SHIN_YEMANIT = '\u05c1'
SHIN_SMALIT = '\u05c2'
NIQQUD_SIN = [RAFE, SHIN_YEMANIT, SHIN_SMALIT]  # RAFE is for acronyms

DAGESH_LETTER = '\u05bc'
DAGESH = [RAFE, DAGESH_LETTER]  # note that DAGESH and SHURUK are one and the same

VALID_LETTERS = [' ', '!', '"', "'", '(', ')', ',', '-', '.', ':', ';', '?'] + HEBREW_LETTERS
SPECIAL_TOKENS = ['H', 'O', '5']

ENDINGS_TO_REGULAR = dict(zip('ךםןףץ', 'כמנפצ', strict=True))


def normalize(c):
    if c in VALID_LETTERS:
        return c
    if c in ENDINGS_TO_REGULAR:
        return ENDINGS_TO_REGULAR[c]
    if c in ['\n', '\t']:
        return ' '
    if c in ['־', '‒', '–', '—', '―', '−']:
        return '-'
    if c == '[':
        return '('
    if c == ']':
        return ')'
    if c in ['´', '‘', '’']:
        return "'"
    if c in ['“', '”', '״']:
        return '"'
    if c.isdigit():
        return '5'
    if c == '…':
        return ','
    if c in ['ײ', 'װ', 'ױ']:
        return 'H'
    return 'O'


def can_dagesh(letter):
    return letter in ('בגדהוזטיכלמנספצקשת' + 'ךף')


def can_sin(letter):
    return letter == 'ש'


def can_niqqud(letter):
    return letter in ('אבגדהוזחטיכלמנסעפצקרשת' + 'ךן')


def remove_niqqud(text: str) -> str:
    return re.sub('[\u05B0-\u05BC\u05C1\u05C2ׇ\u05c7\u05BF]', '', text)


# nakdimon/dataset.py

class CharacterTable:
    MASK_TOKEN = ''

    def __init__(self, chars: list[str]) -> None:
        self.chars = [CharacterTable.MASK_TOKEN] + chars
        self.char_indices = dict((c, i) for i, c in enumerate(self.chars))
        self.indices_char = dict((i, c) for i, c in enumerate(self.chars))


letters_table = CharacterTable(SPECIAL_TOKENS + VALID_LETTERS)
dagesh_table = CharacterTable(DAGESH)
sin_table = CharacterTable(NIQQUD_SIN)
niqqud_table = CharacterTable(NIQQUD)


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

    def predict(self, text: str) -> str:
        """*text* with niqqud. The model reads the letters without the marks they had."""
        ts = remove_niqqud(text)
        if not ts:
            return ts
        x = np.array([[letters_table.char_indices[normalize(c)] for c in ts]], dtype=self._input_type)
        nss, dss, sss = self.session.run(None, {self._input_name: x})
        sentence = []
        for t, n, d, s in zip(ts, nss[0].argmax(-1), dss[0].argmax(-1), sss[0].argmax(-1), strict=True):
            sentence.append(t)
            if can_dagesh(t):
                sentence.append(dagesh_table.indices_char[d].replace(RAFE, ''))
            if can_sin(t):
                sentence.append(sin_table.indices_char[s].replace(RAFE, ''))
            if can_niqqud(t):
                sentence.append(niqqud_table.indices_char[n].replace(RAFE, ''))
        return ''.join(sentence)
