"""One join rule at every chunk size, and the whole text read first at every size.

The chunks of every size, joined by the rule of tts-punctuation, are the
sentence chunks joined: that join is ``phonemize_flat``, and the ``none`` size
gives it as its one chunk. A paragraph chunk groups the sentences after the
read, so a full stop that belongs to the reading ends no paragraph.
"""
import re

import pytest

from scriptconv.frontend import (
    WHOLE_TEXT_LIMIT,
    Chunk,
    FrontendConfig,
    Stages,
    TextFrontend,
    spoken_normalizer,
)
from scriptconv.phonemizers import (
    Alphabet,
    BasePhonemizer,
    GraphemePhonemizer,
    Segment,
    UnicodeCodepointPhonemizer,
)
from scriptconv.phonemizers.base import join_sentences
from scriptconv.phonemizers.dizione import DizionePhonemizer
from scriptconv.phonemizers.enums import Phonemizer

SIZES = [Chunk.SENTENCE, Chunk.CLAUSE, Chunk.PARAGRAPH, Chunk.NONE]


def joined(frontend, text, chunk, keep):
    """The chunks of one size joined by the rule of tts-punctuation."""
    return join_sentences(frontend.phonemize(text, Stages(chunk=chunk)), keep)


class Words(BasePhonemizer):
    """A backend that keeps every space it reads, as Vosk keeps them as tokens."""

    def __init__(self):
        super().__init__(Alphabet.IPA)

    def phonemize_lazy(self, text, lang):
        yield list(text)

    def phonemize_string(self, text, lang):
        return text


class WholeText(BasePhonemizer):
    """An owner backend that reads whole text: a segment per word, a sentence at each ".".

    Each text it reads is recorded.
    """

    owned_stages = frozenset({"normalize"})
    reads_whole_text = True

    def __init__(self):
        super().__init__(Alphabet.IPA)
        self.read = []

    def phonemize_string(self, text, lang):
        return text

    def phonemize_segments(self, text, lang):
        self.read.append(text)
        for match in re.finditer(r"(\S+)(\s*)", text):
            word, space = match.groups()
            mark = word[-1] if word[-1] in ".,?!" else None
            ends_sentence = mark in (".", "?", "!")
            yield Segment(tuple(word.rstrip(".,?!")), mark, ends_sentence,
                          {"level": tuple(range(len(word.rstrip(".,?!"))))},
                          ends_paragraph=ends_sentence and space.count("\n") > 1)


class Bounded(WholeText):
    """A whole-text backend whose segments carry their own start and end symbols."""

    def phonemize_segments(self, text, lang):
        for segment in super().phonemize_segments(text, lang):
            yield Segment(("<s>", *segment.phonemes, *(segment.mark or ""), "</s>"), None,
                          segment.ends_sentence,
                          {"level": (9, *segment.streams["level"], *(0,) * len(segment.mark or ""), 9)},
                          segment.ends_paragraph, bounded=True)


@pytest.fixture(scope="module")
def dizione():
    return DizionePhonemizer()


class TestParagraphsAfterTheRead:
    """F1: a paragraph chunk groups the sentences of the whole read text."""

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text, reading", [
        ("Call Dr.\n\nSmith now.", "dˈɑːktɚ"),
        ("We met on Jan.\n\n5 at noon.", "fˈɪfθ"),
    ])
    def test_dizione_reads_the_full_stop_of_an_abbreviation_at_every_size(self, dizione, text,
                                                                         reading, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        sentences = joined(frontend, text, Chunk.SENTENCE, keep)
        assert reading in "".join(sentences).split()
        for chunk in SIZES:
            assert joined(frontend, text, chunk, keep) == sentences
        assert frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH)) == [sentences]

    @pytest.mark.parametrize("keep", [True, False])
    def test_dizione_cuts_a_paragraph_where_a_sentence_ends_before_a_blank_line(self, dizione, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        text = 'A cat sat.\n\nA dog ran. "It was late."\n\n\nThe end'
        one, two, three, four = frontend.phonemize(text)
        assert frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH)) == [
            one, join_sentences([two, three], keep), four]

    def test_a_whole_text_backend_reads_the_whole_text_once_at_paragraph_size(self):
        backend = WholeText()
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True), backend)
        text = "Um dois.\n\nTrês quatro."
        assert ["".join(chunk) for chunk in frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH))] == [
            "Um dois.", "Três quatro."]
        assert backend.read == [text]

    def test_any_other_backend_gets_the_whole_text_normalised_then_the_paragraph_cut(self):
        hook = spoken_normalizer()
        frontend = TextFrontend(FrontendConfig("en", normalizer=hook, stages=Stages(diacritize=False)),
                                GraphemePhonemizer())
        assert frontend.phonemize("Prof.\n\nSmith arrived.", Stages(chunk=Chunk.PARAGRAPH)) == \
            frontend.phonemize("Prof.\n\nSmith arrived.", Stages(chunk=Chunk.NONE))


class TestClausesJoinAsTheSentence:
    """F2 and F6: clause chunks joined are the sentence, for every backend."""

    TEXTS = ["She reads books! The road is long. It was late.",
             "Olá! Tudo bem? Sim.",
             "Dr Smith called; they won 3 games | Dr Smith called! Wait… go.",
             "Um, dois: três; quatro. Cinco?! Seis."]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", TEXTS)
    @pytest.mark.parametrize("backend", [GraphemePhonemizer, UnicodeCodepointPhonemizer, Words])
    def test_the_clauses_joined_are_the_sentences_joined(self, backend, text, keep):
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=keep,
                                               stages=Stages(diacritize=False)), backend())
        assert joined(frontend, text, Chunk.CLAUSE, keep) == joined(frontend, text, Chunk.SENTENCE, keep)

    @pytest.mark.parametrize("text", TEXTS)
    @pytest.mark.parametrize("backend", [GraphemePhonemizer, UnicodeCodepointPhonemizer, Words])
    def test_no_clause_starts_with_a_space_or_holds_a_bar(self, backend, text):
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True,
                                               stages=Stages(diacritize=False)), backend())
        clauses = frontend.phonemize(text, Stages(chunk=Chunk.CLAUSE))
        assert not any(clause[0] == " " for clause in clauses)
        if backend is not Words:
            assert "|" not in "".join(map("".join, clauses))

    def test_a_space_follows_an_exclamation_mark_inside_a_sentence(self):
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True,
                                               stages=Stages(diacritize=False)), GraphemePhonemizer())
        assert ["".join(c) for c in frontend.phonemize("She reads books! The road is long.",
                                                       Stages(chunk=Chunk.CLAUSE))] == [
            "she reads books! ", "the road is long."]

    def test_a_whole_text_clause_symbol_inside_a_sentence_takes_a_space(self):
        class Exclaims(WholeText):
            def phonemize_segments(self, text, lang):
                yield Segment(("a",), "!", False)
                yield Segment(("b",), ".", True)

        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True), Exclaims())
        assert frontend.phonemize("a! b.") == [["a", "!", " ", "b", "."]]

    @pytest.mark.parametrize("keep", [True, False])
    def test_dizione_writes_a_space_after_a_pause_mark(self, dizione, keep):
        off = "".join(TextFrontend(FrontendConfig("en-US"), dizione).phonemize("Hello, world.")[0])
        first, second = off.split()
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        assert ["".join(chunk) for chunk in frontend.phonemize("Hello, world.")] == [
            f"{first}, {second}." if keep else off]

    def test_a_pause_mark_at_a_sentence_end_takes_a_space_as_on_every_backend(self, dizione):
        text = "Hello, world,"
        graphemes = TextFrontend(FrontendConfig("en", keep_punctuation=True), GraphemePhonemizer())
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=True), dizione)
        assert graphemes.phonemize(text)[-1][-2:] == [",", " "]
        assert frontend.phonemize(text)[-1][-2:] == [",", " "]

    @pytest.mark.parametrize("chunk", SIZES)
    def test_no_vosk_chunk_starts_with_a_space_after_a_block(self, chunk):
        frontend = TextFrontend(FrontendConfig("ru-RU", Phonemizer("vosk"), alphabet=Alphabet("vosk"),
                                               stages=Stages(diacritize=False)))
        chunks = frontend.phonemize("Всё [[ab]] хорошо? Дом большой.\n\nИди сюда.", Stages(chunk=chunk))
        assert len(chunks) > 1 or chunk == Chunk.NONE
        assert not any(chunk[0] == " " for chunk in chunks)

    @pytest.mark.parametrize("keep", [True, False])
    def test_whole_text_clauses_joined_are_the_sentences_joined(self, dizione, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        text = "Really? Yes, I think so! Mrs. Jones came; she left. Bye"
        assert joined(frontend, text, Chunk.CLAUSE, keep) == joined(frontend, text, Chunk.SENTENCE, keep)


class TestTrainingReadsTheSentencePath:
    """F3: flat and none are the sentence chunks joined, for the backends that override."""

    CASES = [("pypinyin", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
             ("xpinyin", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
             ("g2pm", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
             ("shami", "ar", None, "مرحبا بك. كيف حالك؟ أنا بخير"),
             ("vosk", "ru-RU", "vosk", "Кот спит.\n\nМы пошли домой! Дом большой, иди сюда")]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("name, lang, alphabet, text", CASES)
    def test_flat_and_none_are_the_sentences_joined(self, name, lang, alphabet, text, keep):
        frontend = TextFrontend(FrontendConfig(
            lang, Phonemizer(name), alphabet=Alphabet(alphabet) if alphabet else Alphabet.IPA,
            keep_punctuation=keep, stages=Stages(diacritize=False)))
        sentences = frontend.phonemize(text)
        assert len(sentences) > 1
        flat = frontend.phonemize_flat(text)
        # an overriding backend appends no clause symbol, so its sentences join with a space
        assert flat == join_sentences(sentences, keep_punctuation=False)
        assert frontend.phonemize(text, Stages(chunk=Chunk.NONE)) == [flat]

    @pytest.mark.parametrize("name", ["pypinyin", "xpinyin", "g2pm"])
    def test_a_full_width_mark_keeps_the_word_break_of_the_whole_text_read(self, name):
        text = "下了一整天雨？猫在睡觉、她在看书"
        frontend = TextFrontend(FrontendConfig("zh-CN", Phonemizer(name), stages=Stages(diacritize=False)))
        # the backend's own whole-text read keeps each mark as a word, and the words around it
        whole = "".join(frontend.backend.phonemize_to_list(text, "zh")).split()
        words = [word for word in whole if word not in ("？", "、")]
        assert "".join(frontend.phonemize_flat(text)).split() == words


class TestChunkValues:
    """F4: a string value of Chunk is the Chunk."""

    @pytest.mark.parametrize("chunk", list(Chunk))
    def test_a_string_value_reads_as_the_chunk(self, chunk):
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True,
                                               stages=Stages(diacritize=False)), GraphemePhonemizer())
        text = "Um, dois. Três quatro.\n\nCinco seis."
        assert Stages(chunk=chunk.value).chunk is chunk
        assert frontend.phonemize(text, Stages(chunk=chunk.value)) == frontend.phonemize(text, Stages(chunk=chunk))

    def test_an_unknown_value_raises(self):
        with pytest.raises(ValueError):
            Stages(chunk="word")


class TestEmptyBlocks:
    """F5: the hook reads across an empty block at every size."""

    @pytest.mark.parametrize("chunk", SIZES)
    @pytest.mark.parametrize("text, reading", [("Prof.[[]] Smith arrived.", "professor"),
                                               ("Mr.[[ ]] Jones came.", "mister")])
    def test_an_empty_block_reads_as_no_text(self, chunk, text, reading):
        frontend = TextFrontend(FrontendConfig("en", normalizer=spoken_normalizer(),
                                               stages=Stages(diacritize=False)), GraphemePhonemizer())
        assert "".join(frontend.phonemize(text, Stages(chunk=chunk))[0]).split()[0] == reading


class TestDizioneMarks:
    """F7: the tts-punctuation marks in dizione's segments."""

    @pytest.mark.parametrize("keep", [True, False])
    def test_a_mark_between_two_letters_is_a_space(self, dizione, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        assert ["".join(chunk) for chunk in frontend.phonemize("Sim!Não!")] == [
            "sˈɪm nˈaʊ!" if keep else "sˈɪm nˈaʊ"]
        assert "!" not in dizione.tokens("Sim!Não!").symbols[:-2]

    @pytest.mark.parametrize("text, first", [
        ('She said "Stop." Then he left.', ("<bos>", "ʃ", "iː", "<sp>", "s", "ɛ", "d", '"', "s", "t", "ɑː",
                                             "p", ".", '"', "<eos>")),
        ("He asked (why?) and left.", ("<bos>", "h", "iː", "<sp>", "æ", "s", "k", "t", "(", "w", "aɪ", "?",
                                       ")", "<eos>")),
    ])
    def test_a_closing_mark_stays_with_the_sentence_that_ends(self, dizione, text, first):
        sentences = dizione.token_segments(text)
        assert sentences[0].symbols == first
        assert sentences[1].symbols[1] not in ('"', ")", "'")

    @pytest.mark.parametrize("text, starts", [
        ('It was late." The cat sat down.', ["ɪ", "ð"]),
        ('"Go!" he said. "Now?" I asked.', ['"', "h", '"', "aɪ"]),
        ('He said “Stop.” Then left.', ["h", "ð"]),
    ])
    def test_the_text_tells_a_closing_quote_from_an_opening_one(self, dizione, text, starts):
        assert [sentence.symbols[1] for sentence in dizione.token_segments(text)] == starts


class TestSegmentsAndStreams:
    """F8: the frontend groups the segments and keeps the streams in step at every size."""

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", SIZES)
    def test_dizione_stress_stays_in_step(self, dizione, chunk, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), dizione)
        text = "Hello, world! Mrs. Jones came.\n\nBye now; see you."
        segments = list(frontend.segments(text, Stages(chunk=chunk)))
        assert [list(segment.phonemes) for segment in segments] == frontend.phonemize(text, Stages(chunk=chunk))
        for segment in segments:
            assert len(segment.streams["stress"]) == len(segment.phonemes)
            # a stress mark and the vowel after it carry the stress, every other character 0
            stressed = {i for i, s in enumerate(segment.phonemes) if s in "ˈˌ"}
            assert all(segment.streams["stress"][i] > 0 for i in stressed)
            assert all(level == 0 for symbol, level in zip(segment.phonemes, segment.streams["stress"])
                       if symbol in " ,.!;")

    def test_dizione_tokens_per_chunk_are_its_token_sequence(self):
        backend = DizionePhonemizer(tokens=True)
        frontend = TextFrontend(FrontendConfig("en-US"), backend)
        text = 'Hello, world! "Stop." Mrs. Jones came.\n\nBye now; see you.'
        sentences = list(frontend.segments(text))
        assert [(s.phonemes, s.streams["ids"], s.streams["stress"]) for s in sentences] == [
            (t.symbols, t.ids, t.stress) for t in backend.token_segments(text)]
        whole = backend.tokens(text)
        assert [(s.phonemes, s.streams["ids"], s.streams["stress"])
                for s in frontend.segments(text, Stages(chunk=Chunk.NONE))] == [
            (whole.symbols, whole.ids, whole.stress)]
        for chunk in SIZES:
            for segment in frontend.segments(text, Stages(chunk=chunk)):
                assert segment.phonemes[0] == "<bos>" and segment.phonemes[-1] == "<eos>"
                assert segment.phonemes.count("<bos>") == segment.phonemes.count("<eos>") == 1
                assert len(segment.streams["ids"]) == len(segment.streams["stress"]) == len(segment.phonemes)

    @pytest.mark.parametrize("chunk, expected", [
        (Chunk.CLAUSE, [(("<s>", "U", "m", ",", "</s>"), (9, 0, 1, 0, 9)),
                        (("<s>", "d", "o", "i", "s", ".", "</s>"), (9, 0, 1, 2, 3, 0, 9)),
                        (("<s>", "t", "r", "ê", "s", ".", "</s>"), (9, 0, 1, 2, 3, 0, 9))]),
        (Chunk.SENTENCE, [(("<s>", "U", "m", ",", "d", "o", "i", "s", ".", "</s>"), (9, 0, 1, 0, 0, 1, 2, 3, 0, 9)),
                          (("<s>", "t", "r", "ê", "s", ".", "</s>"), (9, 0, 1, 2, 3, 0, 9))]),
        (Chunk.PARAGRAPH, [(("<s>", "U", "m", ",", "d", "o", "i", "s", ".", "</s>"), (9, 0, 1, 0, 0, 1, 2, 3, 0, 9)),
                           (("<s>", "t", "r", "ê", "s", ".", "</s>"), (9, 0, 1, 2, 3, 0, 9))]),
        (Chunk.NONE, [(("<s>", "U", "m", ",", "d", "o", "i", "s", ".", "t", "r", "ê", "s", ".", "</s>"),
                       (9, 0, 1, 0, 0, 1, 2, 3, 0, 0, 1, 2, 3, 0, 9))]),
    ])
    def test_inner_start_and_end_symbols_go_with_their_stream_values(self, chunk, expected):
        frontend = TextFrontend(FrontendConfig("xx"), Bounded())
        assert [(s.phonemes, s.streams["level"])
                for s in frontend.segments("Um, dois.\n\ntrês.", Stages(chunk=chunk))] == expected


class TestWholeTextLimitEdges:
    """F9: the limit is off with None, and the text at the limit is read whole."""

    def test_none_reads_a_text_longer_than_the_default_limit_whole(self):
        backend = WholeText()
        frontend = TextFrontend(FrontendConfig("xx", whole_text_limit=None), backend)
        text = "\n\n".join(["Um dois."] * (WHOLE_TEXT_LIMIT // 8))
        assert len(text) > WHOLE_TEXT_LIMIT
        frontend.phonemize(text)
        assert backend.read == [text]

    @pytest.mark.parametrize("extra, reads", [(0, 1), (1, 2)])
    def test_a_text_at_the_limit_is_read_whole(self, extra, reads):
        text = "Um dois.\n\nTrês quatro."
        backend = WholeText()
        frontend = TextFrontend(FrontendConfig("xx", whole_text_limit=len(text) - extra), backend)
        frontend.phonemize(text)
        assert len(backend.read) == reads
