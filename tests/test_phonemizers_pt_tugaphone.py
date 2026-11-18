"""Tests for TugaphonePhonemizer sub-regional lect resolution.

A sub-regional lect tag such as ``pt-PT-x-lisbon`` or ``pt-PT-x-porto`` must
resolve to itself, and must phonemize distinctly from the generic country
lect and from every other sub-regional lect. A loose tag like ``pt`` must
still resolve to a default supported lect, and a non-Portuguese tag must be
rejected.
"""
import unittest
from unittest import mock

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers.pt import TugaphonePhonemizer


class TestTugaphoneSubregionalLects(unittest.TestCase):

    def setUp(self):
        self.pho = TugaphonePhonemizer()

    def test_subregional_lects_pass_through(self):
        self.assertEqual(TugaphonePhonemizer.get_lang("pt-PT-x-lisbon"), "pt-PT-x-lisbon")
        self.assertEqual(TugaphonePhonemizer.get_lang("pt-PT-x-porto"), "pt-PT-x-porto")

    def test_subregional_lects_produce_distinct_output(self):
        # Lisbon centralizes <ei> to [ɐj]; Porto merges /v/ into [b].
        self.assertIn("ˈpejʃ", self.pho.phonemize_string("O peixe", "pt-PT"))
        self.assertIn("ˈpɐjʃ", self.pho.phonemize_string("O peixe", "pt-PT-x-lisbon"))
        self.assertIn("ˈviɲu", self.pho.phonemize_string("O vinho", "pt-PT"))
        self.assertIn("ˈbiɲu", self.pho.phonemize_string("O vinho", "pt-PT-x-porto"))

    def test_loose_tag_still_resolves(self):
        # "pt" has no country/lect of its own; it must still resolve to a
        # default supported lect instead of raising.
        resolved = TugaphonePhonemizer.get_lang("pt")
        self.assertIn(resolved, ["pt-PT", "pt-BR", "pt-AO", "pt-MZ", "pt-TL"])

    def test_non_portuguese_still_rejected(self):
        with self.assertRaises(ValueError):
            TugaphonePhonemizer.get_lang("es")


class TestTugaphoneOwnsNormalize(unittest.TestCase):
    """The frontend leaves normalisation to tugaphone.

    tugaphone spells out numbers, dates and abbreviations itself, so the
    frontend must not run its ``normalizer`` hook before it, and the text must
    reach tugaphone as written, abbreviations and dates included.
    """

    TEXT = "O Dr. Silva chega a 25/12/2023."
    PUNCTUATED_TEXT = "Olá, Dr. Silva. Chega a 25/12/2023."

    @staticmethod
    def _frontend(normalizer, **config):
        return TextFrontend(FrontendConfig("pt-PT", normalizer=normalizer, **config),
                            TugaphonePhonemizer())

    @classmethod
    def _phonemes(cls, frontend):
        return [phoneme for sentence in frontend.phonemize_lazy(cls.TEXT)
                for phoneme in sentence]

    def test_normalizer_hook_is_not_called(self):
        calls = []
        frontend = self._frontend(lambda text, lang: calls.append((text, lang)) or text)
        self._phonemes(frontend)
        self.assertEqual(calls, [])

    def test_abbreviation_and_date_reach_tugaphone_as_written(self):
        inputs = []
        original = TugaphonePhonemizer.phonemize_string

        def recording(self, text, lang):
            inputs.append(text)
            return original(self, text, lang)

        frontend = self._frontend(lambda text, lang: text)
        with mock.patch.object(TugaphonePhonemizer, "phonemize_string", recording):
            self._phonemes(frontend)
        self.assertTrue(inputs, "tugaphone was never called")
        joined = " ".join(inputs)
        self.assertIn("Dr.", joined)
        self.assertIn("25/12/2023", joined)

    def test_keep_punctuation_keeps_the_marks_and_the_written_text(self):
        inputs = []
        original = TugaphonePhonemizer.phonemize_string

        def recording(self, text, lang):
            inputs.append(text)
            return original(self, text, lang)

        frontend = self._frontend(lambda text, lang: text, keep_punctuation=True)
        with mock.patch.object(TugaphonePhonemizer, "phonemize_string", recording):
            phonemes = [phoneme for sentence in frontend.phonemize_lazy(self.PUNCTUATED_TEXT)
                        for phoneme in sentence]
        joined = " ".join(inputs)
        self.assertTrue(inputs, "tugaphone was never called")
        self.assertIn("Dr.", joined)
        self.assertIn("25/12/2023", joined)
        self.assertIn(",", phonemes)
        self.assertIn(".", phonemes)

    def test_frontend_phonemes_equal_tugaphone_reading(self):
        from tugaphone import TugaPhonemizer
        frontend = self._frontend(lambda text, lang: text)
        frontend_phonemes = self._phonemes(frontend)
        direct = list(TugaPhonemizer().phonemize_sentence(self.TEXT, "pt-PT"))
        self.assertEqual(frontend_phonemes, direct)


if __name__ == "__main__":
    unittest.main()
