"""misaki English builds one G2P per variety, British or American.

misaki loads the ``gb_gold`` or ``us_gold`` lexicon when the G2P is built,
so a British request must build the G2P with ``british=True``. The expected
British forms come from misaki's own ``gb_gold`` lexicon.

misaki declares ``Requires-Python <3.13``, so the ``test`` extra installs it
only below 3.13 and these tests run only there.
"""
import importlib.resources
import json
import sys
import unittest

from scriptconv.phonemizers.mul import MisakiEnPhonemizer, MisakiPhonemizer

WORDS = ["can't", "water", "bottle", "tomato"]


def _lexicon(name):
    from misaki import data
    return json.loads(importlib.resources.files(data).joinpath(name).read_text())


@unittest.skipIf(sys.version_info >= (3, 13), "misaki declares Requires-Python <3.13")
class TestMisakiBritishEnglish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gb_gold = _lexicon("gb_gold.json")
        cls.us_gold = _lexicon("us_gold.json")
        cls.phonemizer = MisakiEnPhonemizer()

    def test_words_differ_between_the_lexicons(self):
        for word in WORDS:
            with self.subTest(word=word):
                self.assertNotEqual(self.gb_gold[word], self.us_gold[word])

    def test_british_request_gives_the_british_lexicon_form(self):
        for word in WORDS:
            with self.subTest(word=word):
                self.assertEqual(self.phonemizer.phonemize_string(word, "en-GB"), self.gb_gold[word])

    def test_american_request_does_not_give_the_british_form(self):
        for word in WORDS:
            with self.subTest(word=word):
                self.assertNotEqual(self.phonemizer.phonemize_string(word, "en-US"), self.gb_gold[word])

    def test_british_and_american_sentences_differ(self):
        text = "I can't find the water bottle"
        self.assertNotEqual(self.phonemizer.phonemize_string(text, "en-GB"),
                            self.phonemizer.phonemize_string(text, "en-US"))

    def test_british_region_request_gives_the_british_form(self):
        for tag in ["en-AU", "en-NZ", "en-IE", "en-ZA", "en-IN", "en_GB"]:
            with self.subTest(tag=tag):
                self.assertEqual(self.phonemizer.phonemize_string("bottle", tag), self.gb_gold["bottle"])

    def test_one_cached_g2p_per_variety(self):
        gb = self.phonemizer._get_phonemizer("en-GB")
        us = self.phonemizer._get_phonemizer("en-US")
        self.assertIsNot(gb, us)
        self.assertIs(self.phonemizer._get_phonemizer("en-GB"), gb)
        self.assertIs(self.phonemizer._get_phonemizer("en-US"), us)

    def test_dispatcher_british_request_gives_the_british_form(self):
        self.assertEqual(MisakiPhonemizer().phonemize_string("water", "en-GB"), self.gb_gold["water"])


if __name__ == "__main__":
    unittest.main()
