"""Tests for the africa-g2p-backed phonemizer.

africa-g2p is not part of the ``test`` extra (it is not yet published to
PyPI at time of writing — see the PR body), so the functional tests here
skip gracefully when the package is unavailable, following the same shape
as the CJK/Arabic backend tests in ``test_phonemizers_cjk_ar.py``. The
registry-wiring and friendly-import-error tests run unconditionally.
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

try:
    import africa_g2p  # noqa: F401
    _HAS_AFRICA_G2P = True
except ImportError:
    _HAS_AFRICA_G2P = False


@unittest.skipUnless(_HAS_AFRICA_G2P, "africa-g2p not installed")
class TestAfricaG2PPhonemizer(unittest.TestCase):
    def test_ipa_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kʷ a a b a")

    def test_native_grapheme_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.AFRICA_G2P)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kw a a b a")

    def test_engine_is_cached_per_language(self):
        p = AfricaG2PPhonemizer()
        first = p._engine("twi")
        self.assertIs(p._engine("twi"), first)

    def test_supported_langs_includes_twi(self):
        self.assertIn("twi", AfricaG2PPhonemizer.supported_langs())
        self.assertGreater(len(AfricaG2PPhonemizer.supported_langs()), 300)

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

    def test_class_resolves_or_raises_named_importerror(self):
        try:
            cls = get_phonemizer_class(Phonemizer.AFRICA_G2P)
        except ImportError as e:
            self.assertIn("scriptconv[", str(e))
        else:
            self.assertIs(cls, AfricaG2PPhonemizer)

    @unittest.skipUnless(_HAS_AFRICA_G2P, "africa-g2p not installed")
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
