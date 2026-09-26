"""Tests for the africa-g2p-backed phonemizer.

africa-g2p is vendored (``scriptconv.phonemizers._vendored.africa_g2p``),
not an optional extra, so it is always present -- these tests never skip.
"""
import unittest

from scriptconv.phonemizers import (
    Alphabet,
    Phonemizer,
    PHONEMIZER_REGISTRY,
    get_phonemizer,
    get_phonemizer_class,
)
from scriptconv.phonemizers.africa import AfricaG2PPhonemizer


class TestAfricaG2PPhonemizer(unittest.TestCase):
    def test_ipa_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kʷ a a b a")

    def test_native_grapheme_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.AFRICA_G2P)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kw a a b a")

    def test_ethiopic_g_is_the_ipa_letter(self):
        # africa-g2p v0.2.4 fixed the Ethiopic tables, which wrote ASCII g
        # (U+0067) where IPA uses ɡ (U+0261).
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("ግብር", "amh"), "ɡɨ bɨ rɨ")
        self.assertNotIn("g", p.phonemize_string("ገና", "amh"))

    def test_kabuverdianu_reads_letters_not_letter_names(self):
        # Before v0.2.4 the kea table read letter NAMES: kasa gave
        # 'ˈkapɐ a ˈɛs(i) a'.
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("kasa", "kea"), "k a s a")
        self.assertEqual(p.phonemize_string("djuntu", "kea"), "d͡ʒ u n t u")

    def test_engine_is_cached_per_language(self):
        p = AfricaG2PPhonemizer()
        first = p._engine("twi")
        self.assertIs(p._engine("twi"), first)

    def test_supported_langs_includes_twi(self):
        self.assertIn("twi", AfricaG2PPhonemizer.supported_langs())
        self.assertGreater(len(AfricaG2PPhonemizer.supported_langs()), 300)

    def test_region_suffixed_rule_files_resolve_by_their_own_name(self):
        # 11 rule files carry a region suffix instead of a bare ISO 639-3
        # code; each must be selectable by that name (T-2701).
        for code in ("hau-nigeria", "hau-niger", "dop-benin", "ngb-zaire",
                     "sag-congo", "sef-cote_d_ivoire", "snk-senegal"):
            self.assertEqual(AfricaG2PPhonemizer.get_lang(code), code)
            self.assertIn(code, AfricaG2PPhonemizer.supported_langs())

    def test_a_region_suffixed_code_phonemizes(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("ƙasa", "hau-nigeria"),
                         "kʼ a s a")

    def test_an_underscore_is_read_as_a_hyphen(self):
        self.assertEqual(AfricaG2PPhonemizer.get_lang("HAU_NIGERIA"),
                         "hau-nigeria")

    def test_a_bare_code_with_only_region_files_still_raises(self):
        # africa-g2p ships no bare 'hau'. Choosing a region for the caller
        # would be a claim this wrapper does not make.
        self.assertNotIn("hau", AfricaG2PPhonemizer.supported_langs())
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer.get_lang("hau")

    def test_get_lang_resolves_exact_iso_639_3_code(self):
        self.assertEqual(AfricaG2PPhonemizer.get_lang("twi"), "twi")
        # region subtag is stripped to the primary subtag before lookup
        self.assertEqual(AfricaG2PPhonemizer.get_lang("twi-GH"), "twi")

    def test_get_lang_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer.get_lang("zzz")

    def test_phonemize_string_rejects_unsupported_language(self):
        p = AfricaG2PPhonemizer()
        with self.assertRaises(ValueError):
            p.phonemize_string("hello", "zzz")

    def test_phonemize_returns_sentence_lists(self):
        p = AfricaG2PPhonemizer()
        out = p.phonemize("Akwaaba.", "twi")
        self.assertEqual(len(out), 1)
        self.assertTrue(all(isinstance(s, list) for s in out))

    def test_rejects_unsupported_alphabet(self):
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer(alphabet=Alphabet.VOSK)


class TestAfricaG2PRegistration(unittest.TestCase):
    def test_registered(self):
        self.assertIn(Phonemizer.AFRICA_G2P, PHONEMIZER_REGISTRY)

    def test_class_resolves_without_any_extra(self):
        # vendored -- always resolves, never an ImportError naming an extra
        cls = get_phonemizer_class(Phonemizer.AFRICA_G2P)
        self.assertIs(cls, AfricaG2PPhonemizer)

    def test_get_phonemizer_builds_it(self):
        p = get_phonemizer(Phonemizer.AFRICA_G2P, Alphabet.IPA)
        self.assertIsInstance(p, AfricaG2PPhonemizer)

    def test_no_lang_default_registered(self):
        # design decision: africa-g2p is not made a default for any language,
        # including African languages that currently have no LANG_DEFAULTS
        # entry at all — see the PR body for the reasoning.
        from scriptconv.phonemizers import LANG_DEFAULTS
        for candidates in LANG_DEFAULTS.values():
            self.assertNotIn(Phonemizer.AFRICA_G2P, candidates)


if __name__ == "__main__":
    unittest.main()
