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
        """dizione's tokens of *text* with the word "x" in place of the block, the block's symbols written in."""
        whole = backend.tokens(text.replace("[[QZ]]", "x"))
        place = next(i for i in range(len(whole.symbols)) if whole.symbols[i:i + 3] == ("ɛ", "k", "s"))
        return ([*whole.symbols[:place], "Q", "Z", *whole.symbols[place + 3:]],
                [*whole.ids[:place], 0, 0, *whole.ids[place + 3:]])

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Hello [[QZ]] world. Bye now.", "Hi. [[QZ]] there, you. Bye.",
                                      "Hello [[QZ]], world.", "[[QZ]] Hello there."])
    def test_the_none_chunk_is_dizione_read_with_the_block_in_place(self, backend, text, keep):
        frontend = TextFrontend(FrontendConfig("en-US", keep_punctuation=keep), backend)
        assert _ids(frontend, text, Chunk.NONE, "ids") == [self._with_block(backend, text)]

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
