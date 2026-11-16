"""TextFrontend reads the text first and cuts it into chunks after.

The contract: blocks, then the normalisation hook on the whole text, then
casing, then the sentence split of the normalised text, then for each
sentence, lazily, the diacritizer and the backend. A backend that owns
``normalize`` and reads whole text gets the whole text.
"""
import pytest

from scriptconv import frontend as frontend_module
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend, spoken_normalizer
from scriptconv.phonemizers import Alphabet, BasePhonemizer
from scriptconv.phonemizers._thirdparty.dizione.symbols import PHONE_SET, STRESS_MARKS
from scriptconv.phonemizers.dizione import DizionePhonemizer


class Echo(BasePhonemizer):
    """Phonemes are the characters of the text. Each text read is recorded."""

    def __init__(self, events=None):
        super().__init__(Alphabet.IPA)
        self.events = [] if events is None else events

    def phonemize_string(self, text, lang):
        self.events.append(("backend", text))
        return text


class NormalizeOwner(Echo):
    owned_stages = frozenset({"normalize"})


def tokens_ipa(phonemized):
    """The words of a dizione token sequence in IPA, written here from the symbols and the stress."""
    words, word = [], ""
    for symbol, stress in zip(phonemized.symbols, phonemized.stress):
        if symbol in PHONE_SET:
            word += STRESS_MARKS.get(stress, "") + symbol
        elif word:
            words.append(word)
            word = ""
    return words + [word] if word else words


class TestTheHookReadsTheWholeText:
    def test_a_reading_that_needs_the_word_after_a_raw_sentence_end(self):
        # quebra_frases ends a sentence after "Mrs.". text2spoken reads a title
        # of its "titles" table, "Mrs.": "Missus", only before a capital letter,
        # so it reads "Mrs." only when it sees the name after it.
        assert frontend_module._sentence_tokenize("Mrs. Smith arrived.") == ["Mrs.", "Smith arrived."]
        hook = spoken_normalizer()
        assert hook("Mrs.", "en") == "Mrs."
        assert hook("Mrs. Smith arrived.", "en") == "Missus Smith arrived."
        frontend = TextFrontend(FrontendConfig("en", normalizer=hook, stages=Stages(diacritize=False)),
                                Echo())
        assert frontend.phonemize("Mrs. Smith arrived.") == [list("Missus Smith arrived")]
        assert frontend.phonemize_flat("Mrs. Smith arrived.") == list("Missus Smith arrived")

    def test_the_whole_text_is_normalised_before_the_first_sentence_is_read(self, monkeypatch):
        events = []

        def normalize(text, lang):
            events.append(("normalize", text))
            return text

        def diacritize(text, lang, diacritizer_model=None):
            events.append(("diacritize", text))
            return text

        monkeypatch.setattr(frontend_module, "diacritize", diacritize)
        frontend = TextFrontend(FrontendConfig("xx", normalizer=normalize,
                                               stages=Stages(diacritize=True)), Echo(events))
        chunks = frontend.phonemize_lazy("ab. cd. ef.")
        assert events == []
        assert next(chunks) == list("ab")
        # sentence 2 is neither diacritized nor read before sentence 1 is yielded
        assert events == [("normalize", "ab. cd. ef."), ("diacritize", "ab."), ("backend", "ab")]
        assert list(chunks) == [list("cd"), list("ef")]
        assert events[3:] == [("diacritize", "cd."), ("backend", "cd"),
                              ("diacritize", "ef."), ("backend", "ef")]


class TestAnOwnerThatCannotReportItsMarks:
    def test_it_gets_the_raw_text_split_and_any_other_backend_the_read_text_split(self):
        def run(backend):
            cased = []

            def casing(text):
                cased.append(text)
                return text

            frontend = TextFrontend(FrontendConfig("xx", stages=Stages(diacritize=False, casing=casing)),
                                    backend)
            frontend.phonemize("ab. cd.")
            return cased

        assert run(NormalizeOwner()) == ["ab.", "cd."]
        assert run(Echo()) == ["ab. cd."]
        assert NormalizeOwner.reads_whole_text is False


@pytest.fixture(scope="module")
def dizione():
    return DizionePhonemizer()


class TestDizioneReadsTheWholeText:
    # The texts that the raw sentence split read wrongly: each loses a word of
    # context at a full stop that belongs to the reading.
    TEXTS = [
        "Mon. to Fri., Jan. 5 to Dec. 25.",
        "See p. 12 and No. 5.",
        "Delivery Mon.-Fri., see the ref. no. on the 3rd fl.",
        "The max. load is listed; the est. time is short.",
        "F. A. McKenzie wrote it.",
        "Jan. 1, 2000",
        "Prof. X",
        "Prof. Close the door.",
    ]

    @pytest.mark.parametrize("text", TEXTS)
    def test_the_frontend_reads_what_tokens_reads(self, dizione, text):
        frontend = TextFrontend(FrontendConfig("en-US"), dizione)
        expected = tokens_ipa(dizione.tokens(text))
        assert " ".join("".join(chunk) for chunk in frontend.phonemize(text)).split() == expected
        assert "".join(frontend.phonemize_flat(text)).split() == expected

    @pytest.mark.parametrize("text, word, reading", [
        ("Prof. Close the door.", 1, "klˈoʊs"),
        ("Jan. 1, 2000", 1, "fˈɜːst"),
        ("See p. 12 and No. 5.", 1, "pˈeɪdʒ"),
    ])
    def test_an_abbreviation_keeps_the_word_after_it(self, dizione, text, word, reading):
        frontend = TextFrontend(FrontendConfig("en-US"), dizione)
        assert " ".join("".join(chunk) for chunk in frontend.phonemize(text)).split()[word] == reading
