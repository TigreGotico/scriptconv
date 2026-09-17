"""Tests for the ghana-g2p-backed phonemizer.

ghana-g2p is in the ``test`` extra, so these tests call the real library.
The expected strings are ghana-g2p 0.1.1 output. ``Akwaaba`` / ``a kʷ a a b a``
is also the example in ghana-g2p's own README.
"""
import unittest

from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer_class
from scriptconv.phonemizers.ghana import GhanaG2PPhonemizer


class TestGhanaG2PPhonemizer(unittest.TestCase):
    def test_twi_ipa(self):
        p = GhanaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kʷ a a b a")

    def test_twi_native_units(self):
        p = GhanaG2PPhonemizer(alphabet=Alphabet.AFRICA_G2P)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kw a a b a")

    def test_ewe_y_is_the_palatal_glide(self):
        # ghana-g2p corrects africa-g2p's Ewe <y>, once IPA y, to /j/.
        p = GhanaG2PPhonemizer()
        self.assertEqual(p.phonemize_string("yaa", "ewe"), "j a a")

    def test_dagbani_long_vowel(self):
        p = GhanaG2PPhonemizer()
        self.assertEqual(p.phonemize_string("Naawuni", "dag"), "n aː w u n i")

    def test_supported_langs_are_the_42_ghanaian_codes(self):
        langs = GhanaG2PPhonemizer.supported_langs()
        self.assertEqual(len(langs), 42)
        for code in ("twi", "ewe", "gaa", "dag", "hau"):
            self.assertIn(code, langs)

    def test_get_lang_strips_region_only(self):
        self.assertEqual(GhanaG2PPhonemizer.get_lang("twi-GH"), "twi")
        with self.assertRaises(ValueError):
            GhanaG2PPhonemizer.get_lang("ee")

    def test_engine_is_cached_per_language(self):
        p = GhanaG2PPhonemizer()
        first = p._engine("twi")
        self.assertIs(p._engine("twi"), first)

    def test_rejects_unsupported_alphabet(self):
        with self.assertRaises(ValueError):
            GhanaG2PPhonemizer(alphabet=Alphabet.VOSK)

    def test_registry_resolves_the_member(self):
        self.assertIs(get_phonemizer_class(Phonemizer.GHANA_G2P), GhanaG2PPhonemizer)


if __name__ == "__main__":
    unittest.main()
