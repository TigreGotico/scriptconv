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
    "phonemize": lambda frontend: frontend.phonemize(TEXT),
    "phonemize_lazy": lambda frontend: list(frontend.phonemize_lazy(TEXT)),
    "phonemize_flat": lambda frontend: frontend.phonemize_flat(TEXT),
    "sentence": lambda frontend: frontend.phonemize(TEXT, Stages(chunk="sentence")),
    "clause": lambda frontend: frontend.phonemize(TEXT, Stages(chunk="clause")),
    "paragraph": lambda frontend: frontend.phonemize(TEXT, Stages(chunk="paragraph")),
    "none": lambda frontend: frontend.phonemize(TEXT, Stages(chunk="none")),
}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("backend", BACKENDS)
def test_no_stage_input_starts_or_ends_with_whitespace(monkeypatch, backend, path):
    frontend, received = _recording_frontend(monkeypatch, BACKENDS[backend]())
    PATHS[path](frontend)
    assert {stage for stage, _ in received} >= {"casing", "diacritize"}
    assert [(stage, text) for stage, text in received if text != text.strip()] == []


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_text_between_blocks_reaches_each_stage_without_its_edges(monkeypatch, backend):
    frontend, received = _recording_frontend(monkeypatch, BACKENDS[backend]())
    frontend.phonemize("[[ab]]  one  [[cd]]  two.  [[ef]]  ")
    assert {text for stage, text in received if stage == "diacritize"} >= {"one", "two."}
    assert [(stage, text) for stage, text in received if text != text.strip()] == []
