"""Language matching follows the default-region rule.

A bare tag means the region where the language first appeared and is still
spoken: ``en`` is British English and ``pt`` is European Portuguese.
"""
import unittest

from scriptconv.phonemizers import BasePhonemizer
from scriptconv.phonemizers.mul import EspeakPhonemizer, MisakiEnPhonemizer
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


if __name__ == "__main__":
    unittest.main()
