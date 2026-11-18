"""Clause punctuation in phonemizer output.

By default no punctuation reaches the phonemes: voices trained that way must
keep receiving the sequences they learned, and training reads the same
sequences as synthesis. ``keep_punctuation`` opts in to the
Piper convention, where every clause is followed by its symbol (``. ? !`` bare,
``, : ;`` followed by a space). Clause breaks that espeak-ng prints as ``"\\n"``
are never returned as phonemes, in either mode: each one is a space.

The espeak tests that read the phonemes are in scriptconv-copyleft, with the
espeak wrapper. The one here checks that the registry sets the flag on it.
"""
import re
import unicodedata

import pytest

from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import get_phonemizer
from scriptconv.phonemizers.base import BasePhonemizer, join_sentences
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.mul import EpitranPhonemizer
from scriptconv.phonemizers.shami import ShamiPhonemizer

SONGS = "Songs near this quiet river every morning, number three."

MULTILINGUAL = {
    "en-us": ["Songs near this quiet river every morning, number three.",
              "Is it ready? Yes! We leave at 16:30; bring 10,4 kg... Mr. Smith said: \"fine\"."],
    "pt": ["Olá, como estás? Eu estou bem! Vamos às 16:30; leva 10,4 kg."],
    "es": ["¿Dónde está la biblioteca? ¡Allí, al lado del parque!"],
    "de": ["Guten Morgen, wie geht es dir? Mir geht es gut!"],
    "ar": ["مرحبا، كيف حالك؟ أنا بخير!"],
}


class Long(BasePhonemizer):
    """Writes a doubled vowel as the vowel and an ASCII ":", as Epitran writes
    vowel length for Finnish and X-SAMPA writes it everywhere."""

    def phonemize_string(self, text, lang):
        return re.sub(r"([aeiou])\1", r"\1:", text.lower())


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


def flat(sentences):
    return [p for sentence in sentences for p in sentence]


class TestDefaultKeepsNoPunctuation:
    def test_clause_breaks_are_not_phonemes(self):
        assert CliLike().phonemize_string("one, two? three", "en") == "ONE\n TWO\n THREE"
        assert CliLike().phonemize_to_list("one, two? three", "en") == list("ONE TWO THREE")

    @pytest.mark.parametrize("text, expected", [
        ("one, two?three", "ONE TWO THREE"),
        ("one,, two", "ONE TWO"),
        ("one ,\n, two!", "ONE TWO"),
        ("one!", "ONE"),
    ])
    def test_a_clause_break_is_one_space(self, text, expected):
        assert "".join(CliLike().phonemize_to_list(text, "en")) == expected
        assert "".join(join_sentences(CliLike().phonemize(text, "en"))) == expected

    def test_synthesis_path_is_unchanged(self):
        # chunked, punctuation removed before the backend, no symbol appended
        assert CliLike().phonemize("one, two. three!", "en") == [
            list("ONE TWO"), list("THREE")]


class TestTrainingEqualsSynthesisWithoutPunctuation:
    """With the flag off, the training stream is the synthesis chunks joined by
    the contract rule, so no mark that synthesis removes reaches training."""

    TEXT = 'Olá, "Ana", tudo bem! Estás pronta?Sim.'

    @pytest.mark.parametrize("backend, expected", [
        ("graphemes", "olá ana tudo bem estás pronta sim"),
        ("unicode", unicodedata.normalize("NFD", "Olá Ana tudo bem Estás pronta Sim")),
        ("stub", "OLÁ ANA TUDO BEM ESTÁS PRONTA SIM"),
    ])
    def test_no_mark_reaches_training(self, backend, expected):
        phonemizer = CliLike() if backend == "stub" else get_phonemizer(Phonemizer(backend))
        assert "".join(phonemizer.phonemize_to_list(self.TEXT, "pt")) == expected
        assert phonemizer.phonemize_to_list(self.TEXT, "pt") == join_sentences(
            phonemizer.phonemize(self.TEXT, "pt"), keep_punctuation=False)

    def test_frontend_flat_equals_the_joined_chunks(self):
        for backend in ("graphemes", "unicode"):
            frontend = TextFrontend(FrontendConfig("pt", stages=Stages(diacritize=False)),
                                    get_phonemizer(Phonemizer(backend)))
            assert frontend.phonemize_flat(self.TEXT) == join_sentences(
                frontend.phonemize(self.TEXT), keep_punctuation=False)

    @pytest.mark.parametrize("text, expected", [
        # the text after a block starts a new sentence, so a space follows the block
        ("Olá [[ˈana]], tudo bem? Sim.", "olá ˈana tudo bem sim"),
        ("Um [[x]]. Dois; três.", "um x dois três"),
    ])
    def test_frontend_flat_keeps_a_block_apart(self, text, expected):
        frontend = TextFrontend(FrontendConfig("pt", stages=Stages(diacritize=False)),
                                get_phonemizer(Phonemizer.GRAPHEMES))
        assert "".join(frontend.phonemize_flat(text)) == expected
        assert frontend.phonemize_flat(text) == join_sentences(
            frontend.phonemize(text), keep_punctuation=False)

    def test_the_normalizer_runs_only_on_synthesis(self):
        phonemizer = CliLike()
        phonemizer.normalizer = lambda text, lang: text.replace("3", "three")
        train = phonemizer.phonemize_to_list("number three, now.", "en")
        assert "".join(train) == "NUMBER THREE NOW"
        assert join_sentences(phonemizer.phonemize("number 3, now.", "en"),
                              keep_punctuation=False) == train

    def test_a_backend_with_its_own_synthesis_keeps_its_list(self):
        class OwnSynthesis(BasePhonemizer):
            def phonemize_string(self, text, lang):
                return text.upper()

            def phonemize_lazy(self, text, lang):
                yield list(self.phonemize_string(text, lang))

        # the whole text reaches the backend, marks included
        assert OwnSynthesis().phonemize_to_list("one, two.", "en") == list("ONE, TWO.")

    def test_shami_reads_the_whole_text(self):
        shami = ShamiPhonemizer()
        # the front-end reads "!" aloud, so the whole-text read keeps that word
        assert shami.phonemize_to_list("Sim!Não", "ar") == list(shami.phonemize_string("Sim!Não", "ar"))

    @pytest.mark.parametrize("text, expected", [
        ("Kaa; taa. Saa!", "ka: ta: sa:"),
        ("Muu... kuu.", "mu: ku:"),
    ])
    def test_a_length_mark_does_not_join_two_words(self, text, expected):
        assert "".join(Long().phonemize_to_list(text, "fi")) == expected
        assert "".join(join_sentences(Long().phonemize(text, "fi"), keep_punctuation=False)) == expected

    def test_epitran_finnish_keeps_the_words_apart(self):
        epitran = EpitranPhonemizer()
        text = "Hyvää päivää; tervetuloa. Kiitos!"
        pieces = [epitran.phonemize_string(piece, "fi")
                  for piece in ("Hyvää päivää", "tervetuloa", "Kiitos")]
        assert pieces[0].endswith(":")
        assert epitran.phonemize_to_list(text, "fi") == list(" ".join(pieces))

    def test_join_without_punctuation_puts_one_space_between_sentences(self):
        sentences = [list("a:"), list("b?"), list("c ")]
        assert join_sentences(sentences, keep_punctuation=False) == list("a: b? c ")
        # with punctuation, a final clause symbol reads as a token
        assert join_sentences(sentences) == list("a:b?c ")


class TestKeepPunctuation:
    def test_a_length_mark_is_not_a_token(self):
        phonemizer = Long()
        phonemizer.keep_punctuation = True
        # an ellipsis ends the first sentence with no token, so a space follows
        assert "".join(phonemizer.phonemize_to_list("Kaa... Saa.", "fi")) == "ka: sa:."
        assert phonemizer.phonemize("Kaa... Saa.", "fi") == [list("ka:"), list("sa:.")]

    def test_epitran_finnish_keeps_the_words_apart(self):
        epitran = EpitranPhonemizer()
        epitran.keep_punctuation = True
        first, second = (epitran.phonemize_string(piece, "fi") for piece in ("Hyvää päivää", "Kiitos"))
        assert first.endswith(":")
        assert epitran.phonemize_to_list("Hyvää päivää... Kiitos.", "fi") == list(f"{first} {second}.")

    def test_factory_sets_the_flag(self):
        phonemizer = get_phonemizer(Phonemizer.ESPEAK, keep_punctuation=True)
        assert phonemizer.keep_punctuation is True
        assert "," in phonemizer.phonemize_to_list(SONGS, "en-us")

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

    @pytest.mark.parametrize("text", ["Olá\nTudo bem.", "Olá\r\nTudo bem.", "Olá\n\nTudo bem."])
    def test_a_line_break_from_the_unicode_backend_is_a_space(self, text):
        unicode = get_phonemizer(Phonemizer.UNICODE, keep_punctuation=True)
        expected = list(unicodedata.normalize("NFD", "Olá Tudo bem."))
        assert unicode.phonemize_to_list(text, "pt") == expected
        assert unicode.phonemize(text, "pt") == [expected]

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

    @pytest.mark.timeout(10)
    def test_a_long_run_of_dots_with_no_space_after_it_is_one_clause(self):
        from scriptconv.phonemizers.base import split_clauses
        sentence = "a" + "." * 20000 + "b"
        assert split_clauses(sentence) == [(sentence, None)]

    @pytest.mark.timeout(10)
    def test_a_long_run_of_dots_before_a_space_ends_a_clause(self):
        from scriptconv.phonemizers.base import split_clauses
        assert split_clauses("a" + "." * 20000 + " b") == [("a", None), (" b", None)]
