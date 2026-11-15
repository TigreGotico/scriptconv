"""A backend reads the stress mark (U+0301) only in the languages it declares.

In a stress language that a backend does not declare, the mark is removed
before the backend reads the text, on every text path, so the marked output
equals the plain output. Each expected value is the backend's own output for
the plain text, or a string written from a published source.
"""
import unittest
from typing import Iterator, List
from unittest.mock import patch

from scriptconv.diacritics import diacritize, replace_stress_mark
from scriptconv.phonemizers.base import (BasePhonemizer, GraphemePhonemizer,
                                         UnicodeCodepointPhonemizer)
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.mul import GruutPhonemizer
from scriptconv.phonemizers.ru import VoskPhonemizer

ACUTE = "\u0301"


class Recorder(BasePhonemizer):
    """A backend that returns the text it receives."""

    def phonemize_string(self, text: str, lang: str) -> str:
        return text


class LazyRecorder(Recorder):
    """A backend that overrides the sentence path and does not call phonemize_string."""

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        yield list(text)


class DeclaresRussian(Recorder):
    stress_mark_langs = frozenset({"ru"})


class TestRemoval(unittest.TestCase):
    def test_undeclared_language_loses_the_mark_on_every_path(self):
        marked, plain = f"за{ACUTE}мок стои{ACUTE}т", "замок стоит"
        backend = Recorder()
        self.assertEqual(backend.phonemize_string(marked, "ru"), plain)
        self.assertEqual(backend.phonemize_string(text=marked, lang="ru"), plain)
        self.assertEqual(backend.phonemize_to_list(marked, "ru"), list(plain))
        self.assertEqual(backend.phonemize(marked, "ru"), [list(plain)])
        self.assertEqual(list(LazyRecorder().phonemize_lazy(marked, "ru")), [list(plain)])

    def test_declared_language_keeps_the_mark(self):
        marked = f"за{ACUTE}мок"
        self.assertEqual(DeclaresRussian().phonemize_string(marked, "ru"), marked)
        self.assertEqual(DeclaresRussian().phonemize_string(marked, "ru-RU"), marked)
        self.assertEqual(DeclaresRussian().phonemize(marked, "ru"), [list(marked)])

    def test_declaration_matches_the_language_not_the_family(self):
        self.assertEqual(DeclaresRussian().phonemize_string(f"за{ACUTE}мок", "uk"), "замок")
        self.assertEqual(DeclaresRussian().phonemize_string(f"за{ACUTE}мок", "be"), "замок")

    def test_an_acute_that_is_spelling_stays(self):
        # Portuguese and Spanish write the acute; NFD Macedonian ѓ is г + U+0301
        for text, lang in [(f"cafe{ACUTE}", "pt-PT"), (f"cafe{ACUTE}", "es"),
                           (f"г{ACUTE}аво", "mk")]:
            with self.subTest(lang=lang):
                self.assertEqual(Recorder().phonemize_string(text, lang), text)

    def test_only_the_acute_is_removed(self):
        grave = "\u0300"
        self.assertEqual(Recorder().phonemize_string(f"и{grave} ка{ACUTE}к", "bg"), f"и{grave} как")

    def test_replace_writes_around_the_marked_letter(self):
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru", before="+"), "прив+ет")
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru", after="+"), "приве+т")
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru"), "привет")


class TestGruutRussian(unittest.TestCase):
    """gruut writes no stress symbol for Russian, and the mark changed its consonants."""

    def test_marked_equals_plain(self):
        gruut = GruutPhonemizer()
        for marked in [f"четырёхме{ACUTE}сячные", f"Тепе{ACUTE}рь", f"кото{ACUTE}рых"]:
            with self.subTest(marked):
                plain = marked.replace(ACUTE, "")
                self.assertEqual(gruut.phonemize_string(marked, "ru"),
                                 gruut.phonemize_string(plain, "ru"))
                self.assertEqual(gruut.phonemize(marked, "ru"), gruut.phonemize(plain, "ru"))


class TestVoskReadsTheMark(unittest.TestCase):
    """Vosk is declared for Russian, so the mark still picks the reading."""

    def test_mark_moves_the_stress(self):
        vosk = VoskPhonemizer(alphabet=Alphabet.VOSK)
        self.assertNotEqual(vosk.phonemize_string(f"за{ACUTE}мок", "ru"),
                            vosk.phonemize_string(f"замо{ACUTE}к", "ru"))


class TestGraphemeStressNotation(unittest.TestCase):
    # utrobinmv/tts_ru_free_hf_vits_low_multispeaker model card: "прив+ет, как дел+а?"
    def test_plus_goes_before_the_stressed_vowel(self):
        graphemes = GraphemePhonemizer(stress_notation="plus")
        self.assertEqual(graphemes.phonemize_string(f"Приве{ACUTE}т, как дела{ACUTE}?", "ru"),
                         "прив+ет, как дел+а?")

    def test_none_removes_the_mark(self):
        graphemes = GraphemePhonemizer(stress_notation="none")
        self.assertEqual(graphemes.phonemize_string(f"приве{ACUTE}т", "ru"),
                         graphemes.phonemize_string("привет", "ru"))

    def test_acute_keeps_the_mark(self):
        self.assertEqual(GraphemePhonemizer().phonemize_string(f"приве{ACUTE}т", "ru"),
                         f"приве{ACUTE}т")
        self.assertEqual(UnicodeCodepointPhonemizer().phonemize_string(f"приве{ACUTE}т", "ru"),
                         f"приве{ACUTE}т")

    def test_spelling_acute_is_not_rewritten(self):
        graphemes = GraphemePhonemizer(stress_notation="plus")
        self.assertEqual(graphemes.phonemize_string(f"cafe{ACUTE}", "pt-PT"), f"cafe{ACUTE}")

    def test_unknown_notation_is_refused(self):
        with self.assertRaises(ValueError):
            GraphemePhonemizer(stress_notation="caret")


class TestHebrewPrefixSeparator(unittest.TestCase):
    # phonikud_onnx output for "שאינם ואשר בעבר", with its prefix separators
    PHONIKUD = "שֶׁ|אֵינָם וַ|אֲשֶׁר בֶּ|עָבָר | סוף"

    def test_diacritize_returns_no_prefix_separator(self):
        with patch("scriptconv.diacritics._phonikud") as phonikud:
            phonikud.return_value.add_diacritics.return_value = self.PHONIKUD
            self.assertEqual(diacritize("שאינם ואשר בעבר | סוף", "he"),
                             "שֶׁאֵינָם וַאֲשֶׁר בֶּעָבָר | סוף")


if __name__ == "__main__":
    unittest.main()
