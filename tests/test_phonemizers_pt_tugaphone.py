"""Tests for TugaphonePhonemizer sub-regional lect resolution.

A sub-regional lect tag such as ``pt-PT-x-lisbon`` or ``pt-PT-x-porto`` must
resolve to itself, and must phonemize distinctly from the generic country
lect and from every other sub-regional lect. A loose tag like ``pt`` must
still resolve to a default supported lect, and a non-Portuguese tag must be
rejected.
"""
import unittest

from scriptconv.phonemizers.pt import TugaphonePhonemizer


class TestTugaphoneSubregionalLects(unittest.TestCase):

    def setUp(self):
        self.pho = TugaphonePhonemizer()

    def test_subregional_lects_pass_through(self):
        self.assertEqual(TugaphonePhonemizer.get_lang("pt-PT-x-lisbon"), "pt-PT-x-lisbon")
        self.assertEqual(TugaphonePhonemizer.get_lang("pt-PT-x-porto"), "pt-PT-x-porto")

    def test_subregional_lects_produce_distinct_output(self):
        text = "O vinho verde"
        generic = self.pho.phonemize_string(text, "pt-PT")
        lisbon = self.pho.phonemize_string(text, "pt-PT-x-lisbon")
        porto = self.pho.phonemize_string(text, "pt-PT-x-porto")
        self.assertNotEqual(generic, lisbon)
        self.assertNotEqual(generic, porto)
        self.assertNotEqual(lisbon, porto)

    def test_loose_tag_still_resolves(self):
        # "pt" has no country/lect of its own; it must still resolve to a
        # default supported lect instead of raising.
        resolved = TugaphonePhonemizer.get_lang("pt")
        self.assertIn(resolved, ["pt-PT", "pt-BR", "pt-AO", "pt-MZ", "pt-TL"])

    def test_non_portuguese_still_rejected(self):
        with self.assertRaises(ValueError):
            TugaphonePhonemizer.get_lang("es")


if __name__ == "__main__":
    unittest.main()
