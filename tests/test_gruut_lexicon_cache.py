"""gruut's sentence rules must not change its cached lexicon pronunciations.

The French liaison and the Catalan fusion rules of gruut change the phoneme
list of a word in place. gruut gives each word the list it caches for the
lexicon entry, so without a copy one liaison changes every later reading of
the same word in the process.

The expected values come from gruut's own lexicon databases and the rules in
``gruut/lang.py``, not from a run of the phonemizer.
"""

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

import gruut_lang_ca
import gruut_lang_fr

from scriptconv.phonemizers.mul import GruutPhonemizer


def lexicon(lang_module, word: str) -> str:
    """The pronunciation gruut reads for a word: the first row by pron_order."""
    db = Path(lang_module.get_lang_dir()) / "lexicon.db"
    with closing(sqlite3.connect(str(db))) as conn:
        row = conn.execute(
            "SELECT phonemes FROM word_phonemes WHERE word = ? ORDER BY pron_order",
            (word,),
        ).fetchone()
    return row[0].replace(" ", "")


class TestFrenchLiaison(unittest.TestCase):
    """fr_post_process_sentence: a pronoun that ends in a silent "s" takes a
    "z" before a verb that starts with a vowel. A consonant start takes none."""

    def assert_no_leak(self, pronoun: str, consonant_verb: str, vowel_verb: str):
        phonemizer = GruutPhonemizer()
        pron = lexicon(gruut_lang_fr, pronoun)
        plain = f"{pron} {lexicon(gruut_lang_fr, consonant_verb)}"
        liaison = f"{pron}z {lexicon(gruut_lang_fr, vowel_verb)}"

        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {consonant_verb}", "fr"), plain)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {vowel_verb}", "fr"), liaison)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {consonant_verb}", "fr"), plain)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {vowel_verb}", "fr"), liaison)

    def test_nous(self):
        self.assert_no_leak("nous", "dînons", "allons")

    def test_vous(self):
        self.assert_no_leak("vous", "dînez", "allez")


class TestCatalanFusion(unittest.TestCase):
    """fusion_if_needed, case 3: a final neutral vowel drops before a word
    that starts with a neutral vowel. The word alone keeps it."""

    def test_aimara(self):
        phonemizer = GruutPhonemizer()
        word = lexicon(gruut_lang_ca, "aimara")
        self.assertTrue(word.endswith("ə"))
        fused = f"{word[:-1]} {lexicon(gruut_lang_ca, 'ablació')}"

        self.assertEqual(phonemizer.phonemize_string("aimara", "ca"), word)
        self.assertEqual(phonemizer.phonemize_string("aimara ablació", "ca"), fused)
        self.assertEqual(phonemizer.phonemize_string("aimara", "ca"), word)
        self.assertEqual(phonemizer.phonemize_string("aimara ablació", "ca"), fused)


if __name__ == "__main__":
    unittest.main()
