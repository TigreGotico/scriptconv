"""Clause punctuation in phonemizer output.

By default no punctuation reaches the phonemes: voices trained that way must
keep receiving the sequences they learned. ``keep_punctuation`` opts in to the
Piper convention, where every clause is followed by its symbol (``. ? !`` bare,
``, : ;`` followed by a space). Clause breaks that espeak-ng prints as ``"\\n"``
are never returned as phonemes, in either mode: each one is a space.

The espeak tests run against the espeak-ng binary when it is installed and
against the pure-Python espyak port otherwise, so they assert the punctuation
and its position, not the exact phonemes the two produce for the words.
"""
import re
import unicodedata

import pytest

from scriptconv.phonemizers import get_phonemizer
from scriptconv.phonemizers.base import BasePhonemizer, join_sentences
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
        # default output is those, with a space at each newline clause break
        for lang, texts in MULTILINGUAL.items():
            for text in texts:
                raw = espeak.phonemize_string(text, lang)
                assert espeak.phonemize_to_list(text, lang) == list(raw.replace("\n", " "))
                previous = [
                    list(re.sub(r"\([^)]+\)", "", espeak.phonemize_string(
                        espeak.remove_punctuation(chunk), lang)))
                    for chunk, _, _ in espeak.chunk_text(text)]
                assert espeak.phonemize(text, lang) == previous
                assert list(espeak.phonemize_lazy(text, lang)) == previous

    @pytest.mark.parametrize("text, expected", [
        ("one,two?three", "ONE TWO THREE"),
        ("one,, two", "ONE TWO"),
        ("one ,\n, two!", "ONE TWO"),
        ("one!", "ONE"),
    ])
    def test_a_clause_break_is_one_space(self, text, expected):
        assert "".join(CliLike().phonemize_to_list(text, "en")) == expected

    @pytest.mark.parametrize("prefer_espyak", [False, True])
    def test_espeak_reads_the_clauses_apart(self, prefer_espyak):
        espeak = EspeakPhonemizer(prefer_espyak=prefer_espyak)
        text = "Olá! Tudo bem? Sim."
        clauses = [espeak.phonemize_string(clause, "pt") for clause in ("Olá", "Tudo bem", "Sim")]
        assert espeak.phonemize_to_list(text, "pt") == list(" ".join(clauses))
        assert espeak.phonemize_to_list(text, "pt") == join_sentences(espeak.phonemize(text, "pt"))

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
                synth = espeak.phonemize(text, lang)
                assert train == join_sentences(synth), (lang, text)
                assert list(espeak.phonemize_lazy(text, lang)) == synth
                assert "\n" not in train

    def test_symbols_follow_piper(self):
        phonemizer = CliLike()
        phonemizer.keep_punctuation = True
        assert phonemizer.phonemize_to_list("one, two: three; four? five! six.", "en") == (
            list("ONE") + [",", " "] + list("TWO") + [":", " "] + list("THREE")
            + [";", " "] + list("FOUR") + ["?"] + list("FIVE") + ["!", " "]
            + list("SIX") + ["."])

    @pytest.mark.parametrize("text, expected", [
        # the text writes a space after the mark, and the next clause starts a
        # new word: a grapheme voice trained on raw text learned that space
        ("one! two?", list("ONE") + ["!", " "] + list("TWO") + ["?"]),
        ("one?! two", list("ONE") + ["?", " "] + list("TWO")),
        # an ellipsis ends a clause with no symbol; the words stay apart
        ("wait… go", list("WAIT") + [" "] + list("GO")),
        ("one | two", list("ONE") + [" "] + list("TWO")),
        # the last clause of a sentence gets no space after its mark
        ("one!", list("ONE") + ["!"]),
    ])
    def test_a_space_follows_a_clause_inside_a_sentence(self, text, expected):
        phonemizer = CliLike()
        phonemizer.keep_punctuation = True
        assert phonemizer.phonemize_to_list(text, "en") == expected

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
        assert join_sentences(phonemizer.phonemize("number 3.", "en")) == train

    def test_a_backend_with_its_own_list_ignores_the_flag(self):
        class OwnList(CliLike):
            def phonemize_to_list(self, text, lang):
                return list(self.phonemize_string(self.remove_punctuation(text), lang))

        phonemizer = OwnList()
        phonemizer.keep_punctuation = True
        # one side overridden: honouring the flag on the other side alone would
        # make training and synthesis disagree
        assert phonemizer.phonemize("one, two.", "en") == [list("ONE TWO")]


class TestWordsStayApart:
    """A sentence that ends with no symbol, and a ``!`` or ``?`` between two
    letters, both separate two words, so the phonemes keep a space there."""

    @staticmethod
    def kept(backend):
        phonemizer = CliLike() if backend == "stub" else get_phonemizer(Phonemizer(backend))
        phonemizer.keep_punctuation = True
        return phonemizer

    @pytest.mark.parametrize("backend, text, expected", [
        # quebra_frases ends a sentence at an ASCII "...", with no symbol
        ("graphemes", "Espera... vamos.", "espera vamos."),
        ("unicode", "Espera... vamos.", unicodedata.normalize("NFD", "Espera vamos.")),
        ("stub", "Espera... vamos.", "ESPERA VAMOS."),
        ("graphemes", "a ... b", "a b"),
        ("stub", "a ... b", "A B"),
        # a "!" or "?" with no space after it is no clause break
        ("graphemes", "Sim!Não! talvez", "sim não! talvez"),
        ("unicode", "Sim!Não! talvez", unicodedata.normalize("NFD", "Sim Não! talvez")),
        ("stub", "Sim!Não! talvez", "SIM NÃO! TALVEZ"),
        ("graphemes", "Isto?Aquilo", "isto aquilo"),
        ("unicode", "Isto?Aquilo", "Isto Aquilo"),
        ("stub", "Isto?Aquilo", "ISTO AQUILO"),
        ("graphemes", "Sim?!Não", "sim não"),
        # every mark that the clause table reads as "?" counts
        ("graphemes", "نعم؟لا", "نعم لا"),
        ("unicode", "نعم؟لا", "نعم لا"),
    ])
    def test_words_stay_apart(self, backend, text, expected):
        phonemizer = self.kept(backend)
        assert "".join(phonemizer.phonemize_to_list(text, "pt")) == expected
        assert "".join(join_sentences(phonemizer.phonemize(text, "pt"))) == expected

    @pytest.mark.parametrize("text, parts", [
        # two sentences: each read on its own, then a space between them
        ("Espera... vamos.", ["Espera", "vamos."]),
        ("a ... b", ["a", "b"]),
        # one sentence: read as the text with a written space
        ("sim!não! talvez", ["sim não! talvez"]),
        ("isto?aquilo", ["isto aquilo"]),
    ])
    @pytest.mark.parametrize("prefer_espyak", [False, True])
    def test_espeak_reads_the_words_apart(self, text, parts, prefer_espyak):
        espeak = EspeakPhonemizer(prefer_espyak=prefer_espyak)
        espeak.keep_punctuation = True
        words = espeak.phonemize_to_list(parts[0], "pt")
        for part in parts[1:]:
            words += [" "] + espeak.phonemize_to_list(part, "pt")
        assert espeak.phonemize_to_list(text, "pt") == words
        assert join_sentences(espeak.phonemize(text, "pt")) == words

    @pytest.mark.parametrize("backend, text, expected", [
        # a sentence that ends in a symbol joins the next one, as in Piper
        ("graphemes", "estás? Eu", "estás?eu"),
        ("stub", "estás? Eu", "ESTÁS?EU"),
        ("graphemes", "Olá, ... vamos.", "olá, vamos."),
        ("graphemes", "U.S.A.! go", "usa! go"),
        ("graphemes", "10,4", "10,4"),
        ("graphemes", "16:30", "16,30"),
        ("unicode", "16:30", "16:30"),
        ("stub", "um!", "UM!"),
        ("graphemes", "um!", "um!"),
        # a full-width mark gives no space: CJK text writes none
        ("graphemes", "你好！我们走。", "你好我们走"),
        ("unicode", "你好！我们走。", "你好我们走"),
    ])
    def test_joins_that_stay(self, backend, text, expected):
        phonemizer = self.kept(backend)
        assert "".join(phonemizer.phonemize_to_list(text, "pt")) == expected
        assert "".join(flat(phonemizer.phonemize(text, "pt"))) == expected

    @pytest.mark.parametrize("backend, text, sentences", [
        ("stub", "Espera... vamos.", ["ESPERA", "VAMOS."]),
        ("stub", "a ... b", ["A", "B"]),
        ("stub", "Espera. Vamos...", ["ESPERA.", "VAMOS"]),
        ("graphemes", "Espera... vamos.", ["espera", "vamos."]),
        ("graphemes", "a ... b", ["a", "b"]),
    ])
    def test_no_sentence_starts_with_a_space(self, backend, text, sentences):
        # a voice never saw a space at the start of an utterance; the space
        # between two sentences exists only in the flat training stream
        phonemizer = self.kept(backend)
        assert phonemizer.phonemize(text, "pt") == [list(s) for s in sentences]
        assert list(phonemizer.phonemize_lazy(text, "pt")) == [list(s) for s in sentences]

    @pytest.mark.parametrize("text", ["Espera... vamos.", "a ... b"])
    @pytest.mark.parametrize("prefer_espyak", [False, True])
    def test_no_espeak_sentence_starts_with_a_space(self, text, prefer_espyak):
        espeak = EspeakPhonemizer(prefer_espyak=prefer_espyak)
        espeak.keep_punctuation = True
        sentences = espeak.phonemize(text, "pt")
        assert len(sentences) == 2
        assert all(sentence and sentence[0] != " " for sentence in sentences)

    def test_synthesis_without_punctuation_keeps_the_words_apart(self):
        phonemizer = get_phonemizer(Phonemizer.GRAPHEMES)
        assert phonemizer.phonemize("Sim!Não! talvez", "pt") == [list("sim não talvez")]
        chunks = phonemizer.phonemize("Espera... vamos.", "pt")
        assert [chunk for chunk in chunks if chunk] == [list("espera"), list("vamos")]


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
