"""Every stage reads its text without the whitespace at the edges, and that whitespace goes back around the result."""
import pytest

import scriptconv.frontend as frontend_module
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.dizione import DizionePhonemizer

FATHA = "َ"
TEXT = "  I have [[ab]]  three cats.  \n\n  Do you , want tea?  Yes,  please.  [[cd]]  "


class Echo(BasePhonemizer):
    """Phonemes are the characters of the text."""

    def __init__(self):
        super().__init__(Alphabet.IPA)

    def phonemize_string(self, text, lang):
        return text


class NormalizeOwner(Echo):
    owned_stages = frozenset({"normalize"})


BACKENDS = {"echo": Echo, "normalize-owner": NormalizeOwner, "dizione": DizionePhonemizer}


def _recording_frontend(monkeypatch, backend, mark=""):
    """A frontend whose hook, casing and diacritizer record the text they receive. The diacritizer appends *mark*."""
    received = []

    def normalize(text, lang):
        received.append(("normalize", text))
        return text

    def casing(text):
        received.append(("casing", text))
        return text

    def diacritize(text, lang, diacritizer_model=None):
        received.append(("diacritize", text))
        return text + mark

    monkeypatch.setattr(frontend_module, "diacritize", diacritize)
    config = FrontendConfig("en-US", normalizer=normalize, stages=Stages(diacritize=True, casing=casing))
    return TextFrontend(config, backend), received


def test_the_diacritizer_marks_the_word_before_a_block_not_the_space(monkeypatch):
    frontend, received = _recording_frontend(monkeypatch, Echo(), mark=FATHA)
    first = frontend.phonemize("عندي [[ab]] قطط.")[0]
    assert first == [*"عندي", FATHA, " ", "a", "b", " "]
    assert [text for stage, text in received if stage == "diacritize"] == ["عندي", "قطط."]


PATHS = {
    "phonemize": lambda frontend, text: frontend.phonemize(text),
    "phonemize_lazy": lambda frontend, text: list(frontend.phonemize_lazy(text)),
    "phonemize_flat": lambda frontend, text: frontend.phonemize_flat(text),
    "sentence": lambda frontend, text: frontend.phonemize(text, Stages(chunk="sentence")),
    "clause": lambda frontend, text: frontend.phonemize(text, Stages(chunk="clause")),
    "paragraph": lambda frontend, text: frontend.phonemize(text, Stages(chunk="paragraph")),
    "none": lambda frontend, text: frontend.phonemize(text, Stages(chunk="none")),
}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("backend", BACKENDS)
def test_no_stage_input_starts_or_ends_with_whitespace(monkeypatch, backend, path):
    frontend, received = _recording_frontend(monkeypatch, BACKENDS[backend]())
    PATHS[path](frontend, TEXT)
    assert {stage for stage, _ in received} >= {"casing", "diacritize"}
    assert [(stage, text) for stage, text in received if text != text.strip()] == []


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_text_between_blocks_reaches_each_stage_without_its_edges(monkeypatch, backend):
    frontend, received = _recording_frontend(monkeypatch, BACKENDS[backend]())
    frontend.phonemize("[[ab]]  one  [[cd]]  two.  [[ef]]  ")
    assert {text for stage, text in received if stage == "diacritize"} >= {"one", "two."}
    assert [(stage, text) for stage, text in received if text != text.strip()] == []



WHITESPACE = {"tab": "\t", "no-break space": "\u00a0", "ideographic space": "\u3000", "crlf": "\r\n"}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("space", WHITESPACE)
def test_every_kind_of_whitespace_stays_out_of_the_stages(monkeypatch, space, path):
    edge = WHITESPACE[space]
    text = f"{edge}I have{edge}[[ab]]{edge}three cats.{edge}Yes{edge}[[cd]]{edge}"
    frontend, received = _recording_frontend(monkeypatch, Echo())
    PATHS[path](frontend, text)
    assert {text for stage, text in received if stage == "diacritize"} >= {"I have", "three cats.", "Yes"}
    assert [(stage, text) for stage, text in received if text != text.strip()] == []


@pytest.mark.parametrize("text", ["Jan. [[ab]]\n5 to Dec. 25.", "Mr. [[ab]]. and Mrs. Jones met Prof. Lee."])
def test_a_text_with_no_blank_line_is_one_paragraph_chunk_around_a_block(monkeypatch, text):
    frontend, _ = _recording_frontend(monkeypatch, Echo())
    assert len(frontend.phonemize(text, Stages(chunk="paragraph"))) == 1


@pytest.mark.parametrize("text, staged", [(" \tab \r\n", " \tAB \r\n"), ("　ab", "　AB"), ("ab ", "AB "),
                                          ("ab", "AB"), (" \n\t", " \n\t"), ("", "")])
def test_a_stage_reads_the_core_and_the_edges_go_back_around_the_result(text, staged):
    received = []

    def upper(core):
        received.append(core)
        return core.upper()

    frontend = TextFrontend(FrontendConfig("en-US"), Echo())
    assert frontend._stage("casing", frontend._resolve(None), upper, text) == staged
    assert received == ([text.strip()] if text.strip() else [])
