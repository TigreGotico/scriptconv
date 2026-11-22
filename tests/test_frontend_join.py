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
from scriptconv.phonemizers._thirdparty.dizione.symbols import SYMBOL_TO_ID
from scriptconv.phonemizers.base import join_sentences
from scriptconv.phonemizers.dizione import DizionePhonemizer
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.shami import ShamiPhonemizer

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
            yield Segment(("<s>", *segment.phonemes, *(segment.mark or ""), "</s>"), segment.mark,
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
        text = "Prof.\n\nSmith arrived."
        paragraphs = hook(text, "en").split("\n\n")
        assert len(paragraphs) == 2
        assert frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH)) == [
            GraphemePhonemizer().phonemize_to_list(paragraph, "en") for paragraph in paragraphs]


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
        # a lower-case word after the "!" keeps one sentence
        assert ["".join(c) for c in frontend.phonemize("She reads books! the road is long.",
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


class TestSentencesJoinAsTheTextWrites:
    """A sentence that ends with no clause symbol takes a space before the
    next sentence only where the text writes whitespace between them.

    The sentence split here ends a sentence after ``。！？`` with no space
    after it, as Chinese and Japanese write it, so the rows do not depend on
    the installed quebra-frases."""

    @pytest.fixture(autouse=True)
    def cjk_sentence_split(self, monkeypatch):
        import quebra_frases
        monkeypatch.setattr(quebra_frases, "sentence_tokenize",
                            lambda text: re.split(r"(?<=[。！？])(?=\S)|(?<=[.?!。！？])\s+", text))

    @pytest.mark.parametrize("backend", [GraphemePhonemizer, UnicodeCodepointPhonemizer])
    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text, expected", [
        ("你好！我们走。", "你好我们走"),
        ("我有三本书。你有几本？太好了！", "我有三本书你有几本太好了"),
        # whitespace in the text keeps the space
        ("你好！ 我们走。", "你好 我们走"),
        ("你好！\n我们走。", "你好 我们走"),
        # the whitespace before the first word counts, also after a mark
        ("你好！' 我们走。", "你好 我们走"),
        ("你好！「我们走」", "你好我们走"),
    ])
    def test_flat_streams(self, backend, keep, text, expected):
        frontend = TextFrontend(FrontendConfig("zh", keep_punctuation=keep,
                                               stages=Stages(diacritize=False)), backend())
        assert "".join(frontend.backend.phonemize_to_list(text, "zh")) == expected
        assert "".join(frontend.phonemize_flat(text)) == expected
        assert ["".join(c) for c in frontend.phonemize(text, Stages(chunk=Chunk.NONE))] == [expected]

    @pytest.mark.parametrize("text", ["你好！我们走。", "你好！ 我们走。"])
    def test_the_chunk_text_keeps_the_gap(self, text):
        frontend = TextFrontend(FrontendConfig("zh", keep_punctuation=True,
                                               stages=Stages(diacritize=False)), GraphemePhonemizer())
        assert [s.text for s in frontend.segments(text, Stages(chunk=Chunk.NONE))] == [text]


class TestTrainingReadsTheSentencePath:
    """F3: flat and none are the sentence chunks joined, for the backends that override."""

    CASES = [("pypinyin", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
             ("xpinyin", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
             ("g2pm", "zh-CN", None, "我很好. 猫在睡觉! 你好, 我们回家了"),
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

    @pytest.mark.parametrize("chunk", [Chunk.CLAUSE, Chunk.PARAGRAPH])
    def test_flat_reads_sentences_whatever_the_chunk_size_of_the_call(self, chunk):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer("orthography2ipa"), stages=Stages(diacritize=False)))
        text = "Ela lê livros… vem cá.\n\nO gato dorme."
        flat = frontend.phonemize_flat(text)
        assert frontend.phonemize_flat(text, Stages(chunk=chunk)) == flat
        # the clauses read alone give another word at the cut, so the size of the read shows
        assert join_sentences(frontend.phonemize(text, Stages(chunk=Chunk.CLAUSE)), False) != flat

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


    @pytest.mark.parametrize("text", ['He said "Stop." .\n\nThe cat sat.', 'He said "Stop.".\n\nThe cat sat.',
                                      "He asked (why?) .\n\nThe cat sat."])
    def test_a_mark_after_a_closing_mark_stays_with_the_sentence_that_ends(self, dizione, text):
        ends = [(s.ends_sentence, s.ends_paragraph) for s in dizione.phonemize_segments(text, "en-US")]
        plain = [(s.ends_sentence, s.ends_paragraph) for s in dizione.phonemize_segments("Stop.\n\nThe cat sat.", "en-US")]
        assert ends == plain == [(True, True), (True, False)]
        assert [s.symbols[1] for s in dizione.token_segments(text)] == ["h", "ð"]

    def test_no_clause_starts_with_a_mark_after_a_closing_quote(self, dizione):
        frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
        chunks = frontend.phonemize('He asked "why?", then left.', Stages(chunk=Chunk.CLAUSE))
        assert [chunk[1] for chunk in chunks] == ["h", "ð"]
        assert chunks[0][-4:] == ["?", '"', ",", "<eos>"]


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


class TestParagraphsAtBlankLines:
    """A paragraph chunk is the text between blank-line breaks, whatever ends the paragraph."""

    BODY = {"en-US": ("Come here", "Open the door now. We went home."),
            "pt-PT": ("Vem cá", "Abre a porta agora. Fomos para casa."),
            "es-ES": ("Ven aquí", "Abre la puerta ahora. Fuimos a casa."),
            "ru-RU": ("Иди сюда", "Открой дверь сейчас. Мы пошли домой.")}
    ENDINGS = ["!", "?", ".", "", ":", "…", "...", ";", "!»", '?"', ".)"]
    BACKENDS = [("graphemes", "en-US", None), ("orthography2ipa", "en-US", None),
                ("orthography2ipa", "pt-PT", None), ("graphemes", "pt-PT", None),
                ("orthography2ipa", "es-ES", None), ("orthography2ipa", "ru-RU", None),
                ("vosk", "ru-RU", "vosk")]

    @pytest.mark.parametrize("ending", ENDINGS)
    @pytest.mark.parametrize("name, lang, alphabet", BACKENDS)
    def test_each_paragraph_is_a_chunk(self, name, lang, alphabet, ending):
        frontend = TextFrontend(FrontendConfig(
            lang, Phonemizer(name), alphabet=Alphabet(alphabet) if alphabet else Alphabet.IPA,
            stages=Stages(diacritize=False)))
        first, second = self.BODY[lang]
        paragraphs = [first + ending, second]
        # the backend's own read of each paragraph alone
        expected = [frontend.backend.phonemize_to_list(paragraph, lang) for paragraph in paragraphs]
        text = "\n\n".join(paragraphs)
        assert frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH)) == expected
        sentences = frontend.phonemize(text)
        assert sentences[0] == expected[0]
        assert frontend.phonemize_flat(text) == join_sentences(sentences, keep_punctuation=False)

    @pytest.mark.parametrize("name, lang, alphabet", BACKENDS + [("dizione", "en-US", None)])
    def test_a_block_ends_a_paragraph_only_before_a_blank_line(self, name, lang, alphabet):
        frontend = TextFrontend(FrontendConfig(
            lang, Phonemizer(name), alphabet=Alphabet(alphabet) if alphabet else Alphabet.IPA,
            stages=Stages(diacritize=False)))
        first, second = self.BODY[lang]
        size = Stages(chunk=Chunk.PARAGRAPH)
        for text in (f"{first} [[ab]] {second}", f"{first} [[ab]]. {second}", f"{first} [[ab]]\n{second}"):
            assert len(frontend.phonemize(text, size)) == 1
            assert len(frontend.phonemize(text + f"\n\n{first}", size)) == 2
            assert len(frontend.phonemize(f"{first}.\n\n" + text, size)) == 2
        for text in (f"{first} [[ab]]\n\n{second}", f"{first} [[ab]].\n\n{second}", f"{first}.\n\n[[ab]] {second}",
                     f"{first}.\n\n[[cd]] [[ab]] {second}"):
            chunks = frontend.phonemize(text, size)
            assert len(chunks) == 2
            assert chunks[0][-2:] == ["a", "b"] or chunks[0][-3:-1] == ["a", "b"]


def _after(chunks, word):
    """The symbols after the first *word* in *chunks*, to the end of its chunk."""
    return next(chunk[i + len(word):] for chunk in chunks for i in range(len(chunk)) if chunk[i:i + len(word)] == word)


def _ids(frontend, text, chunk, stream):
    """The symbols and the *stream* of each chunk of *text*."""
    return [(list(segment.phonemes), list(segment.streams[stream]))
            for segment in frontend.segments(text, Stages(chunk=chunk))]


def _joined_by_the_contract(chunks, space, space_id):
    """Bounded *chunks* joined: the inner end and start symbols go with their ids, and a word break comes between."""
    symbols, ids = [chunks[0][0][0]], [chunks[0][1][0]]
    for number, (chunk_symbols, chunk_ids) in enumerate(chunks):
        if number:
            symbols.append(space)
            ids.append(space_id)
        symbols += chunk_symbols[1:-1]
        ids += chunk_ids[1:-1]
    return symbols + [chunks[-1][0][-1]], ids + [chunks[-1][1][-1]]


class TestShamiBounds:
    """Shami: a joined chunk has one ``<bos>`` and one ``<eos>``, and the language ids stay in step."""

    TEXT = "ذهب الولد إلى المدرسة، وكتب الدرس. ثم عاد إلى البيت.\n\nنام مبكرا."

    @pytest.fixture(scope="class")
    def frontend(self):
        return TextFrontend(FrontendConfig("ar", Phonemizer("shami"), stages=Stages(diacritize=False)))

    @pytest.fixture(scope="class")
    def space_id(self):
        # the language id that Shami's own front-end gives a space between two words
        utterance = ShamiPhonemizer().frontend.process("نام مبكرا")
        return utterance.language_ids[utterance.symbols.index(" ")]

    def test_each_clause_chunk_is_one_call_with_one_pair(self, frontend):
        for symbols, ids in _ids(frontend, self.TEXT, Chunk.CLAUSE, "language_ids"):
            assert (symbols[0], symbols[-1]) == ("<bos>", "<eos>")
            assert symbols.count("<bos>") == symbols.count("<eos>") == 1
            assert len(ids) == len(symbols)

    @pytest.mark.parametrize("chunk", [Chunk.NONE, Chunk.PARAGRAPH])
    def test_a_joined_chunk_is_its_clauses_joined_by_the_contract(self, frontend, space_id, chunk):
        clauses = _ids(frontend, self.TEXT, Chunk.CLAUSE, "language_ids")
        # the first paragraph holds the first three clauses
        groups = [clauses] if chunk == Chunk.NONE else [clauses[:3], clauses[3:]]
        assert _ids(frontend, self.TEXT, chunk, "language_ids") == [
            _joined_by_the_contract(group, " ", space_id) for group in groups]

    def test_flat_is_the_none_chunk_and_shamis_own_read(self, frontend):
        flat = frontend.phonemize_flat(self.TEXT)
        assert flat.count("<bos>") == flat.count("<eos>") == 1
        assert [flat] == frontend.phonemize(self.TEXT, Stages(chunk=Chunk.NONE))
        assert flat == ShamiPhonemizer().frontend.process(self.TEXT).symbols

    @pytest.mark.parametrize("chunk", SIZES)
    def test_a_block_sits_inside_the_pair_with_no_space_at_either_end(self, frontend, chunk):
        # a block ends the sentence chunk before it, so the word break after the block meets the <eos>
        for symbols, ids in _ids(frontend, "البيت [[ab]] كبير. كيف حالك؟", chunk, "language_ids"):
            assert symbols.count("<bos>") == symbols.count("<eos>") == 1
            assert " " not in (symbols[1], symbols[-2])
            assert len(ids) == len(symbols)


class TestDizioneTokensAndBlocks:
    """dizione ``tokens=True``: a block sits inside the chunk's ``<bos>`` and ``<eos>``, next to ``<sp>``."""

    @pytest.fixture(scope="class")
    def backend(self):
        return DizionePhonemizer(tokens=True)

    @staticmethod
    def _with_block(backend, text):
        """dizione's tokens of *text* with the word "x" in place of each block, the block's symbols written in."""
        whole = backend.tokens(text.replace("[[QZ]]", "x"))
        symbols, ids = list(whole.symbols), list(whole.ids)
        for _ in range(text.count("[[QZ]]")):
            place = next(i for i in range(len(symbols)) if symbols[i:i + 3] == ["ɛ", "k", "s"])
            symbols[place:place + 3], ids[place:place + 3] = ["Q", "Z"], [0, 0]
        return symbols, ids

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Hello [[QZ]] world. Bye now.", "Hi. [[QZ]] there, you. Bye.",
                                      "Hello [[QZ]], world.", "[[QZ]] Hello there.",
                                      "[[QZ]]. Hello there.", "[[QZ]], hello there.", "[[QZ]]? Hello there.",
                                      "Hi. [[QZ]]. Hello there.", "Hi. [[QZ]], hello there.",
                                      "Wait [[QZ]]\nGo.", "[[QZ]] [[QZ]]. Hello there.", "[[QZ]]\n[[QZ]] Hello there.",
                                      "Wait [[QZ]]... go now.", "[[QZ]]... go now.", "Wait [[QZ]]...\n\ngo now.",
                                      "Wait [[QZ]] . go now.", "Wait [[QZ]]\t?! go now.", "[[QZ]]. [[QZ]] go now.",
                                      "Wait [[QZ]] !go now.", 'Wait [[QZ]] ."go now."', "Wait [[QZ]]| go now.",
                                      "Wait [[QZ]]\u203c go now.", "Wait [[QZ]]*. go now.", "Wait [[QZ]] ;* go now.",
                                      'He said "wait [[QZ]];*" Go.', "He left (see [[QZ]]); then came back.",
                                      'Wait [[QZ]]". "go now."', "Wait [[QZ]];* go now.", "Hi [[QZ]]. \u2026 [[QZ]] go."])
    def test_the_none_chunk_is_dizione_read_with_the_block_in_place(self, backend, text, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Wait [[QZ]] != go now.", "The rate fell by [[QZ]] .5 percent.",
                                      "Items [[QZ]]:(a) one, (b) two.", "See [[QZ]];(see above) now.",
                                      "Wait [[QZ]]:( go now.", "Wait [[QZ]];-) go now.", "Wait [[QZ]] :-( go now.",
                                      "Wait [[QZ]]:(", "Hi [[QZ]]:( [[QZ]] go.", "He left (see [[QZ]]):D then came back."])
    def test_a_mark_that_belongs_to_the_text_after_it_stays_there(self, backend, text, keep):
        # dizione reads a decimal point, an operator or an emoticon with the text after it, and writes no mark
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Wait [[QZ]]) ; go now.", "Wait [[QZ]]. , go now.", "He left (see [[QZ]]) ;",
                                      "He left (see [[QZ]]). ) then came back.", 'Wait [[QZ]]. " go now.',
                                      "Wait [[QZ]], \u2026 go now.", "Wait [[QZ]]. \uff02 go now.", 'Wait [[QZ]]. "',
                                      "Wait [[QZ]]) ;go now.", "Wait [[QZ]]. !go now."])
    def test_a_second_run_of_marks_after_whitespace_goes_with_the_block(self, backend, text, keep):
        # where a word follows, dizione starts a clause with a quote or an ellipsis after the whitespace
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]
        # the marks end the block's chunk, as they end the clause of the word "x" in dizione's own read
        clauses = frontend.phonemize(text.replace("[[QZ]]", "x"), Stages(chunk=Chunk.CLAUSE))
        for chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            assert _after(frontend.phonemize(text, Stages(chunk=chunk)), ["Q", "Z"]) == _after(clauses, ["ɛ", "k", "s"])

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Wait [[QZ]].);5 go.", "Wait [[QZ]]!):D go.", 'Wait [[QZ]]"):go now.',
                                      "Wait [[QZ]]:')) go now.", "Wait [[QZ]]:']] go now.", "Wait [[QZ]]);'* go.",
                                      "Wait [[QZ]]):'* go.", "Wait [[QZ]];') ' go.", "Wait [[QZ]]. );5 go."])
    def test_no_mark_of_the_run_after_a_block_starts_the_next_chunk(self, backend, text, keep):
        # dizione reads a tail such as ");" or ":'))" at the end of a text as an emoticon, and with the next word as marks
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]
        for chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            chunks = frontend.phonemize(text, Stages(chunk=chunk))
            assert [c[1] for c in chunks[1:] if c[1] in set(".,?!;:…)\"'")] == []

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Wait [[QZ]]%. go now.", "Wait [[QZ]] %, go now.", 'He said "wait [[QZ]]&" Go.',
                                      'He said "wait [[QZ]].%" Go.', "Wait [[QZ]]\u00a7. go now.", "Wait [[QZ]]%.",
                                      "Wait [[QZ]].% go now.", "Wait [[QZ]]!& go."])
    def test_a_symbol_that_dizione_reads_as_a_word_ends_the_marks(self, backend, text, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]
        # the word goes with the text after it, so the block's chunk ends in marks only
        for chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            after = _after(frontend.phonemize(text, Stages(chunk=chunk)), ["Q", "Z"])
            assert [s for s in after if s[:1] != "<" and any(c.isalpha() for c in s)] == []

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Wait [[QZ]] \u2019tis fine.", "He left [[QZ]] \u2019cause it rained.",
                                      "They met in [[QZ]] \u201990s style.", "He said [[QZ]] 'go home.'",
                                      'Wait [[QZ]] "go," he said.', "Er sagte [[QZ]] \u00bbGeh nach Hause\u00ab.",
                                      "Han sa [[QZ]] \u201dG\u00e5 hem\u201d.", 'Wait [[QZ]] " go now.',
                                      'Wait [[QZ]] \u2039"go now."'])
    def test_a_quote_after_whitespace_reads_as_dizione_reads_it(self, backend, text, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", [text for mark in (".", ",", "?", "!", ";", ":", "…", "...", "?!", "!»", "),",
                                                        '."', ");", "):", "|", "\u203c")
                                      for text in (f"Wait [[QZ]]{mark}", f"Wait [[QZ]]{mark} [[QZ]] go now.")])
    def test_a_mark_with_no_word_after_it_is_written_from_dizione_table(self, backend, text, keep):
        # dizione reads no word after the mark, so the frontend writes it from dizione's mark table
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]

    @pytest.mark.parametrize("marks, symbols", [(".", ["."]), ("...", ["…"]), ("?!", ["?", "!"]), ("!»", ["!", '"']),
                                                ("),", [")", ","]), ('."', [".", '"']), ("!!", ["!"]), ("。", []),
                                                ("\u203c", ["!"]), ("*.", ["."]), (");", [")", ";"]),
                                                ("]:", [")", ":"]), (";*", [";"]), (":/", [":"])])
    def test_dizione_mark_table_is_what_dizione_writes_after_a_word(self, backend, marks, symbols):
        # dizione drops ";*" and ":/" alone as emoticons, but not after a word
        table = backend.mark_symbols(marks)
        assert list(table.phonemes) == symbols
        assert list(table.streams["ids"]) == [SYMBOL_TO_ID[symbol] for symbol in symbols]
        assert list(table.streams["stress"]) == [0] * len(symbols)
        between = list(backend.tokens(f"go{marks} now").symbols)
        assert between[between.index("oʊ") + 1:between.index("n")] in (symbols, symbols + ["<sp>"])

    def test_dizione_has_no_mark_table_without_tokens(self):
        assert DizionePhonemizer().mark_symbols(".") is None

    @pytest.mark.parametrize("chunk", SIZES)
    def test_a_block_before_the_first_text_at_each_size(self, backend, chunk):
        # a chunk of its own at sentence and clause size, with the mark right after it,
        # and the start of the chunk after it at paragraph and none size
        frontend = TextFrontend(FrontendConfig("en-US"), backend)
        text = "[[QZ]]. Hello there. Bye now."
        if chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            expected = [self._with_block(backend, "[[QZ]].")] + [
                (list(backend.tokens(sentence).symbols), list(backend.tokens(sentence).ids))
                for sentence in ("Hello there.", "Bye now.")]
        else:
            expected = [self._with_block(backend, text)]
        assert _ids(frontend, text, chunk, "ids") == expected

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", SIZES)
    def test_every_chunk_has_one_pair_and_the_block_inside(self, backend, chunk, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        text = "Hello [[QZ]] world. Bye now.\n\nHi. [[QZ]] there, you."
        chunks = _ids(frontend, text, chunk, "ids")
        for symbols, ids in chunks:
            assert (symbols[0], symbols[-1]) == ("<bos>", "<eos>")
            assert symbols.count("<bos>") == symbols.count("<eos>") == 1
            assert " " not in symbols
            assert "<sp>" not in (symbols[1], symbols[-2])
            assert len(ids) == len(symbols)
        flat = [symbol for symbols, _ in chunks for symbol in symbols]
        assert flat.count("Q") == 2
        # the word break after each block is dizione's own, with its id
        for symbols, ids in chunks:
            for place in (i for i, symbol in enumerate(symbols) if symbol == "Z"):
                if symbols[place + 1] != "<eos>":
                    assert (symbols[place + 1], ids[place + 1]) == ("<sp>", backend.tokens("a b").ids[2])


class TestAMarkAfterABlock:
    """A closing mark after a block, right after it or after whitespace, closes the block's sentence.

    So the mark goes with the block's chunk, as tts-punctuation puts a closing
    mark with the sentence that it ends, and no chunk starts with a mark that
    closes a block's sentence, at any size and for any backend.
    """

    MARKS = (".", ",", "?", '"', "،", "…")
    CASES = [("graphemes", "en-US", None, "Wait [[ab]]. Go. Wait [[ab]], go now. He said \"wait [[ab]].\" Go. "
                                          "Wait [[ab]] . Go. Wait [[ab]]... go."),
             ("orthography2ipa", "en-US", None, "Wait [[ab]]? Go. [[ab]]. Go now. Wait [[ab]] ? Go."),
             ("dizione", "en-US", None, "Wait [[ab]]. Go. Wait [[ab]], go now. He said \"wait [[ab]].\" Go. "
                                        "Wait [[ab]] . Go. Wait [[ab]]... go."),
             ("shami", "ar", None, "انتظر [[ab]]. اذهب. [[ab]]، اذهب الآن. انتظر [[ab]] . اذهب."),
             ("vosk", "ru-RU", "vosk", "Жди [[ab]]. Иди. Жди [[ab]], иди. Жди [[ab]] . Иди. Жди [[ab]] !Иди.")]

    @staticmethod
    def _frontend(name, lang, alphabet, keep):
        return TextFrontend(FrontendConfig(
            lang, Phonemizer(name), alphabet=Alphabet(alphabet) if alphabet else Alphabet.IPA,
            keep_punctuation=keep, stages=Stages(diacritize=False)))

    def test_dizione_tokens_end_the_block_chunk_with_its_mark(self):
        backend = DizionePhonemizer(tokens=True)
        frontend = TextFrontend(FrontendConfig("en-US"), backend)
        for chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            first, second = frontend.phonemize("Wait [[ab]]. Go.", Stages(chunk=chunk))
            assert first[-4:] == ["a", "b", ".", "<eos>"]
            assert second[:2] == ["<bos>", "ɡ"]
            assert (first, second) == (TestDizioneTokensAndBlocks._with_block(backend, "Wait [[QZ]].")[0][:-4]
                                       + ["a", "b", ".", "<eos>"], list(backend.tokens("Go.").symbols))

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    @pytest.mark.parametrize("name, lang, alphabet, text", CASES)
    def test_no_chunk_starts_with_a_closing_mark(self, name, lang, alphabet, text, chunk, keep):
        frontend = self._frontend(name, lang, alphabet, keep)
        chunks = frontend.phonemize(text, Stages(chunk=chunk))
        bodies = [c[1:-1] if c[0] == "<bos>" else c for c in chunks]
        assert [body for body in bodies if body and body[0] in self.MARKS + (" ",)] == []
        # the marks move between chunks, and none is lost or doubled
        whole = frontend.phonemize(text, Stages(chunk=Chunk.NONE))[0]
        assert [sum(c.count(m) for c in chunks) for m in self.MARKS] == [whole.count(m) for m in self.MARKS]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    @pytest.mark.parametrize("text, tail", [("Wait [[ab]]. Go.", ["."]), ("Wait [[ab]], go now.", [","]),
                                            ("Wait [[ab]]? Go.", ["?"]), ("[[ab]]. Go now.", ["."]),
                                            ('He said "wait [[ab]]." Go.', [".", '"']), ('Wait [[ab]] " Go.', ['"']),
                                            ("He asked (why [[ab]]?) and left.", ["?", ")"])])
    def test_a_bounded_backend_writes_the_mark_inside_the_block_chunk(self, text, tail, chunk, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), DizionePhonemizer(tokens=True))
        first, *rest = frontend.phonemize(text, Stages(chunk=chunk))
        assert first[-len(tail) - 3:] == ["a", "b", *tail, "<eos>"]
        assert rest[0][1] not in self.MARKS

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE, Chunk.PARAGRAPH])
    @pytest.mark.parametrize("text", ["Wait [[ab]]... Go.", "Wait [[ab]]...\n\nGo.", "Wait [[ab]] . Go.",
                                      "Wait [[ab]]\n\n. Go.", "Wait [[ab]] ?!\n\nGo.", "Wait [[ab]] !Go."])
    def test_no_dizione_token_chunk_starts_with_a_closing_mark(self, text, chunk, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), DizionePhonemizer(tokens=True))
        assert [c[:3] for c in frontend.phonemize(text, Stages(chunk=chunk)) if c[1] in (".", "?", "!", "…")] == []

    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE, Chunk.PARAGRAPH])
    @pytest.mark.parametrize("text, start", [('Wait [[ab]]\n\n"Go," he said.', ['"', "ɡ"]),
                                             ("Wait [[ab]]\n\n\u2019tis fine.", ["t", "ɪ"]),
                                             ("Wait [[ab]]\n\n'Go,' he said.", ["'", "ɡ"]),
                                             ("Er sagte [[ab]]\n\n\u00bbGeh!\u00ab", ['"', "dʒ"]),
                                             ("Han sa [[ab]]\n\n\u201dG\u00e5!\u201d", ['"', "ɡ"])])
    def test_a_quote_that_opens_the_next_word_stays_with_it(self, text, start, chunk):
        frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
        first, second, *_ = frontend.phonemize(text, Stages(chunk=chunk))
        assert first[-3:] == ["a", "b", "<eos>"]
        assert second[:3] == ["<bos>", *start]

    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    def test_the_marks_that_dizione_reads_alone_leave_the_next_chunk(self, chunk):
        # dizione reads "):'(" alone as ") '", and the text with a word as ")": the "'" is no mark of either chunk
        frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
        first, second = frontend.phonemize("He left (see [[ab]]):'( then came back.", Stages(chunk=chunk))
        assert first[-4:] == ["a", "b", ")", "<eos>"]
        assert second[1] != "'"

    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    def test_a_symbol_word_after_a_block_starts_the_next_chunk(self, chunk):
        # dizione reads "%" as the word "percent", so it is no mark of the block's sentence
        frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
        first, second, *_ = frontend.phonemize("Wait [[ab]]%. Go now.", Stages(chunk=chunk))
        assert first[-3:] == ["a", "b", "<eos>"]
        assert second[:3] == ["<bos>", "p", "ɚ"]

    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    def test_an_opening_quote_after_the_mark_starts_the_next_chunk(self, chunk):
        frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
        first, second, *_ = frontend.phonemize('Wait [[ab]]. "Go," he said.', Stages(chunk=chunk))
        assert first[-4:] == ["a", "b", ".", "<eos>"]
        assert second[:3] == ["<bos>", '"', "ɡ"]

    @pytest.mark.parametrize("keep", [True, False])
    def test_shami_keeps_a_word_break_where_it_drops_the_mark_after_a_block(self, keep):
        frontend = self._frontend("shami", "ar", None, keep)
        for text in ("انتظر [[ab]]. اذهب.", "[[ab]]، اذهب الآن.", "انتظر [[ab]]\nاذهب."):
            whole = frontend.phonemize(text, Stages(chunk=Chunk.NONE))[0]
            assert whole[whole.index("b") + 1] == " "
        # a block glued to the next word takes no word break: the word's own first symbol follows it
        whole = frontend.phonemize("انتظر [[ab]]اذهب.", Stages(chunk=Chunk.NONE))[0]
        word = frontend.phonemize("اذهب.", Stages(chunk=Chunk.NONE))[0]
        assert word[0] == "<bos>"
        assert whole[whole.index("b") + 1] == word[1]

    @pytest.mark.parametrize("text", ["Жди [[ab]]% иди.", "Жди [[ab]] % иди.", "Жди [[ab]]%"])
    def test_a_symbol_that_the_backend_writes_as_a_mark_goes_with_the_block(self, text):
        # vosk writes "%" as a mark, where dizione reads it as the word "percent"
        first, *rest = self._frontend("vosk", "ru-RU", "vosk", True).phonemize(text)
        assert "".join(first).endswith("ab%")
        assert [chunk for chunk in rest if chunk[0] == "%"] == []

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.CLAUSE])
    def test_vosk_writes_a_second_run_of_marks_with_the_block(self, chunk, keep):
        frontend = self._frontend("vosk", "ru-RU", "vosk", keep)
        for text in ("Жди [[ab]]) ; иди сейчас.", "Жди [[ab]]) ;иди сейчас."):
            first, second = frontend.phonemize(text, Stages(chunk=chunk))
            assert "".join(first).endswith("ab) ;")
            assert second[0] == "i0"
        # vosk's own read starts a sentence after the full stop, so the comma starts the chunk after the block
        assert frontend.phonemize("Жди [[ab]]. , иди.", Stages(chunk=chunk))[1:] == frontend.phonemize(
            "Жди кот. , иди.", Stages(chunk=chunk))[1:]

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Жди [[ab]] \u00a1иди сейчас.", "Жди [[ab]] \u00bfиди сейчас."])
    def test_vosk_keeps_an_inverted_mark_with_the_word_it_opens(self, text, keep):
        first, second = self._frontend("vosk", "ru-RU", "vosk", keep).phonemize(text)
        assert first[-2:] == ["a", "b"] or first[-3:] == ["a", "b", " "]
        assert second[0] == text[text.index("]] ") + 3]

    @pytest.mark.parametrize("keep", [True, False])
    def test_vosk_joins_its_chunks_after_a_block_by_the_one_rule(self, keep):
        frontend = self._frontend("vosk", "ru-RU", "vosk", keep)
        for text in ("Жди [[ab]]. Иди. Жди [[ab]], иди.", "Жди [[ab]]. [[cd]] иди."):
            sentences = frontend.phonemize(text)
            assert not [c for c in sentences if c[0] == " "]
            assert frontend.phonemize(text, Stages(chunk=Chunk.NONE)) == [join_sentences(sentences, keep_punctuation=False)]
        # a block after the mark of a block joins the chunk before it, with the mark
        first, second = frontend.phonemize("Жди [[ab]]. [[cd]] иди.")
        assert first[first.index("a"):first.index("d") + 1] == ["a", "b", ".", " ", "c", "d"]
        assert second[0] != " "


class TestRulesOfTheFix:
    """Rules of the fix that change real output, each held by a test."""

    @pytest.mark.parametrize("name", ["pypinyin", "xpinyin", "g2pm"])
    def test_spaces_around_a_latin_word_in_zh_change_nothing(self, name):
        frontend = TextFrontend(FrontendConfig("zh-CN", Phonemizer(name), stages=Stages(diacritize=False)))
        backend = frontend.backend
        spaced = backend.phonemize_to_list("我爱 Python 和 C++。", "zh")
        assert spaced == backend.phonemize_to_list("我爱Python和C++。", "zh")
        assert frontend.phonemize_flat("我爱 Python 和 C++。") == frontend.phonemize_flat("我爱Python和C++。")

    @pytest.mark.parametrize("chunk", [Chunk.SENTENCE, Chunk.PARAGRAPH])
    def test_each_cut_above_the_limit_ends_a_sentence_and_a_paragraph(self, chunk):
        text = "Um dois\n\nTrês quatro"
        backend = WholeText()
        frontend = TextFrontend(FrontendConfig("xx", whole_text_limit=5), backend)
        assert ["".join(c) for c in frontend.phonemize(text, Stages(chunk=chunk))] == ["Um dois", "Três quatro"]
        assert backend.read == ["Um dois", "Três quatro"]

    def test_dizione_reads_each_cut_above_the_limit_as_its_own_paragraph(self, dizione):
        text = "Chapter one\n\nThe cat sat"
        frontend = TextFrontend(FrontendConfig("en-US", whole_text_limit=5), dizione)
        alone = TextFrontend(FrontendConfig("en-US"), dizione)
        assert frontend.phonemize(text, Stages(chunk=Chunk.PARAGRAPH)) == [
            alone.phonemize_flat("Chapter one"), alone.phonemize_flat("The cat sat")]

    @pytest.mark.parametrize("chunk", SIZES)
    def test_a_block_keeps_the_bounds_of_its_chunk(self, chunk):
        frontend = TextFrontend(FrontendConfig("xx"), Bounded())
        segments = list(frontend.segments("[[q]] Um, dois [[q]] três.", Stages(chunk=chunk)))
        assert all(s.bounded and s.phonemes[0] == "<s>" and s.phonemes[-1] == "</s>" for s in segments)
        assert sum(s.phonemes.count("<s>") for s in segments) == len(segments)
        assert sum(s.phonemes.count("q") for s in segments) == 2

    def test_a_hyphen_before_a_block_separates_it_in_a_bounded_piece(self):
        frontend = TextFrontend(FrontendConfig("xx"), Bounded())
        assert [s.phonemes for s in frontend.segments("Sim vem-[[xy]].")] == [
            ("<s>", *"Sim vem- xy.", "</s>")]


class TestDizioneReadsOnce:
    """dizione rewrites a text once for its paragraphs and quotes, and tokenizes it once."""

    def test_one_rewrite_and_one_tokenize_per_call(self, dizione, monkeypatch):
        import scriptconv.phonemizers.dizione as module
        calls = {"rewrite": 0, "tokenize": 0}
        rewrite, tokenize = dizione.engine.normalizer.rewrite, module.tokenize

        def counted(name, function):
            def call(*args, **kwargs):
                calls[name] += 1
                return function(*args, **kwargs)
            return call

        text = "\n\n".join(f'"Sentence number {n}." He left.' for n in range(20))
        expected = list(dizione.phonemize_segments(text, "en-US"))
        monkeypatch.setattr(dizione.engine.normalizer, "rewrite", counted("rewrite", rewrite))
        monkeypatch.setattr(module, "tokenize", counted("tokenize", tokenize))
        assert list(dizione.phonemize_segments(text, "en-US")) == expected
        # engine.pieces rewrites the text once itself
        assert calls == {"rewrite": 2, "tokenize": 1}
        assert sum(segment.ends_paragraph for segment in expected) == 19


class TestDizioneParagraphEnds:
    """Where dizione's blank lines end a paragraph: after the sentence mark right before them."""

    @staticmethod
    def _ends(dizione, text):
        return [segment.ends_paragraph for segment in dizione.phonemize_segments(text, "en-US")]

    def test_a_repeated_mark_ends_the_paragraph_once(self, dizione):
        assert self._ends(dizione, "Wait!! Go.\n\nNext one.") == [False, True, False]

    def test_a_blank_line_ends_no_paragraph_at_an_earlier_mark(self, dizione):
        # the blank line follows "Title", so "Hi." ends no paragraph
        assert self._ends(dizione, "Hi. Title\n\nBody here.")[0] is False

    def test_a_mark_before_the_first_sound_ends_no_paragraph(self, dizione):
        assert self._ends(dizione, "?\n\nHi. Bye.\n\nOk.") == [False, True, False]

    def test_marks_that_differ_in_number_end_no_paragraph(self, dizione):
        from scriptconv.phonemizers._thirdparty.dizione.symbols import tokenize
        from scriptconv.phonemizers.dizione import _paragraph_ends
        text = "Go.\n\nOk."
        pieces = dizione.engine.pieces(text)
        symbols = tokenize(pieces).symbols
        rewritten = dizione.engine.normalizer.rewrite(text)
        assert _paragraph_ends(rewritten, pieces, symbols) == {symbols.index(".")}
        # a rewritten text with one more mark than the tokens maps no blank line
        assert _paragraph_ends("Hi. " + rewritten, pieces, symbols) == set()


class TestDiacritizerChunks:
    def test_the_diacritizer_reads_each_sentence_alone_across_a_blank_line(self, monkeypatch):
        import scriptconv.frontend as frontend_module
        read = []

        def diacritize(text, lang, diacritizer_model=None):
            read.append(text)
            return text

        monkeypatch.setattr(frontend_module, "diacritize", diacritize)
        frontend = TextFrontend(FrontendConfig("en-US", Phonemizer("graphemes"), stages=Stages(diacritize=True)))
        assert frontend.prepare("Come here!\n\nOpen the door.") == "Come here!\n\nOpen the door."
        assert read == ["Come here!", "Open the door."]
