"""Clause punctuation in phonemizer output.

By default no punctuation reaches the phonemes: voices trained that way must
keep receiving the sequences they learned. ``keep_punctuation`` opts in to the
Piper convention, where every clause is followed by its symbol (``. ? !`` bare,
``, : ;`` followed by a space). Clause breaks that espeak-ng prints as ``"\\n"``
are never returned as phonemes, in either mode.

The espeak tests run against the espeak-ng binary when it is installed and
against the pure-Python espyak port otherwise, so they assert the punctuation
and its position, not the exact phonemes the two produce for the words.
"""
import re

import pytest

from scriptconv.phonemizers import get_phonemizer
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.mul import EspeakPhonemizer

SONGS = "Songs near this quiet river every morning, number three."

MULTILINGUAL = {
    "en-us": ["Songs near this quiet river every morning, number three.",
              "Is it ready? Yes! We leave at 16:30; bring 10,4 kg... Mr. Smith said: \"fine\"."],
    "pt": ["Olá, como estás? Eu estou bem! Vamos às 16:30; leva 10,4 kg."],
    "es": ["¿Dónde está la biblioteca? ¡Allí, al lado del parque!"],
    "de": ["Guten Morgen, wie geht es dir? Mir geht es gut!"],
    "ar": ["مرحبا، كيف حالك؟ أنا بخير!"],
}


class CliLike(BasePhonemizer):
    """Behaves like the espeak-ng CLI: drops punctuation, prints a newline at
    every clause break, and nothing for a full stop."""

    def phonemize_string(self, text, lang):
        out = []
        for char in text:
            if char in ",?!;:":
                out.append("\n")
            elif char not in ".":
                out.append(char.upper())
        return "".join(out).strip()


@pytest.fixture
def espeak():
    return EspeakPhonemizer()


def flat(sentences):
    return [p for sentence in sentences for p in sentence]


class TestDefaultKeepsNoPunctuation:
    def test_flag_is_off_by_default(self, espeak):
        assert espeak.keep_punctuation is False
        assert get_phonemizer(Phonemizer.ESPEAK).keep_punctuation is False

    def test_no_punctuation_in_espeak_output(self, espeak):
        for lang, texts in MULTILINGUAL.items():
            for text in texts:
                assert not set(",.?!:;") & set(espeak.phonemize_to_list(text, lang))
                assert not set(",.?!:;") & set(flat(espeak.phonemize(text, lang)))

    def test_clause_breaks_are_not_phonemes(self):
        assert CliLike().phonemize_string("one, two? three", "en") == "ONE\n TWO\n THREE"
        assert CliLike().phonemize_to_list("one, two? three", "en") == list("ONE TWO THREE")

    def test_no_newline_from_espeak(self, espeak):
        for lang, texts in MULTILINGUAL.items():
            for text in texts:
                assert "\n" not in espeak.phonemize_to_list(text, lang)

    def test_default_matches_the_previous_definitions(self, espeak):
        # phonemize_to_list was list(phonemize_string) and phonemize_lazy
        # phonemized each chunk_text chunk with its punctuation removed; the
        # default output is those, less the newline clause breaks
        for lang, texts in MULTILINGUAL.items():
            for text in texts:
                raw = espeak.phonemize_string(text, lang)
                assert espeak.phonemize_to_list(text, lang) == [p for p in raw if p != "\n"]
                previous = [
                    list(re.sub(r"\([^)]+\)", "", espeak.phonemize_string(
                        espeak.remove_punctuation(chunk), lang)))
                    for chunk, _, _ in espeak.chunk_text(text)]
                assert espeak.phonemize(text, lang) == previous
                assert list(espeak.phonemize_lazy(text, lang)) == previous

    def test_synthesis_path_is_unchanged(self):
        # chunked, punctuation removed before the backend, no symbol appended
        assert CliLike().phonemize("one, two. three!", "en") == [
            list("ONE TWO"), list("THREE")]


class TestKeepPunctuation:
    def test_espeak_keeps_comma_and_full_stop(self, espeak):
        espeak.keep_punctuation = True
        phonemes = espeak.phonemize_to_list(SONGS, "en-us")
        text = "".join(phonemes)
        assert phonemes.count(",") == 1 and phonemes.count(".") == 1
        assert phonemes[-1] == "."
        assert text.index(", ") < text.index("nˈʌmb")  # before "number"
        assert "\n" not in phonemes

    def test_factory_sets_the_flag(self):
        phonemizer = get_phonemizer(Phonemizer.ESPEAK, keep_punctuation=True)
        assert phonemizer.keep_punctuation is True
        assert "," in phonemizer.phonemize_to_list(SONGS, "en-us")

    def test_training_and_synthesis_agree(self, espeak):
        espeak.keep_punctuation = True
        for lang, texts in MULTILINGUAL.items():
            for text in texts:
                train = espeak.phonemize_to_list(text, lang)
                synth = flat(espeak.phonemize(text, lang))
                assert train == synth, (lang, text)
                assert flat(espeak.phonemize_lazy(text, lang)) == synth
                assert "\n" not in train

    def test_symbols_follow_piper(self):
        phonemizer = CliLike()
        phonemizer.keep_punctuation = True
        assert phonemizer.phonemize_to_list("one, two: three; four? five! six.", "en") == (
            list("ONE") + [",", " "] + list("TWO") + [":", " "] + list("THREE")
            + [";", " "] + list("FOUR") + ["?"] + list("FIVE") + ["!"] + list("SIX") + ["."])

    def test_sentences_stay_separate_for_synthesis(self):
        phonemizer = CliLike()
        phonemizer.keep_punctuation = True
        assert phonemizer.phonemize("One, two. Three?", "en") == [
            list("ONE") + [",", " "] + list("TWO") + ["."], list("THREE") + ["?"]]

    def test_arabic_marks_map_to_ascii(self, espeak):
        espeak.keep_punctuation = True
        phonemes = espeak.phonemize_to_list("مرحبا، كيف حالك؟ أنا بخير!", "ar")
        assert [p for p in phonemes if p in ",?!"] == [",", "?", "!"]

    def test_normalizer_runs_only_on_synthesis(self):
        phonemizer = CliLike()
        phonemizer.keep_punctuation = True
        phonemizer.normalizer = lambda text, lang: text.replace("3", "three")
        train = phonemizer.phonemize_to_list("number three.", "en")
        assert train[-1] == "."
        assert flat(phonemizer.phonemize("number 3.", "en")) == train

    def test_a_backend_with_its_own_list_ignores_the_flag(self):
        class OwnList(CliLike):
            def phonemize_to_list(self, text, lang):
                return list(self.phonemize_string(self.remove_punctuation(text), lang))

        phonemizer = OwnList()
        phonemizer.keep_punctuation = True
        # one side overridden: honouring the flag on the other side alone would
        # make training and synthesis disagree
        assert phonemizer.phonemize("one, two.", "en") == [list("ONE TWO")]


class TestSplitClauses:
    @pytest.mark.parametrize("sentence, clauses", [
        ("one, two.", [("one", ","), (" two.", ".")]),
        ("at 16:30, ten", [("at 16:30", ","), (" ten", None)]),
        ("10,4 kg", [("10,4 kg", None)]),
        ("wait... go", [("wait", None), (" go", None)]),
        ("wait…", [("wait…", None)]),
        ('he said "hi," then left.', [('he said "hi', ","), (" then left.", ".")]),
        ("really?! yes", [("really", "?"), (" yes", None)]),
        ("Mr. Smith", [("Mr. Smith", None)]),
        ("مرحبا، كيف", [("مرحبا", ","), (" كيف", None)]),
    ])
    def test_split(self, sentence, clauses):
        from scriptconv.phonemizers.base import split_clauses
        assert split_clauses(sentence) == clauses
