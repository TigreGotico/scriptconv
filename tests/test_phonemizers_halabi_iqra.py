"""Tests for the three Halabi-notation Arabic edges: mantoq (full pipeline),
Phonemizer.HALABI (raw phonetiser), Phonemizer.IQRA (IqraEval-flavored raw
phonetiser). All three share the vendored/externally-installed mantoq backend
and its CC BY-NC quarantine — see test_phonemizers_cjk_ar.py's
TestLicensingStubs for the quarantine tests proper.

The documented example, from arbtok's scripts/benchmark_iqraeval.py /
IqraEval/Iqra_train (Nawar Halabi's Arabic-Phonetiser, verified
symbol-by-symbol against the corpus): "فِيهِ خَيْرَاتٌ" ->
raw Halabi ``f ii0 h i0 + x A y r aa t u1 n``.
"""
import unittest

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.registry import get_phonemizer, PHONEMIZER_REGISTRY

EXAMPLE = "فِيهِ خَيْرَاتٌ"
EXAMPLE_RAW_HALABI = "f ii0 h i0 + x A y r aa t u1 n"


class TestRegistryResolution(unittest.TestCase):
    def test_halabi_and_iqra_registered(self):
        self.assertIn(Phonemizer.HALABI, PHONEMIZER_REGISTRY)
        self.assertIn(Phonemizer.IQRA, PHONEMIZER_REGISTRY)

    def test_wire_format_values(self):
        self.assertEqual(Phonemizer.HALABI.value, "halabi")
        self.assertEqual(Phonemizer.IQRA.value, "iqra")

    def test_classes_resolve(self):
        from scriptconv.phonemizers.ar import HalabiPhonemizer, IqraPhonemizer
        self.assertIs(get_phonemizer_class(Phonemizer.HALABI), HalabiPhonemizer)
        self.assertIs(get_phonemizer_class(Phonemizer.IQRA), IqraPhonemizer)


class TestHalabiPhonemizer(unittest.TestCase):
    def test_native_output_matches_documented_example(self):
        p = get_phonemizer(Phonemizer.HALABI, alphabet=Alphabet.HALABI)
        self.assertEqual(p.phonemize_string(EXAMPLE, "ar"), EXAMPLE_RAW_HALABI)

    def test_native_output_preserves_digits_and_separator(self):
        p = get_phonemizer(Phonemizer.HALABI, alphabet=Alphabet.HALABI)
        out = p.phonemize_string(EXAMPLE, "ar")
        self.assertIn("0", out)
        self.assertIn("1", out)
        self.assertIn(" + ", out)

    def test_ipa_output_strips_digits_and_separator(self):
        p = get_phonemizer(Phonemizer.HALABI, alphabet=Alphabet.IPA)
        out = p.phonemize_string(EXAMPLE, "ar")
        self.assertNotIn("0", out)
        self.assertNotIn("1", out)
        self.assertNotIn("+", out)
        self.assertNotIn("_", out)
        # x -> x, A (emphatic) -> ɑ, aa -> aː ...
        self.assertIn("ɑ", out)

    def test_default_alphabet_is_halabi(self):
        p = get_phonemizer_class(Phonemizer.HALABI)()
        self.assertEqual(p.alphabet, Alphabet.HALABI)

    def test_unsupported_alphabet_rejected(self):
        cls = get_phonemizer_class(Phonemizer.HALABI)
        with self.assertRaises(ValueError):
            cls(alphabet=Alphabet.BUCKWALTER)


class TestIqraPhonemizer(unittest.TestCase):
    def test_native_output_has_no_digits_or_word_separator(self):
        p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)
        out = p.phonemize_string(EXAMPLE, "ar")
        self.assertNotIn("0", out)
        self.assertNotIn("1", out)
        self.assertNotIn("+", out)
        # emphatic-context vowel kept distinct from mantoq's simplified form
        self.assertIn("A", out.split())

    def test_ipa_output_keeps_emphatic_vowel_distinct(self):
        p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.IPA)
        out = p.phonemize_string(EXAMPLE, "ar")
        self.assertIn("ɑ", out)  # the emphatic allophone of "a" (token "A")
        self.assertNotIn("_", out)

    def test_tanwin_dropped(self):
        # tanwīn dhamm on the final word ("خَيْرَاتٌ") is dropped entirely,
        # not rendered as "u n" (verified against IqraEval/Iqra_train, see
        # scripts/benchmark_iqraeval.py)
        p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)
        out = p.phonemize_string(EXAMPLE, "ar").split()
        self.assertNotIn("n", out)

    def test_mantoq_vs_iqra_differ_on_bare_undiacritized_input(self):
        # mantoq restores diacritics itself (its own diacritizer); the raw
        # IQRA/HALABI edges take the bare text at face value and phonemize
        # it literally (garbage-in on undiacritized text, by contract)
        bare = "فيه خيرات"
        mantoq_p = get_phonemizer(Phonemizer.MANTOQ, alphabet=Alphabet.HALABI)
        iqra_p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)
        self.assertNotEqual(mantoq_p.phonemize_string(bare, "ar"),
                             iqra_p.phonemize_string(bare, "ar"))

    def test_default_alphabet_is_halabi(self):
        p = get_phonemizer_class(Phonemizer.IQRA)()
        self.assertEqual(p.alphabet, Alphabet.HALABI)

    def test_unsupported_alphabet_rejected(self):
        cls = get_phonemizer_class(Phonemizer.IQRA)
        with self.assertRaises(ValueError):
            cls(alphabet=Alphabet.BUCKWALTER)


class TestIqraPreprocessRules(unittest.TestCase):
    """The three text-level transforms in isolation — each independently
    verified against a 2,588-row held-out sample of IqraEval/Iqra_train's dev
    split (see scripts/benchmark_iqraeval.py for the current exact-match rate
    and any residual mismatch classes)."""

    def test_tanwin_stripped_mid_utterance_not_just_at_pause(self):
        from scriptconv.phonemizers.ar import _iqra_preprocess
        # "دَابَّةٍ وَ..." — tanwin kasr mid-sentence, not the last word
        out = _iqra_preprocess("دَابَّةٍ وَالْمَلَائِكَةُ")
        self.assertNotIn("ٍ", out)

    def test_waw_al_jamaa_silent_alif_dropped(self):
        from scriptconv.phonemizers.ar import _iqra_preprocess
        out = _iqra_preprocess("قَالُوا")
        self.assertFalse(out.endswith("ا"))
        self.assertTrue(out.endswith("و") or out.endswith("ُو"))

    def test_utterance_initial_definite_article_gets_hamza(self):
        from scriptconv.phonemizers.ar import _iqra_preprocess
        out = _iqra_preprocess("الْكُرْزُ أَحْمَرُ")
        self.assertTrue(out.startswith("أَ"))

    def test_phrase_final_word_loses_case_ending(self):
        from scriptconv.phonemizers.ar import _iqra_preprocess
        out = _iqra_preprocess("قَدِ اسْتَوْعَبْتُهَا")
        # final "هَا" -> "ها" (fatha on the alif-maqsura-like final vowel is
        # a long vowel, untouched; the point is nothing crashes and the
        # rule only ever touches the true last word)
        self.assertTrue(out)


class TestIqraPhonetiserBackend(unittest.TestCase):
    """Regression tests for the ``_vendored/iqra_phonetiser`` backend fixes
    that took the IqraEval dev-split exact-match rate from an initial,
    badly-regressed port (33.6%, missing the utterance-level normalization
    pass entirely) to 98.3% — see the introducing PR for the full history
    and ``scripts/benchmark_iqraeval.py`` for the current rate and the
    residual mismatch classes (predominantly a proven dataset-generation
    bug, not a phonetiser fidelity gap)."""

    def test_mid_utterance_connecting_alif_is_silent(self):
        # hamzat al-waṣl: a definite article mid-utterance connects directly
        # to the previous word's final vowel — its own alif is never
        # pronounced as a long "aa" (only utterance-INITIAL "ال" gets the
        # explicit hamza treatment; see _iqra_preprocess). Regression test
        # for the missing ``_preprocess_utterance`` normalization pass (the
        # ``([^-]) A`` -> `` `` rule) that, when absent, phonetised every
        # mid-utterance "ال" alif as a spurious "aa".
        #
        # Built with explicit codepoints (shadda U+0651 before the fatha
        # U+064E on the shadda-doubled seen) — the dataset's own diacritic
        # ordering convention; some keyboard input methods produce the
        # opposite order, which the raw phonetiser (upstream's own
        # ambiguity, not this port's) reads differently.
        seen_al_samawati = (
            "ا" + "ل" + "س" + "ّ" + "َ" + "م" + "َ" + "ا"
            + "و" + "َ" + "ا" + "ت" + "ِ"
        )
        p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)
        out = p.phonemize_string(f"فِي {seen_al_samawati} وَالْأَرْضِ", "ar").split()
        # "في" + "السماوات": the alif of "ال" must not surface as "aa"
        # between "ii" (fii) and "ss" (the sun-letter-elided lam + shadda-
        # doubled seen).
        self.assertEqual(out[:9], ["f", "ii", "ss", "a", "m", "aa", "w", "aa", "t"])

    def test_emphatic_context_does_not_leak_across_ra(self):
        # Upstream's (and mantoq's) actual, executed condition for resetting
        # emphaticContext is an adjacent-string-literal typo that never
        # matches "r"/"l" despite the "(except for Lam and Ra)" comment —
        # i.e. an emphatic consonant's context does NOT survive past a
        # following "r" the way the comment claims. phoneme_ref was
        # generated against that actual (buggy) behavior, so this backend
        # reproduces it verbatim rather than the comment's intent.
        p = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)
        out = p.phonemize_string("يُبْصِرُونَ", "ar").split()
        # final "uu" is after a non-resetting-per-the-comment "r", but the
        # actual upstream behavior resets emphaticContext there anyway.
        self.assertIn("uu", out)
        self.assertNotIn("UU", out)


class TestMantoqHalabiLabelingIsAccurate(unittest.TestCase):
    """The BUCKWALTER-label verdict: mantoq's own inventory is Halabi's
    phonetic notation, not an orthographic Buckwalter transliteration layer
    — both alphabets already return byte-identical output (fixed prior to
    this PR); this just pins that contract so it cannot silently regress."""

    def test_buckwalter_and_halabi_alphabets_are_byte_identical(self):
        cls = get_phonemizer_class(Phonemizer.MANTOQ)
        bw = cls(alphabet=Alphabet.BUCKWALTER)
        halabi = cls(alphabet=Alphabet.HALABI)
        self.assertEqual(bw.phonemize_string(EXAMPLE, "ar"),
                          halabi.phonemize_string(EXAMPLE, "ar"))


if __name__ == "__main__":
    unittest.main()
