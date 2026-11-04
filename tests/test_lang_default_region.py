"""Language matching follows the default-region rule.

A bare tag means the region where the language first appeared and is still
spoken: ``en`` is British English and ``pt`` is European Portuguese.
"""
import unittest

from scriptconv.phonemizers import BasePhonemizer
from scriptconv.phonemizers.mul import (CharsiuPhonemizer, EspeakPhonemizer, GoruutPhonemizer,
                                        MisakiEnPhonemizer, TransphonePhonemizer)
from scriptconv.phonemizers.pt import TugaphonePhonemizer


class TestMatchLangDefaultRegion(unittest.TestCase):
    def test_bare_en_picks_british_english(self):
        self.assertEqual(BasePhonemizer.match_lang("en", ["en-US", "en-GB"]), "en-GB")

    def test_bare_pt_picks_european_portuguese(self):
        self.assertEqual(BasePhonemizer.match_lang("pt", ["pt-BR", "pt-PT"]), "pt-PT")

    def test_regional_request_keeps_its_region(self):
        self.assertEqual(BasePhonemizer.match_lang("en-US", ["en-GB", "en-US"]), "en-US")
        self.assertEqual(BasePhonemizer.match_lang("pt-BR", ["pt-PT", "pt-BR"]), "pt-BR")

    def test_unparseable_entry_is_measured_by_its_language(self):
        # "nar" is not a valid variant subtag, so the entry is not a valid tag
        self.assertEqual(BasePhonemizer.match_lang("de", ["en", "deu-Latn-nar"]),
                         "deu-Latn-nar")


class TestPhonemizerDefaultRegion(unittest.TestCase):
    def test_tugaphone_bare_pt_is_european(self):
        self.assertEqual(TugaphonePhonemizer.get_lang("pt"), "pt-PT")

    def test_misaki_bare_en_is_british(self):
        self.assertEqual(MisakiEnPhonemizer.get_lang("en"), "en-GB")

    def test_espeak_bare_en_is_british(self):
        self.assertEqual(EspeakPhonemizer.get_lang("en"), "en-gb")


class TestHongKongCantonese(unittest.TestCase):
    """Hong Kong and Macau tags reach each backend's Cantonese entry.

    A bare ``yue`` is mainland Cantonese in Simplified script, so these tags
    are far from it by language distance. The Cantonese data of Charsiu
    (``dicts/yue.tsv``, from ipa-dict and WikiPron ``yue_hani``) and of Goruut
    (``dicts/cantonese/language.json``) is written in Traditional script, the
    script of Hong Kong and Macau.
    """
    TAGS = ["yue-HK", "yue-Hant", "yue-MO", "yue-Hant-HK", "zh-HK", "zh-MO",
            "zh-Hant-HK", "zh-Hant-MO", "yue_HK", "ZH-hk"]

    def test_charsiu(self):
        self.assertIn("yue", CharsiuPhonemizer.BYT5_LANGS)
        for tag in self.TAGS:
            with self.subTest(tag=tag):
                self.assertEqual(CharsiuPhonemizer.get_lang(tag), "yue")

    def test_goruut(self):
        cantonese = GoruutPhonemizer.ISO639["yue"]
        for tag in self.TAGS:
            with self.subTest(tag=tag):
                self.assertEqual(GoruutPhonemizer.get_lang(tag), cantonese)

    def test_transphone(self):
        self.assertIn("yue", TransphonePhonemizer.TRANSPHONE_LANGS)
        for tag in self.TAGS:
            with self.subTest(tag=tag):
                self.assertEqual(TransphonePhonemizer.get_lang(tag), "yue")

    def test_espeak(self):
        self.assertIn("yue", EspeakPhonemizer.ESPEAK_LANGS)
        for tag in ["zh-HK", "zh-MO", "zh-Hant-HK", "zh-Hant-MO", "yue-HK"]:
            with self.subTest(tag=tag):
                self.assertEqual(EspeakPhonemizer.get_lang(tag), "yue")

    def test_taiwan_stays_mandarin(self):
        for tag in ["zh-TW", "zh-Hant", "zh-Hant-TW"]:
            with self.subTest(tag=tag):
                self.assertEqual(EspeakPhonemizer.get_lang(tag), "cmn")


if __name__ == "__main__":
    unittest.main()
