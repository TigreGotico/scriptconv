"""A backend reads the stress mark (U+0301) only in the languages it declares.

In a stress language that a backend does not declare, the mark is removed
before the backend reads the text, on every text path, so the marked output
equals the plain output. Each expected value is the backend's own output for
the plain text, or a string written from a published source.
"""
import unittest
from typing import Iterator, List
from unittest.mock import patch

from stressonnx import ALL_LANGS, lang_to_script

from scriptconv.diacritics import _STRESS_SCRIPTS, diacritize, replace_stress_mark
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


class EveryPathRecorder(BasePhonemizer):
    """A backend that overrides every text method, so each one returns the text it receives."""

    def phonemize_string(self, text: str, lang: str) -> str:
        return text

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        return [text]

    def phonemize(self, text: str, lang: str) -> List[List[str]]:
        return [[text]]

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        yield [text]

    def phonemize_segments(self, text: str, lang: str) -> List[str]:
        return [text]


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

    def test_every_overridden_text_method_loses_the_mark(self):
        marked, plain = f"за{ACUTE}мок", "замок"
        backend = EveryPathRecorder()
        self.assertEqual(backend.phonemize_string(marked, "ru"), plain)
        self.assertEqual(backend.phonemize_to_list(marked, "ru"), [plain])
        self.assertEqual(backend.phonemize(marked, "ru"), [[plain]])
        self.assertEqual(list(backend.phonemize_lazy(marked, "ru")), [[plain]])
        self.assertEqual(backend.phonemize_segments(marked, "ru"), [plain])

    def test_every_tag_of_a_stress_language_loses_the_mark(self):
        # linguatag matches these tags to a stressonnx language, as the declaration does
        for text, lang in [(f"за{ACUTE}мок", "rus"), (f"за{ACUTE}мок", "rus-Cyrl"),
                           (f"за{ACUTE}мок", "ukr"), (f"за{ACUTE}мок", "ru-RU"),
                           (f"Bo{ACUTE}bu", "lv"), (f"me{ACUTE}sece", "slv"),
                           (f"ა{ACUTE}ბა", "ka"), (f"ա{ACUTE}ր", "hy"),
                           (f"о{ACUTE}т", "uz-Cyrl-UZ"), (f"о{ACUTE}т", "be-tarask")]:
            with self.subTest(lang=lang):
                self.assertEqual(Recorder().phonemize_string(text, lang), text.replace(ACUTE, ""))

    def test_a_capital_stressed_vowel_loses_the_mark(self):
        # a capital Turkic İ lowercases to i + U+0307
        for text, lang in [(f"\u0130{ACUTE}\u015f yax\u015f\u0131{ACUTE}d\u0131r.", "az-Latn"),
                           (f"\u0130{ACUTE}\u015f yax\u015f\u0131{ACUTE}d\u0131r.", "az"),
                           (f"\u0401{ACUTE}лка", "ru"), (f"\u016a{ACUTE}dens", "lv"),
                           (f"Т\u045e{ACUTE}рт", "uz-Cyrl"), (f"\u0531{ACUTE}ր", "hy")]:
            with self.subTest(lang=lang, text=text):
                self.assertEqual(Recorder().phonemize_string(text, lang), text.replace(ACUTE, ""))

    def test_the_languages_are_the_stressonnx_languages(self):
        names = {"Armn": "armenian", "Cyrl": "cyrillic", "Geor": "georgian", "Latn": "latin"}
        self.assertEqual(set(_STRESS_SCRIPTS), set(ALL_LANGS))
        for tag, script in _STRESS_SCRIPTS.items():
            with self.subTest(tag=tag):
                self.assertEqual(names[script], lang_to_script(tag))

    def test_declared_language_keeps_the_mark(self):
        marked = f"за{ACUTE}мок"
        self.assertEqual(DeclaresRussian().phonemize_string(marked, "ru"), marked)
        self.assertEqual(DeclaresRussian().phonemize_string(marked, "ru-RU"), marked)
        self.assertEqual(DeclaresRussian().phonemize(marked, "ru"), [list(marked)])

    def test_declaration_matches_the_language_not_the_family(self):
        self.assertEqual(DeclaresRussian().phonemize_string(f"за{ACUTE}мок", "uk"), "замок")
        self.assertEqual(DeclaresRussian().phonemize_string(f"за{ACUTE}мок", "be"), "замок")

    def test_an_acute_that_is_spelling_stays(self):
        # Portuguese and Spanish write the acute; NFD Macedonian ѓ is г + U+0301;
        # a Latin letter in Cyrillic text, and Kazakh in its Latin alphabet (ǵ, ó)
        for text, lang in [(f"cafe{ACUTE}", "pt-PT"), (f"cafe{ACUTE}", "es"),
                           (f"г{ACUTE}аво", "mk"), (f"Это Cafe{ACUTE} на углу.", "ru"),
                           (f"G{ACUTE}ylym o{ACUTE}ner", "kk-Latn"),
                           (f"G{ACUTE}ylym o{ACUTE}ner", "kk"), (f"cafe{ACUTE}", "ru-Latn")]:
            with self.subTest(lang=lang):
                self.assertEqual(Recorder().phonemize_string(text, lang), text)

    def test_only_the_acute_is_removed(self):
        grave = "\u0300"
        self.assertEqual(Recorder().phonemize_string(f"и{grave} ка{ACUTE}к", "bg"), f"и{grave} как")

    def test_a_mark_after_no_vowel_stays(self):
        for text in [f"1{ACUTE} к{ACUTE}", f"«{ACUTE}за»"]:
            with self.subTest(text):
                self.assertEqual(replace_stress_mark(text, "ru", before="+"), text)

    def test_a_static_or_class_text_method_is_refused(self):
        for wrap in (staticmethod, classmethod):
            with self.subTest(wrap.__name__), self.assertRaisesRegex(TypeError, "must be an instance method"):
                type("Static", (BasePhonemizer,), {"phonemize_string": wrap(lambda *args: args[-2])})

    def test_replace_writes_around_the_marked_letter(self):
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru", before="+"), "прив+ет")
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru", after="+"), "приве+т")
        self.assertEqual(replace_stress_mark(f"приве{ACUTE}т", "ru"), "привет")
        # NFD ё: the mark follows the diaeresis of its vowel
        self.assertEqual(replace_stress_mark(f"ве\u0308{ACUTE}л", "ru", before="+"), "в+е\u0308л")


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
        self.assertEqual(graphemes.phonemize_string(f"cafe{ACUTE} у до{ACUTE}ма", "ru"),
                         f"cafe{ACUTE} у д+ома")
        self.assertEqual(graphemes.phonemize_string(f"g{ACUTE}ylym o{ACUTE}ner", "kk-Latn"),
                         f"g{ACUTE}ylym o{ACUTE}ner")

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

    def test_a_bar_between_two_words_stays(self):
        for text in ["בעבר | סוף", "בעבר| סוף", "בעבר |סוף", "סוף|", "|סוף", "a|b"]:
            with self.subTest(text), patch("scriptconv.diacritics._phonikud") as phonikud:
                phonikud.return_value.add_diacritics.return_value = text
                self.assertEqual(diacritize(text, "he"), text)


if __name__ == "__main__":
    unittest.main()
