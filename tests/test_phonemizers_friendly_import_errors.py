"""Pins the friendly-ImportError convention for the lazy backend imports
inside phonemizer wrappers.

``get_phonemizer_class`` (see ``registry.py``) already raises a friendly,
extra-naming ``ImportError`` when the wrapper *module itself* fails to
import.  That does not cover the far more common case: the wrapper module
imports fine (the backend package is only imported lazily, inside
``__init__``/a method), and it is that inner, lazy import that fails when
the backend is missing.  Every wrapper must catch that inner failure and
re-raise a friendly ``ImportError`` naming the pip extra — never let a bare
``ModuleNotFoundError``/``ImportError`` escape.

This test forces each wrapper's lazy import to fail (by shadowing the
backend module in ``sys.modules`` with ``None``, which makes the ``import``
statement raise ``ImportError`` regardless of whether the package is
actually installed) and asserts the resulting exception is an
``ImportError`` whose message contains an install instruction. No optional
backend needs to be installed to run this, and nothing is skipped.
"""
import sys
import unittest
from unittest.mock import patch

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class


def _trigger_construct(cls):
    cls()


def _trigger_gruut(cls):
    p = cls()
    list(p._text_to_phonemes("hi", "en"))


def _trigger_misaki_en(cls):
    p = cls()
    p._get_phonemizer("en-US")


def _trigger_jieba(cls):
    p = cls()
    p.phonemize_string("你好", "zh")


# member -> (module name to blank out in sys.modules, how to trigger the
# lazy import that consumes it)
CASES = {
    Phonemizer.MISAKI: ("misaki", _trigger_misaki_en),
    Phonemizer.MISAKI_EN: ("misaki", _trigger_misaki_en),
    Phonemizer.GRUUT: ("gruut", _trigger_gruut),
    Phonemizer.GORUUT: ("pygoruut", _trigger_construct),
    Phonemizer.EPITRAN: ("epitran", _trigger_construct),
    Phonemizer.TRANSPHONE: ("transphone", _trigger_construct),
    Phonemizer.DEEPPHONEMIZER: ("dp", _trigger_construct),
    Phonemizer.OPENPHONEMIZER: ("openphonemizer", _trigger_construct),
    Phonemizer.G2PEN: ("nltk", _trigger_construct),
    Phonemizer.TUGAPHONE: ("tugaphone", _trigger_construct),
    Phonemizer.CUTLET: ("cutlet", _trigger_construct),
    Phonemizer.PYKAKASI: ("pykakasi", _trigger_construct),
    Phonemizer.VIPHONEME: ("viphoneme", _trigger_construct),
    Phonemizer.G2PK: ("g2pk", _trigger_construct),
    Phonemizer.JIEBA: ("jieba", _trigger_jieba),
}


class TestLazyBackendImportsAreFriendly(unittest.TestCase):
    def test_all_documented_backends_covered(self):
        # keeps this test list honest if a new Phonemizer member is added
        # backed by one of the wrapper modules touched by this convention
        self.assertEqual(len(CASES), 15)

    def _assert_friendly(self, member):
        module_name, trigger = CASES[member]
        cls = get_phonemizer_class(member)
        with patch.dict(sys.modules, {module_name: None}):
            with self.assertRaises(ImportError, msg=member) as ctx:
                trigger(cls)
        msg = str(ctx.exception)
        self.assertIn("pip install", msg, member)

    def test_misaki(self):
        self._assert_friendly(Phonemizer.MISAKI)

    def test_misaki_en(self):
        self._assert_friendly(Phonemizer.MISAKI_EN)

    def test_gruut(self):
        self._assert_friendly(Phonemizer.GRUUT)

    def test_goruut(self):
        self._assert_friendly(Phonemizer.GORUUT)

    def test_epitran(self):
        self._assert_friendly(Phonemizer.EPITRAN)

    def test_transphone(self):
        self._assert_friendly(Phonemizer.TRANSPHONE)

    def test_deepphonemizer(self):
        self._assert_friendly(Phonemizer.DEEPPHONEMIZER)

    def test_openphonemizer(self):
        self._assert_friendly(Phonemizer.OPENPHONEMIZER)

    def test_g2pen(self):
        self._assert_friendly(Phonemizer.G2PEN)

    def test_tugaphone(self):
        self._assert_friendly(Phonemizer.TUGAPHONE)

    def test_cutlet(self):
        self._assert_friendly(Phonemizer.CUTLET)

    def test_pykakasi(self):
        self._assert_friendly(Phonemizer.PYKAKASI)

    def test_viphoneme(self):
        self._assert_friendly(Phonemizer.VIPHONEME)

    def test_g2pk(self):
        self._assert_friendly(Phonemizer.G2PK)

    def test_jieba(self):
        self._assert_friendly(Phonemizer.JIEBA)


if __name__ == "__main__":
    unittest.main()
