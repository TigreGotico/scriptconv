"""euskaphone owns ``normalize``: the frontend skips its hook and passes the text as written."""
import unittest
from unittest import mock

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers.eu import EuskaphonePhonemizer


class TestEuskaphoneOwnsNormalize(unittest.TestCase):
    TEXT = "Bilera 2023/12/25ean izan zen: sagarrak, udareak, etab."
    PUNCTUATED_TEXT = "Kaixo, Etxeberria jauna. Bilera 2023/12/25ean izan zen: sagarrak, udareak, etab."
    # One sentence each, so the frontend reads each in one call.
    SENTENCES = [
        "3 sagar eta 21 udare ditut.",
        "Bilera 1990/03/07an izan zen.",
        "Etxeberria 2023-12-25ean etorriko da.",
        "Liburuak 15,50 € balio ditu.",
        "Bezeroak 1.250 € ordaindu ditu.",
        "Fruta asko erosi ditut: sagarrak, udareak, etab.",
        "Erromatarrak K.a. 218an iritsi ziren.",
    ]

    @staticmethod
    def _frontend(normalizer, **config):
        return TextFrontend(FrontendConfig("eu", normalizer=normalizer, **config),
                            EuskaphonePhonemizer())

    @staticmethod
    def _phonemes(frontend, text):
        return [phoneme for sentence in frontend.phonemize_lazy(text) for phoneme in sentence]

    def _inputs(self, frontend, text):
        """The phonemes of *text*, and each text that euskaphone was given."""
        inputs = []
        original = EuskaphonePhonemizer.phonemize_string

        def recording(backend, piece, lang="eu"):
            inputs.append(piece)
            return original(backend, piece, lang)

        with mock.patch.object(EuskaphonePhonemizer, "phonemize_string", recording):
            phonemes = self._phonemes(frontend, text)
        self.assertTrue(inputs, "euskaphone was never called")
        return phonemes, " ".join(inputs)

    def test_normalizer_hook_is_not_called(self):
        calls = []
        frontend = self._frontend(lambda text, lang: calls.append((text, lang)) or text)
        self._phonemes(frontend, self.TEXT)
        self.assertEqual(calls, [])

    def test_abbreviation_and_date_reach_euskaphone_as_written(self):
        _, joined = self._inputs(self._frontend(lambda text, lang: text), self.TEXT)
        self.assertIn("etab.", joined)
        self.assertIn("2023/12/25ean", joined)

    def test_keep_punctuation_keeps_the_marks_and_the_written_text(self):
        frontend = self._frontend(lambda text, lang: text, keep_punctuation=True)
        phonemes, joined = self._inputs(frontend, self.PUNCTUATED_TEXT)
        self.assertIn("etab.", joined)
        self.assertIn("2023/12/25ean", joined)
        self.assertIn(",", phonemes)
        self.assertIn(".", phonemes)

    def test_frontend_phonemes_equal_euskaphone_reading(self):
        from euskaphone import EuskaPhonemizer
        direct = EuskaPhonemizer()
        dialect = EuskaphonePhonemizer.get_lang("eu")
        frontend = self._frontend(lambda text, lang: text)
        self.assertEqual({sentence: self._phonemes(frontend, sentence) for sentence in self.SENTENCES},
                         {sentence: list(direct.phonemize_sentence(sentence, dialect=dialect))
                          for sentence in self.SENTENCES})


if __name__ == "__main__":
    unittest.main()
