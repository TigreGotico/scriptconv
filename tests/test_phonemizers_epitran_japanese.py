"""Epitran's map list matches the maps the installed epitran ships.

epitran 1.26.1 renamed its Japanese maps from ``jpn-Ktkn``/``jpn-Hrgn`` to
the ISO 15924 script codes ``jpn-Kana``/``jpn-Hira``. The Japanese maps
convert one kana script each, so a Japanese request must name Kana or Hira.
Gothic goes through ``got-Latn`` only, because ``got-Goth`` outputs Latin
letters, not IPA.
A language request gets the full map, not the reduced ``-red`` map.
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

    def test_mixed_kana_request_raises(self):
        for tag in ["ja-Hrkt", "jpn-Hrkt", "ja-Hrkt-JP"]:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    EpitranPhonemizer.get_lang(tag)
        with self.assertRaises(ValueError):
            EpitranPhonemizer().phonemize_string("わたしは コーヒーを のみます", "ja-Hrkt")

    def test_kana_script_request_gets_the_full_map(self):
        self.assertEqual(EpitranPhonemizer.get_lang("ja-Kana"), "jpn-Kana")
        self.assertEqual(EpitranPhonemizer.get_lang("ja-Hira"), "jpn-Hira")


class TestEpitranGothic(unittest.TestCase):
    def test_gothic_script_request_raises(self):
        for tag in ["got", "got-Goth"]:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    EpitranPhonemizer.get_lang(tag)

    def test_latin_gothic_request_gives_ipa(self):
        self.assertEqual(EpitranPhonemizer.get_lang("got-Latn"), "got-Latn")
        # thorn is a Latin letter; the IPA for it is the dental fricative
        self.assertEqual(EpitranPhonemizer().phonemize_string("þu", "got-Latn"), "θu")


class TestEpitranMapFiles(unittest.TestCase):
    def test_every_entry_has_a_map_file(self):
        # eng-Latn goes through Flite and has no map file
        for lang in EpitranPhonemizer.EPITRAN_LANGS:
            if lang == "eng-Latn":
                continue
            with self.subTest(lang=lang):
                self.assertTrue(os.path.isfile(os.path.join(MAP_DIR, f"{lang}.csv")))


class TestEpitranReducedMaps(unittest.TestCase):
    def test_full_map_is_listed_before_its_reduced_map(self):
        langs = EpitranPhonemizer.EPITRAN_LANGS
        for reduced in [lang for lang in langs if lang.endswith("-red")]:
            full = reduced[:-len("-red")]
            if full in langs:
                with self.subTest(full=full):
                    self.assertLess(langs.index(full), langs.index(reduced))

    def test_language_request_gets_the_full_map(self):
        expected = {
            "bn": "ben-Beng", "ben": "ben-Beng", "bn-BD": "ben-Beng",
            "ti": "tir-Ethi", "tir": "tir-Ethi", "ti-ER": "tir-Ethi",
            "tl": "tgl-Latn", "tgl": "tgl-Latn", "tl-PH": "tgl-Latn",
            "sw": "swa-Latn", "swa": "swa-Latn", "sw-KE": "swa-Latn",
            "kmr": "kmr-Latn", "ku": "kmr-Latn", "kmr-TR": "kmr-Latn",
        }
        for tag, lang in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(EpitranPhonemizer.get_lang(tag), lang)


if __name__ == "__main__":
    unittest.main()
