"""goruut gets text without the overlay marks that it cannot read.

The diacritize stage adds tashkeel to Arabic, niqqud to Hebrew and a combining
acute (U+0301) to the stress languages. goruut reads none of them: a marked
letter stays in the source script inside the IPA, or moves to the front of the
word. The wrapper removes those marks, so marked text reads as bare text.

goruut can give a different reading of the same text from one call to the
next. So the tests check the text that goruut receives for every language.
They check goruut's IPA for one language per script, by the script of its
characters, and compare marked and bare readings only for Arabic, where goruut
is stable.
"""
import unicodedata
import unittest
from unittest.mock import patch

import requests

from scriptconv.phonemizers.mul import GoruutPhonemizer

ACUTE = "\u0301"

# (lang, bare text, the same text with the marks a diacritizer adds, the
# source script that must not reach goruut's IPA, or None where only the text
# that goruut receives is checked)
MARKED = [
    # text2tashkeel rawi-ensemble output
    ("ar", "عشرون جميل خمسة", "عِشْرُونَ جَمِيلٌ خَمْسَةَ", "ARABIC"),
    ("ar", "خمسة", "خَمْسَة", "ARABIC"),
    ("he", "ספר", "סֵפֶר", "HEBREW"),
    # stressonnx output
    ("ru", "мука и сахар", f"мука{ACUTE} и са{ACUTE}хар", "CYRILLIC"),
    ("uk", "двадцять п'ять", f"два{ACUTE}дцять п'я{ACUTE}ть", None),
    ("be", "дваццаць пяць", f"два{ACUTE}ццаць пя{ACUTE}ць", None),
    ("bg", "двадесет и пет", f"два{ACUTE}десет и{ACUTE} пе{ACUTE}т", "CYRILLIC"),
    ("mk", "дваесет и пет", f"два{ACUTE}есет и{ACUTE} пе{ACUTE}т", None),
    ("kk", "жиырма бес", f"жиырма{ACUTE} бе{ACUTE}с", None),
    ("hy", "քսան հինգ", f"քսա{ACUTE}ն հի{ACUTE}նգ", "ARMENIAN"),
    ("ka", "ოცდახუთი", f"ოცდა{ACUTE}ხუთი", "GEORGIAN"),
    ("sl-SI", "dvajset pet", f"dva{ACUTE}jset pe{ACUTE}t", None),
    ("lv", "divdesmit pieci", f"di{ACUTE}vdesmit pi{ACUTE}eci", None),
]

# Text whose letters and accents are spelling, not overlay marks: precomposed
# letters, Arabic hamza carriers, and an acute in a language without a
# diacritizer, precomposed or decomposed.
NATIVE = [
    ("ru", "ёжик и йод"),
    ("ar", "أحمد إلى آخر سؤال قائم"),
    ("lv", "māja un ķēde"),
    ("pt-PT", "o café é bom"),
    ("es", f"el cafe{ACUTE}"),
    ("fr", "été"),
]


def _without_combining_marks(text: str) -> str:
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _in_script(text: str, script: str) -> str:
    return "".join(c for c in text if unicodedata.name(c, "").startswith(script))


class TestGoruutMarks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.phonemizer = GoruutPhonemizer()
        # goruut loads a language model on the first request for it, which
        # takes up to 13 s. On a loaded machine the server can drop that first
        # request, so each language is loaded here before the tests run.
        for lang, bare, _, script in MARKED:
            if script is None:
                continue
            try:
                cls.phonemizer.phonemize_string(bare, lang)
            except requests.ConnectionError:
                pass

    @classmethod
    def tearDownClass(cls):
        server = cls.phonemizer.pygoruut.process
        server.terminate()
        server.wait()

    def _sent_to_goruut(self, text: str, lang: str) -> str:
        with patch.object(self.phonemizer.pygoruut, "phonemize", return_value="") as spy:
            self.phonemizer.phonemize_string(text, lang)
        return spy.call_args.kwargs["sentence"]

    def test_fixtures_differ_only_by_combining_marks(self):
        for lang, bare, marked, _ in MARKED:
            with self.subTest(lang=lang):
                self.assertNotEqual(marked, bare)
                self.assertEqual(_without_combining_marks(marked), bare)

    def test_goruut_receives_the_bare_text(self):
        for lang, bare, marked, _ in MARKED:
            with self.subTest(lang=lang, text=marked):
                self.assertEqual(self._sent_to_goruut(marked, lang), bare)

    def test_no_source_script_in_ipa(self):
        for lang, _, marked, script in MARKED:
            if script is None:
                continue
            with self.subTest(lang=lang, text=marked):
                ipa = self.phonemizer.phonemize_string(marked, lang)
                self.assertEqual(_in_script(ipa, script), "", ipa)

    def test_arabic_marked_reads_as_bare(self):
        for lang, bare, marked, _ in MARKED:
            if lang != "ar":
                continue
            with self.subTest(text=marked):
                expected = {self.phonemizer.phonemize_string(bare, lang) for _ in range(5)}
                for _ in range(3):
                    self.assertIn(self.phonemizer.phonemize_string(marked, lang), expected)

    def test_native_spelling_reaches_goruut(self):
        for lang, text in NATIVE:
            with self.subTest(lang=lang):
                self.assertEqual(self._sent_to_goruut(text, lang), text)


if __name__ == "__main__":
    unittest.main()
