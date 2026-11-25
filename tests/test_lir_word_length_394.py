"""Kolokwa refuses a spelling that is longer than its id buffer before it calls ONNX."""
import numpy as np
import pytest

from scriptconv.phonemizers import lir
from scriptconv.phonemizers.lir import KolokwaPhonemizer


class FakeSession:
    """Records the ids sent to the model and returns one end symbol per position."""

    def __init__(self):
        self.calls = 0
        self.ids = None

    def run(self, _inputs, feeds):
        self.calls += 1
        ids = feeds["text"][0]
        self.ids = list(ids)
        logits = np.zeros((len(ids), 6))
        logits[:, 5] = 1
        return [logits[None, :, :]]


def backend(monkeypatch):
    monkeypatch.setattr(lir, "_MAX_MODEL_IDS", 11)
    inst = KolokwaPhonemizer.__new__(KolokwaPhonemizer)
    inst.text_tokens = {c: i + 3 for i, c in enumerate("abcde")}
    inst.char_repeats = 2
    inst.text_start = 1
    inst.text_end = 2
    inst.phoneme_end = 5
    inst.phonemes = [""] * 6
    inst.phonemes[5] = "#"
    inst.special = {"#"}
    inst.session = FakeSession()
    return inst


def test_a_spelling_that_fits_reaches_the_model(monkeypatch):
    inst = backend(monkeypatch)
    assert inst._predict("abcd") == ""
    assert inst.session.ids == [1] + [3, 3, 4, 4, 5, 5, 6, 6] + [2]
    assert inst.session.calls == 1


def test_a_longer_spelling_raises_before_the_model_call(monkeypatch):
    inst = backend(monkeypatch)
    with pytest.raises(ValueError, match="at most 4 letters in one spelling, got 5"):
        inst._predict("abcde")
    assert inst.session.calls == 0


def test_the_exported_graph_uses_a_5000_id_buffer():
    assert lir._MAX_MODEL_IDS == 5000
