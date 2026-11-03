"""Epitran's map list matches the maps the installed epitran ships.

epitran 1.26.1 renamed its Japanese maps from ``jpn-Ktkn``/``jpn-Hrgn`` to
the ISO 15924 script codes ``jpn-Kana``/``jpn-Hira``. The Japanese maps
convert kana only, so a Japanese request must name a kana script.
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


class TestEpitranJapaneseScript(unittest.TestCase):
    def test_japanese_without_kana_script_raises(self):
        for tag in ["ja", "ja-JP", "jpn", "ja-Jpan", "ja_JP"]:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    EpitranPhonemizer.get_lang(tag)

    def test_mixed_japanese_text_raises(self):
        with self.assertRaises(ValueError):
            EpitranPhonemizer().phonemize_string("今日は東京でコーヒーを飲みました。", "ja")

    def test_kana_script_request_gets_the_full_map(self):
        self.assertEqual(EpitranPhonemizer.get_lang("ja-Kana"), "jpn-Kana")
        self.assertEqual(EpitranPhonemizer.get_lang("ja-Hira"), "jpn-Hira")


class TestEpitranMapFiles(unittest.TestCase):
    def test_every_entry_has_a_map_file(self):
        # eng-Latn goes through Flite and has no map file
        for lang in EpitranPhonemizer.EPITRAN_LANGS:
            if lang == "eng-Latn":
                continue
            with self.subTest(lang=lang):
                self.assertTrue(os.path.isfile(os.path.join(MAP_DIR, f"{lang}.csv")))


if __name__ == "__main__":
    unittest.main()
