"""ARPABET stress preservation (stress=True) — reversible by construction."""
import random
import unittest

from scriptconv.notation import _ARPA_BASE, _ARPA_VOWELS, arpa_to_ipa, ipa_to_arpa


class TestStressForward(unittest.TestCase):
    def test_marks_placed_before_stressed_vowel(self):
        self.assertEqual(arpa_to_ipa("HH AH0 L OW1", stress=True), "həlˈoʊ")
        self.assertEqual(arpa_to_ipa("K AE1 T", stress=True), "kˈæt")
        self.assertEqual(arpa_to_ipa("AH2", stress=True), "ˌʌ")

    def test_unstressed_and_consonants_unmarked(self):
        self.assertEqual(arpa_to_ipa("AH0", stress=True), "ə")
        self.assertEqual(arpa_to_ipa("K T", stress=True), "kt")

    def test_default_still_strips(self):
        self.assertEqual(arpa_to_ipa("HH AH0 L OW1"), "həloʊ")

    def test_unknown_token_never_gets_a_mark(self):
        self.assertEqual(arpa_to_ipa("ZZ1", stress=True), "ZZ1")


class TestStressReverse(unittest.TestCase):
    def test_marks_become_digits_unmarked_vowels_get_zero(self):
        self.assertEqual(ipa_to_arpa("həlˈoʊ", stress=True), "HH AH0 L OW1")
        self.assertEqual(ipa_to_arpa("kˈæt", stress=True), "K AE1 T")
        self.assertEqual(ipa_to_arpa("ˌʌ", stress=True), "AH2")

    def test_schwa_spelled_ah0_like_cmudict(self):
        self.assertEqual(ipa_to_arpa("ə", stress=True), "AH0")

    def test_default_still_drops_marks(self):
        self.assertEqual(ipa_to_arpa("həlˈoʊ"), "HH AX L OW")


class TestRoundTrip(unittest.TestCase):
    def test_readme_example_exact(self):
        x = "HH AH0 L OW1"
        self.assertEqual(ipa_to_arpa(arpa_to_ipa(x, stress=True), stress=True), x)

    def test_property_cmudict_legal_sequences(self):
        """Random CMUdict-legal sequences round-trip exactly up to
        IPA-equivalence: token sequences whose IPA concatenation is identical
        (r-colored schwa, affricates, diphthong fusion — contiguous IPA has
        no token boundary) may normalize to the fused spelling, and that
        spelling must itself be IPA-stable.  The overwhelming majority
        round-trip byte-exactly."""
        random.seed(20260721)
        cons = [c for c in _ARPA_BASE
                if c not in _ARPA_VOWELS and c not in ("AX", "AXR")]
        vows = [v for v in _ARPA_VOWELS if v not in ("AX", "AXR")]
        exact = fused = 0
        for _ in range(400):
            seq = []
            for _ in range(random.randint(1, 7)):
                if random.random() < 0.5:
                    seq.append(random.choice(cons))
                else:
                    seq.append(random.choice(vows) + random.choice("012"))
            s = " ".join(seq)
            ipa = arpa_to_ipa(s, stress=True)
            rt = ipa_to_arpa(ipa, stress=True)
            if rt == s:
                exact += 1
            else:
                fused += 1
                # fusion residue must be IPA-stable
                self.assertEqual(arpa_to_ipa(rt, stress=True), ipa, s)
        self.assertGreater(exact, 350)
        self.assertLess(fused, 50)

    def test_documented_residues(self):
        # extended-ARPABET AX normalizes to CMUdict's AH0 spelling
        self.assertEqual(
            ipa_to_arpa(arpa_to_ipa("AX", stress=True), stress=True), "AH0")
        # schwa+R fuses to the r-colored vowel; stable from the IPA side
        fused = ipa_to_arpa(arpa_to_ipa("AH0 R", stress=True), stress=True)
        self.assertEqual(fused, "AXR0")
        # affricate fusion exists in default mode too (contiguous IPA)
        self.assertEqual(ipa_to_arpa(arpa_to_ipa("T SH")), "CH")
        self.assertEqual(arpa_to_ipa(fused, stress=True),
                         arpa_to_ipa("AH0 R", stress=True))


if __name__ == "__main__":
    unittest.main()


class TestEnglishInputAliases(unittest.TestCase):
    """British/phonetic-detail IPA symbols accepted on ARPA input."""

    def test_rhotic_approximant(self):
        from scriptconv import ipa_to_arpa
        self.assertEqual(ipa_to_arpa("ɹ"), "R")
        self.assertEqual(ipa_to_arpa("maɪkɹɑft"), "M AY K R AA F T")

    def test_british_goat_diphthong(self):
        from scriptconv import ipa_to_arpa
        self.assertEqual(ipa_to_arpa("əʊ"), "OW")

    def test_british_lot_vowel(self):
        from scriptconv import ipa_to_arpa
        self.assertEqual(ipa_to_arpa("ɒ"), "AA")

    def test_canonical_round_trip_unchanged(self):
        from scriptconv import arpa_to_ipa, ipa_to_arpa
        self.assertEqual(ipa_to_arpa(arpa_to_ipa("OW")), "OW")
        self.assertEqual(ipa_to_arpa(arpa_to_ipa("R")), "R")
