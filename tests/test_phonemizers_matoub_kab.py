"""The Matoub Kabyle route: it phonemizes, and it is not the africa-g2p route."""
import unittest

from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, get_phonemizer

# Measured against the reference rules in agbalu/Matoub-82M
# tokenization_matoub.py at revision 3d00056f, on 2026-09-25.
REFERENCE = {
    "taddart": "θædːærθ",
    "ameqqran": "æməqːræn",
    "azul fell awen": "æzul fəlː æwən",
    "tamurt n leqbayel": "θæmurθ n ləqβæjəl",
    "aqcic yecca aɣrum": "ɑqʃiʃ jəʃːæ ɑʁrum",
}


class TestMatoubKabyle(unittest.TestCase):
    def setUp(self):
        self.p = MatoubKabylePhonemizer()

    def test_phonemizes_real_words(self):
        for text, expected in REFERENCE.items():
            with self.subTest(text=text):
                self.assertEqual(self.p.phonemize_string(text, "kab"), expected)

    def test_the_rules_that_make_this_route_its_own(self):
        # Each assertion is one rule africa-g2p does not apply. If these ever
        # start matching africa-g2p, the two routes have been conflated.
        # spirantisation: t -> θ, b -> β, d -> ð
        self.assertEqual(self.p.phonemize_string("tamurt", "kab"), "θæmurθ")
        # gemination is length on the restored stop, not a doubled symbol
        self.assertEqual(self.p.phonemize_string("taddart", "kab"), "θædːærθ")
        self.assertNotIn("ðð", self.p.phonemize_string("taddart", "kab"))
        # /a/ backs to ɑ beside a backing consonant, and stays æ otherwise
        self.assertTrue(self.p.phonemize_string("aqcic", "kab").startswith("ɑ"))
        self.assertTrue(self.p.phonemize_string("azul", "kab").startswith("æ"))

    def test_registry_entry_resolves(self):
        self.assertIn(Phonemizer.MATOUB_KAB, PHONEMIZER_REGISTRY)
        module, name, extra = PHONEMIZER_REGISTRY[Phonemizer.MATOUB_KAB]
        self.assertEqual(name, "MatoubKabylePhonemizer")
        # no extra: the rules are vendored and need only the standard library
        self.assertIsNone(extra)
        self.assertIsInstance(get_phonemizer(Phonemizer.MATOUB_KAB),
                              MatoubKabylePhonemizer)

    def test_emits_ipa_and_chunks(self):
        self.assertEqual(self.p.alphabet, Alphabet.IPA)
        self.assertEqual(self.p.phonemize("azul", "kab"), [["æ", "z", "u", "l"]])

    def test_only_kabyle(self):
        self.assertEqual(MatoubKabylePhonemizer.supported_langs(), ["kab"])
        for other in ("eng", "fra", "ber"):
            with self.subTest(lang=other):
                with self.assertRaises(ValueError):
                    self.p.phonemize_string("azul", other)

    def test_an_unknown_character_raises_and_is_never_dropped(self):
        # The upstream file records that silent deletion cost three Kabyle
        # consonants once. A symbol with no rule must be reported.
        with self.assertRaises(ValueError):
            self.p.phonemize_string("aβc", "kab")

    def test_the_vendored_rules_need_no_third_party_import(self):
        import sys

        for module in ("transformers", "torch"):
            self.assertNotIn(module, sys.modules,
                             f"{module} must not be imported to phonemize")


if __name__ == "__main__":
    unittest.main()
