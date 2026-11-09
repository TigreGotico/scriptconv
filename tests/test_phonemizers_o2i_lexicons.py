"""The orthography2ipa phonemizer gives its own engine the packaged o2i-lexicons.

The expected IPA is read from the o2i-lexicons data files, not from engine
output. The en-GB entries carry no stress mark, so the output is compared with
its stress marks removed. ⟨aldeburgh⟩ is an en-GB exception and ⟨cringes⟩ an
en-GB patch.
"""
import subprocess
import sys
import textwrap
import unittest

import o2i_lexicons
import orthography2ipa

from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer

STRESS = str.maketrans("", "", "ˈˌ")
EXCEPTION = "aldeburgh"
PATCH = "cringes"


def entry(path, word: str) -> str:
    """The IPA that the TSV file at *path* lists for *word*."""
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, ipa = line.partition("\t")
        if key == word:
            return ipa
    raise LookupError(f"{word!r} is not in {path}")


def rules(code: str, word: str) -> str:
    """The reading of the orthography2ipa rules alone."""
    return orthography2ipa.G2P(code, pipeline=orthography2ipa.Pipeline(lexicon={})).transcribe(word)


class TestPackagedLexicons(unittest.TestCase):
    def test_default_uses_the_packaged_exceptions(self):
        expected = entry(o2i_lexicons.tsv_path("en-GB"), EXCEPTION)
        out = Orthography2IPAPhonemizer().phonemize_string(EXCEPTION, "en-GB")
        self.assertEqual(out.translate(STRESS), expected)
        self.assertNotEqual(rules("en-GB", EXCEPTION).translate(STRESS), expected)

    def test_default_uses_the_packaged_patches(self):
        expected = entry(o2i_lexicons.patch_tsv_path("en-GB"), PATCH)
        out = Orthography2IPAPhonemizer().phonemize_string(PATCH, "en-GB")
        self.assertEqual(out.translate(STRESS), expected)
        self.assertNotEqual(rules("en-GB", PATCH).translate(STRESS), expected)

    def test_bare_english_tag_uses_the_packaged_lexicon(self):
        expected = entry(o2i_lexicons.tsv_path("en-GB"), EXCEPTION)
        out = Orthography2IPAPhonemizer().phonemize_string(EXCEPTION, "en")
        self.assertEqual(out.translate(STRESS), expected)

    def test_off_uses_the_rules_only(self):
        off = Orthography2IPAPhonemizer(packaged_lexicons=False)
        for word in (EXCEPTION, PATCH):
            self.assertEqual(off.phonemize_string(word, "en-GB"), rules("en-GB", word))

    def test_the_lexicon_does_not_leak_to_other_engines(self):
        # A fresh process, so that no other test's state is in play.
        script = textwrap.dedent(f"""
            import orthography2ipa
            from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
            rules = orthography2ipa.G2P(
                "en-GB", pipeline=orthography2ipa.Pipeline(lexicon={{}}))
            Orthography2IPAPhonemizer().phonemize_string({EXCEPTION!r}, "en-GB")
            assert orthography2ipa.available_lexicon_codes() == [], \\
                orthography2ipa.available_lexicon_codes()
            plain = orthography2ipa.G2P("en-GB").transcribe({EXCEPTION!r})
            assert plain == rules.transcribe({EXCEPTION!r}), plain
        """)
        run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_language_without_a_packaged_lexicon_uses_the_rules(self):
        self.assertNotIn("eu", orthography2ipa.packaged_lexicon_sources())
        out = Orthography2IPAPhonemizer().phonemize_string("Kaixo", "eu")
        self.assertEqual(out, rules("eu", "Kaixo"))

    def test_registry_forwards_the_key(self):
        from scriptconv.phonemizers import Phonemizer, get_phonemizer
        off = get_phonemizer(Phonemizer.ORTHOGRAPHY2IPA, packaged_lexicons=False)
        self.assertFalse(off.packaged_lexicons)
        self.assertTrue(get_phonemizer(Phonemizer.ORTHOGRAPHY2IPA).packaged_lexicons)


if __name__ == "__main__":
    unittest.main()
