"""The orthography2ipa phonemizer enables the packaged o2i-lexicons by default.

The expected IPA is read from the o2i-lexicons data file, not from engine
output. orthography2ipa keeps lexicons process-wide, so every test starts and
ends with ``clear_lexicons()``.
"""
import unittest

import orthography2ipa
from o2i_lexicons import DATA_DIR

from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer

STRESS = str.maketrans("", "", "ˈˌ")


def lexicon_ipa(code: str, word: str) -> str:
    """The IPA that the packaged TSV file for *code* lists for *word*."""
    for path in sorted((DATA_DIR / code).glob("*.tsv")):
        for line in path.read_text(encoding="utf-8").splitlines():
            entry, _, ipa = line.partition("\t")
            if entry == word:
                return ipa
    raise LookupError(f"{word!r} is not in the packaged {code} lexicon")


class TestPackagedLexicons(unittest.TestCase):
    def setUp(self):
        orthography2ipa.clear_lexicons()

    def tearDown(self):
        orthography2ipa.clear_lexicons()

    def test_default_uses_the_packaged_lexicon(self):
        expected = lexicon_ipa("en-GB", "yacht")
        out = Orthography2IPAPhonemizer().phonemize_string("yacht", "en-GB")
        self.assertEqual(out.translate(STRESS), expected)

    def test_bare_english_tag_uses_the_packaged_lexicon(self):
        expected = lexicon_ipa("en-GB", "yacht")
        out = Orthography2IPAPhonemizer().phonemize_string("yacht", "en")
        self.assertEqual(out.translate(STRESS), expected)

    def test_off_equals_plain_orthography2ipa(self):
        out = Orthography2IPAPhonemizer(packaged_lexicons=False) \
            .phonemize_string("yacht", "en-GB")
        self.assertEqual(out, orthography2ipa.G2P("en-GB").transcribe("yacht"))
        self.assertNotEqual(out.translate(STRESS), lexicon_ipa("en-GB", "yacht"))
        self.assertEqual(orthography2ipa.available_lexicon_codes(), [])

    def test_enables_only_the_languages_it_transcribes(self):
        Orthography2IPAPhonemizer().phonemize_string("yacht", "en-GB")
        self.assertEqual(orthography2ipa.available_lexicon_codes(), ["en-GB"])

    def test_language_without_a_packaged_lexicon_uses_the_rules(self):
        out = Orthography2IPAPhonemizer().phonemize_string("Kaixo", "eu")
        self.assertEqual(out, orthography2ipa.G2P("eu").transcribe("Kaixo"))
        self.assertEqual(orthography2ipa.available_lexicon_codes(), [])

    def test_registry_forwards_the_key(self):
        from scriptconv.phonemizers import Phonemizer, get_phonemizer
        off = get_phonemizer(Phonemizer.ORTHOGRAPHY2IPA, packaged_lexicons=False)
        self.assertFalse(off.packaged_lexicons)
        self.assertTrue(get_phonemizer(Phonemizer.ORTHOGRAPHY2IPA).packaged_lexicons)


if __name__ == "__main__":
    unittest.main()
