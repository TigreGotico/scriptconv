"""The chunk size of TextFrontend, and the whole-text read of an owner backend.

The size moves only the cuts: the stage order is the same at every size, and
the clause symbols join two chunks the same way at every size.
"""
import re

import pytest

from scriptconv import frontend as frontend_module
from scriptconv.frontend import FRONTEND_VERSION, WHOLE_TEXT_LIMIT, Chunk, FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import Alphabet, BasePhonemizer, GraphemePhonemizer, Segment
from scriptconv.phonemizers.base import join_sentences
from scriptconv.phonemizers.dizione import DizionePhonemizer


class Echo(BasePhonemizer):
    """Phonemes are the characters of the text. Each text read is recorded."""

    def __init__(self, events=None):
        super().__init__(Alphabet.IPA)
        self.events = [] if events is None else events

    def phonemize_string(self, text, lang):
        self.events.append(("backend", text))
        return text


class WholeText(Echo):
    """An owner backend that reads whole text: a segment per word, a sentence at each ".".

    A sentence that a blank line follows ends a paragraph.
    """

    owned_stages = frozenset({"normalize"})
    reads_whole_text = True

    def phonemize_segments(self, text, lang):
        self.events.append(("segments", text))
        for match in re.finditer(r"(\S+)(\s*)", text):
            word, space = match.groups()
            mark = word[-1] if word[-1] in ".,?" else None
            ends_sentence = mark in (".", "?")
            yield Segment(tuple(word.rstrip(".,?")), mark, ends_sentence,
                          ends_paragraph=ends_sentence and space.count("\n") > 1)


def build(backend, keep=False, **config):
    return TextFrontend(FrontendConfig("xx", keep_punctuation=keep, **config), backend)


def chunks(frontend, text, chunk):
    return ["".join(phonemes) for phonemes in frontend.phonemize(text, Stages(chunk=chunk))]


TEXT = "Um, dois. Três quatro.\n\nCinco seis."


class TestChunkBoundaries:
    @pytest.mark.parametrize("chunk, keep, expected", [
        (Chunk.SENTENCE, True, ["Um, dois.", "Três quatro.", "Cinco seis."]),
        (Chunk.CLAUSE, True, ["Um, ", "dois.", "Três quatro.", "Cinco seis."]),
        (Chunk.PARAGRAPH, True, ["Um, dois.Três quatro.", "Cinco seis."]),
        (Chunk.NONE, True, ["Um, dois.Três quatro.Cinco seis."]),
        (Chunk.SENTENCE, False, ["Um dois", "Três quatro", "Cinco seis"]),
        (Chunk.CLAUSE, False, ["Um", "dois", "Três quatro", "Cinco seis"]),
        (Chunk.PARAGRAPH, False, ["Um dois Três quatro", "Cinco seis"]),
        (Chunk.NONE, False, ["Um dois Três quatro Cinco seis"]),
    ])
    def test_each_size_cuts_where_the_contract_says(self, chunk, keep, expected):
        assert chunks(build(Echo(), keep), TEXT, chunk) == expected

    @pytest.mark.parametrize("chunk, keep, expected", [
        (Chunk.SENTENCE, True, ["Um, dois.", "Três quatro.", "Cinco seis."]),
        (Chunk.CLAUSE, True, ["Um, ", "dois.", "Três", "quatro.", "Cinco", "seis."]),
        (Chunk.PARAGRAPH, True, ["Um, dois.Três quatro.", "Cinco seis."]),
        (Chunk.NONE, True, ["Um, dois.Três quatro.Cinco seis."]),
        (Chunk.CLAUSE, False, ["Um", "dois", "Três", "quatro", "Cinco", "seis"]),
        (Chunk.NONE, False, ["Um dois Três quatro Cinco seis"]),
    ])
    def test_a_whole_text_backend_is_grouped_by_the_same_rules(self, chunk, keep, expected):
        assert chunks(build(WholeText(), keep), TEXT, chunk) == expected

    def test_the_frontend_size_holds_when_the_call_sets_none(self):
        frontend = build(Echo(), stages=Stages(chunk=Chunk.NONE))
        assert frontend.phonemize("Um gato. Dois.") == [list("Um gato Dois")]
        assert frontend.phonemize("Um gato. Dois.", Stages(chunk=Chunk.SENTENCE)) == [
            list("Um gato"), list("Dois")]


class TestTheSizeMovesOnlyTheCuts:
    TEXTS = ["Um, dois. Três quatro.", "Olá! Tudo bem? Sim.", "Espera... vamos.",
             "Um; dois: três. Quatro, cinco.\n\nSeis."]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", TEXTS)
    @pytest.mark.parametrize("backend", [Echo, GraphemePhonemizer, WholeText])
    def test_none_is_the_sentences_joined(self, backend, text, keep):
        frontend = build(backend(), keep)
        whole = frontend.phonemize(text, Stages(chunk=Chunk.NONE))
        assert whole == [join_sentences(frontend.phonemize(text), keep)]
        assert whole == [frontend.phonemize_flat(text)]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Hello, world. Mrs. Jones came; then she left.\n\nBye now.",
                                      "Jan. 1, 2000", "See p. 12 and No. 5. Why? Because."])
    def test_dizione_none_is_the_sentences_joined(self, text, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), DizionePhonemizer())
        whole = frontend.phonemize(text, Stages(chunk=Chunk.NONE))
        assert whole == [join_sentences(frontend.phonemize(text), keep)]
        assert whole == [frontend.phonemize_flat(text)]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Um, dois. Três quatro.", "Um; dois: três. Quatro, cinco."])
    def test_clauses_joined_are_the_sentences_when_no_sentence_mark_is_inside(self, text, keep):
        frontend = build(Echo(), keep)
        clauses = frontend.phonemize(text, Stages(chunk=Chunk.CLAUSE))
        assert join_sentences(clauses, keep) == join_sentences(frontend.phonemize(text), keep)


class TestStreamingOrder:
    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Um, dois. Três quatro.", "Olá! Tudo bem? Sim.",
                                      "Espera... vamos. Agora: já."])
    def test_sentence_chunks_are_the_backend_sentences(self, text, keep):
        # phoonnx streams the sentences of the backend's phonemize_lazy
        backend = GraphemePhonemizer()
        backend.keep_punctuation = keep
        frontend = build(GraphemePhonemizer(), keep)
        assert frontend.phonemize(text, Stages(chunk=Chunk.SENTENCE)) == [
            sentence for sentence in backend.phonemize(text, "xx") if sentence]

    @pytest.mark.parametrize("chunk, first", [
        (Chunk.SENTENCE, [("diacritize", "Um, dois."), ("backend", "Um"), ("backend", "dois")]),
        (Chunk.CLAUSE, [("diacritize", "Um, "), ("backend", "Um")]),
    ])
    def test_chunk_two_is_read_after_chunk_one_is_yielded(self, monkeypatch, chunk, first):
        events = []

        def diacritize(text, lang, diacritizer_model=None):
            events.append(("diacritize", text))
            return text

        monkeypatch.setattr(frontend_module, "diacritize", diacritize)
        frontend = build(Echo(events), True, stages=Stages(diacritize=True))
        lazy = frontend.phonemize_lazy("Um, dois. Três.", Stages(chunk=chunk))
        next(lazy)
        assert events == first
        list(lazy)
        assert events[-2:] == [("diacritize", "Três."), ("backend", "Três")]


class TestWholeTextLimit:
    def test_the_default_is_the_module_limit(self):
        assert FrontendConfig("xx").whole_text_limit == WHOLE_TEXT_LIMIT

    def test_above_the_limit_the_text_is_cut_at_paragraph_breaks(self):
        backend = WholeText()
        frontend = build(backend, whole_text_limit=10)
        assert chunks(frontend, "Um dois.\n \n\nTrês quatro.", Chunk.SENTENCE) == ["Um dois", "Três quatro"]
        assert [event for event in backend.events if event[0] == "segments"] == [
            ("segments", "Um dois."), ("segments", "Três quatro.")]

    @pytest.mark.parametrize("limit", [None, 100])
    def test_at_or_under_the_limit_the_text_is_read_whole(self, limit):
        backend = WholeText()
        frontend = build(backend, whole_text_limit=limit)
        frontend.phonemize("Um dois.\n\nTrês quatro.")
        assert [event for event in backend.events if event[0] == "segments"] == [
            ("segments", "Um dois.\n\nTrês quatro.")]

    def test_dizione_reads_a_paragraph_break_as_no_sentence_end_unless_it_is_cut(self):
        text = "The title\n\nThe body is here."
        whole = TextFrontend(FrontendConfig("en-US", whole_text_limit=None), DizionePhonemizer())
        cut = TextFrontend(FrontendConfig("en-US", whole_text_limit=5), DizionePhonemizer())
        assert len(whole.phonemize(text)) == 1
        assert len(cut.phonemize(text)) == 2
        assert " ".join("".join(c) for c in cut.phonemize(text)) == "".join(whole.phonemize(text)[0])


class TestWholeTextBackends:
    def test_the_base_class_does_not_read_whole_text(self):
        assert BasePhonemizer.reads_whole_text is False
        backend = GraphemePhonemizer()
        assert [segment.phonemes for segment in backend.phonemize_segments("Um dois. Três.", "xx")] == [
            tuple(sentence) for sentence in backend.phonemize_lazy("Um dois. Três.", "xx")]

    def test_a_whole_text_backend_gives_its_own_segments(self):
        class Whole(GraphemePhonemizer):
            reads_whole_text = True

        with pytest.raises(NotImplementedError):
            next(Whole().phonemize_segments("a", "xx"))

    def test_a_segment_is_frozen(self):
        segment = Segment(("a",), ".", True, {"stress": (0,)})
        with pytest.raises(AttributeError):
            segment.mark = ","

    @pytest.mark.parametrize("keep, expected", [
        (True, ["həlˈoʊ, wˈɜːld.", "həlˈoʊ wˈɜːld!"]),
        (False, ["həlˈoʊ wˈɜːld", "həlˈoʊ wˈɜːld"]),
    ])
    def test_dizione_gets_the_clause_symbols_of_its_own_marks(self, keep, expected):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), DizionePhonemizer())
        assert ["".join(c) for c in frontend.phonemize("Hello, world. Hello world!")] == expected

    def test_the_identity_carries_the_frontend_version(self):
        identity = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer()).identity()
        assert identity.frontend == FRONTEND_VERSION == 2
        assert DizionePhonemizer().identity("en-US").frontend is None
        assert identity.differs_from(DizionePhonemizer().identity("en-US")) == ("frontend",)
