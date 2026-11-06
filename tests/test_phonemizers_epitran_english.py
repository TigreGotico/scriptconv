"""Epitran reads English through ``lex_lookup`` from Flite.

When the binary is missing, epitran logs a warning, converts an empty ARPAbet
string and raises ``KeyError: ''``. The phonemizer names the missing binary
before it calls epitran.
"""
import shutil
import unittest
from unittest import mock

from scriptconv.phonemizers.mul import EpitranPhonemizer

_which = shutil.which


def _without_lex_lookup(name, *args, **kwargs):
    return None if name == "lex_lookup" else _which(name, *args, **kwargs)


class TestEpitranEnglishNeedsFlite(unittest.TestCase):
    def test_english_without_lex_lookup_names_the_missing_binary(self):
        with mock.patch("shutil.which", _without_lex_lookup):
            for lang in ("en", "en-US", "eng-Latn"):
                with self.subTest(lang=lang):
                    with self.assertRaises(RuntimeError) as cm:
                        EpitranPhonemizer().phonemize_string("hello world", lang)
                    self.assertIn("lex_lookup", str(cm.exception))

    def test_other_languages_do_not_need_lex_lookup(self):
        with mock.patch("shutil.which", _without_lex_lookup):
            self.assertEqual(
                EpitranPhonemizer().phonemize_string("casa", "spa-Latn"), "kasa")


if __name__ == "__main__":
    unittest.main()
