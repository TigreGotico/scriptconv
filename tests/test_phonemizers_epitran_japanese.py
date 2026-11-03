"""Epitran's Japanese maps are named as the installed epitran names them.

epitran 1.26.1 renamed its Japanese maps from ``jpn-Ktkn``/``jpn-Hrgn`` to
the ISO 15924 script codes ``jpn-Kana``/``jpn-Hira``.
"""
import os
import unittest

import epitran

from scriptconv.phonemizers.mul import EpitranPhonemizer

MAP_DIR = os.path.join(os.path.dirname(epitran.__file__), "data", "map")
JAPANESE = [lang for lang in EpitranPhonemizer.EPITRAN_LANGS if lang.startswith("jpn-")]


class TestEpitranJapaneseMaps(unittest.TestCase):
    def test_every_japanese_entry_names_an_installed_map(self):
        self.assertEqual(len(JAPANESE), 4)
        for lang in JAPANESE:
            with self.subTest(lang=lang):
                self.assertTrue(os.path.isfile(os.path.join(MAP_DIR, f"{lang}.csv")))

    def test_explicit_katakana_request_phonemizes(self):
        text = "コーヒー テレビ"
        expected = epitran.Epitran("jpn-Kana").transliterate(text)
        self.assertNotEqual(expected, text)
        self.assertEqual(EpitranPhonemizer().phonemize_string(text, "jpn-Kana"), expected)

    def test_explicit_hiragana_request_phonemizes(self):
        text = "わたし がくせい"
        expected = epitran.Epitran("jpn-Hira").transliterate(text)
        self.assertNotEqual(expected, text)
        self.assertEqual(EpitranPhonemizer().phonemize_string(text, "jpn-Hira"), expected)


if __name__ == "__main__":
    unittest.main()
