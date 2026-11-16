"""The text frontend: text stages and a phonemizer backend in one fixed order.

:class:`TextFrontend` takes text to phonemes. Every path runs the same order:

1. Split out inline ``[[phonemes]]`` blocks. No stage reads the text inside a
   block, and its symbols reach the output as written.
2. Run the normalisation hook on the whole text, if the caller set one.
   Every stage reads its text without the whitespace at its edges, and that
   whitespace goes back around the result.
3. Apply casing, if the call sets a casing function.
4. Cut the normalised text into sentences, or into clauses at ``clause``
   size.
5. For each sentence or clause, lazily: diacritize, then run the backend.
   The backend cuts a sentence into clauses and appends the clause symbols.
6. Group the sentences into chunks of the size :class:`Chunk` names, and
   join them by the rule of
   :func:`~scriptconv.phonemizers.base.join_sentences`.

A sentence split on raw text cuts at full stops that belong to the reading, as
in ``"Prof. Smith arrived."``, so the split runs after normalisation.

The frontend skips a stage that the backend names in ``owned_stages``, because
the backend runs it itself. scriptconv does not normalise text. The hook is
off by default, and :func:`spoken_normalizer` returns ``text2spoken.normalize``
for it.

A backend that owns ``normalize`` reads the text with its own rules, so the
frontend cannot cut it for that backend:

- A backend that sets ``reads_whole_text`` gets the whole text and reports its
  own sentences and clauses through ``phonemize_segments``. The frontend
  appends the clause symbols and groups the segments. Above
  :attr:`FrontendConfig.whole_text_limit` characters, the frontend first cuts
  the text at its paragraph breaks.
- Any other owner of ``normalize`` gets the text cut into sentences before
  casing, as written.

With ``strict=False`` a failed stage logs a warning and the text continues
without that stage. With ``strict=True`` it raises :class:`StageError`.

Around a block, the spaces and clause symbols are those of the same text with a
plain word in place of the block, and an empty block reads as no text. Some
differences stay:

- A backend can change a word by the word after it. orthography2ipa voices a
  final consonant before a voiced sound, but a block holds its word as read
  alone.
- The frontend counts a digit as a word, but orthography2ipa reads a clause of
  only digits to nothing without a normaliser.
- A block gives one space symbol for a run of whitespace, but the unicode
  backend copies each tab and space.
- A mark directly before a block gives no symbol and no space, but plain
  text reads ``!`` or ``?`` between two words as a space.
"""
import copy
import dataclasses
import enum
import importlib.util
import itertools
import logging
import re
import unicodedata
from typing import Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from scriptconv.diacritics import _DIACRITIZER_PACKAGES, _diacritizer_family, diacritize
from scriptconv.graph import ConversionGraph, Edge
from scriptconv.phonemizers.base import (
    _CLAUSE_BREAK,
    _CLAUSE_TOKENS,
    _PARAGRAPH_BREAK,
    _PAUSE_PUNCTUATION,
    BasePhonemizer,
    PhonemizerIdentity,
    Segment,
    StageError,
    UnreadTextError,
    split_clauses,
)
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.registry import get_phonemizer, phonemizer_for_lang

__all__ = ["Chunk", "Stages", "FrontendConfig", "TextFrontend", "spoken_normalizer",
           "FRONTEND_VERSION", "WHOLE_TEXT_LIMIT"]

LOG = logging.getLogger(__name__)

FRONTEND_VERSION = 2
"""The version of the stage order, in :meth:`TextFrontend.identity`. A change
to the stages raises it. Version 1 cut the raw text into sentences before
normalisation."""

# scripts/time_owner_backends.py, output in scripts/time_owner_backends.txt: one dizione call on English text
# dense in dates and prices, also with a blank line and quotes after each sentence, stays under 100 ms up to
# 1,750 characters, both with a new backend per call (at most 61.9 ms in two runs) and with one backend read
# again and again (at most 79.3 ms in 11 runs). At 2,000 characters one run of the second kind took 100.5 ms.
# Prose reads faster. The limit bounds the read; a full garbage collection of the process can add to one call.
WHOLE_TEXT_LIMIT = 1_750
"""The default of :attr:`FrontendConfig.whole_text_limit`."""

# The word that stands for a block when the frontend reads the mark after it.
_BLOCK_WORD = "a"
# Text that ends in whitespace and then only marks. The marks join the block
# after them as they join a plain word, and the whitespace stays.
_SPACE_BEFORE_BLOCK = re.compile(r"\s\W*$")
# The quotes and apostrophes that can open a word besides the categories of
# opening and closing quotes (Pi, Pf).
_OPENING_MARKS = frozenset("\"'\u2019\u2018\u201a\u201e\u00ab\u00bb\u2039\u203a\u00a1\u00bf")
# The text before the first letter or digit: whitespace and marks.
_WORDLESS_START = re.compile(r"[\W_]*")

# linguatag puts "ar" with any region, and each individual Arabic language in
# Arabic script, at 5 or less from "ar". Those languages diacritize by default.
_ARABIC_DISTANCE = 5


def spoken_normalizer() -> Callable[[str, str], str]:
    """``text2spoken.normalize``, for :attr:`FrontendConfig.normalizer`.

    Raises:
        ImportError: If the ``normalize`` extra is not installed.
    """
    try:
        from text2spoken import normalize
    except ImportError as e:
        raise ImportError(
            "the spoken-form normaliser needs text2spoken — install with "
            "`pip install scriptconv[normalize]`") from e
    return normalize


class Chunk(str, enum.Enum):
    """What :meth:`TextFrontend.phonemize_lazy` yields in one step.

    The stage order is the same at every size, and one rule joins the chunks
    of every size: the chunks joined by the rule of
    :func:`~scriptconv.phonemizers.base.join_sentences` are
    :meth:`TextFrontend.phonemize_flat`. So the size moves only the cuts. At
    ``clause`` size the backend reads each clause alone, so a reading that
    needs a word of the next clause can change.
    """

    SENTENCE = "sentence"
    """One sentence. Live speech."""
    CLAUSE = "clause"
    """One clause. Faster first audio on long sentences."""
    PARAGRAPH = "paragraph"
    """The text between blank-line breaks. Fewer false sentence ends."""
    NONE = "none"
    """The whole text. Offline rendering and dataset work."""


@dataclasses.dataclass(frozen=True)
class Stages:
    """The text stages of one call.

    A value of ``None`` takes the frontend's own value.
    """

    normalize: Optional[bool] = None
    """``False`` skips the normalisation hook. ``None`` takes the frontend's
    value, and when that is ``None`` too, the hook runs."""
    diacritize: Optional[bool] = None
    """``None`` takes the frontend's value. When that is ``None`` too, Arabic
    diacritizes and every other language does not."""
    diacritizer_model: Optional[str] = None
    lang: Optional[str] = None
    """The language of the text. A cloning reference has its own language."""
    casing: Optional[Callable[[str], str]] = None
    """Runs after normalisation. Only training sets one."""
    chunk: Optional[Chunk] = None
    """The chunk size, a :class:`Chunk` or its value such as ``"clause"``.
    ``None`` takes the frontend's value, and when that is ``None`` too, a
    chunk is a sentence.

    Raises:
        ValueError: If the value is not a :class:`Chunk` value.
    """

    def __post_init__(self):
        if self.chunk is not None:
            object.__setattr__(self, "chunk", Chunk(self.chunk))


@dataclasses.dataclass(frozen=True)
class FrontendConfig:
    """What a :class:`TextFrontend` is built from."""

    lang: str
    phonemizer: Optional[Phonemizer] = None
    """``None`` takes the default backend for :attr:`lang`."""
    alphabet: Alphabet = Alphabet.IPA
    model: Optional[str] = None
    stages: Stages = Stages()
    normalizer: Optional[Callable[[str, str], str]] = None
    """A ``(text, lang) -> str`` hook. ``None`` means no normalisation."""
    keep_punctuation: bool = False
    strict: bool = False
    whole_text_limit: Optional[int] = WHOLE_TEXT_LIMIT
    """Above this many characters, the frontend cuts the text at its paragraph
    breaks before a ``reads_whole_text`` backend reads it. ``None`` turns the
    cut off."""


def _sentence_tokenize(text: str) -> List[str]:
    """*text* split into sentences by quebra-frases.

    Raises:
        ImportError: If the ``phonemizers`` extra is not installed.
    """
    try:
        from quebra_frases import sentence_tokenize
    except ImportError:
        raise ImportError(
            "sentence chunking needs quebra-frases — install with "
            "`pip install scriptconv[phonemizers]`") from None
    return sentence_tokenize(text)


def _with_gaps(text: str, chunks: List[str]) -> List[Tuple[str, str]]:
    """*text* as ``(gap, chunk)`` pairs, for *chunks* found in order in *text*.

    The gaps and chunks joined give *text* back.
    """
    pairs = []
    start = 0
    for chunk in chunks:
        found = text.find(chunk, start)
        pairs.append((text[start:found], chunk))
        start = found + len(chunk)
    if start < len(text):
        pairs.append((text[start:], ""))
    return pairs


def _paragraphs(text: str) -> List[str]:
    """*text* cut at its blank-line breaks."""
    return _PARAGRAPH_BREAK.split(text)[::2]


def _clauses(sentence: str) -> List[str]:
    """*sentence* cut after each clause break of :func:`~scriptconv.phonemizers.base.split_clauses`.

    Each clause keeps the marks that end it and the whitespace after them, so
    the backend reads the break as it reads it inside the sentence: ``|``
    and an ellipsis give no symbol, and the next clause starts at a word.
    """
    clauses = []
    start = 0
    for match in _CLAUSE_BREAK.finditer(sentence):
        end = match.end() + len(sentence[match.end():]) - len(sentence[match.end():].lstrip())
        clauses.append(sentence[start:end])
        start = end
    clauses.append(sentence[start:])
    return clauses


def _paragraph_sentences(text: str) -> List[List[str]]:
    """The sentences of each paragraph of *text*.

    The cut at the blank lines comes first, so a paragraph break ends a
    sentence also where the sentence split sees none, as after a title or
    a ``!``.
    """
    return [_sentence_tokenize(paragraph) for paragraph in _paragraphs(text) if paragraph.strip()]


@dataclasses.dataclass
class _Piece:
    """A sentence or clause as the frontend reads it, or several of them joined."""

    phonemes: List[str]
    ends_in_token: bool = False
    """Whether :attr:`phonemes` ends in a clause symbol, which joins the next
    piece with no space. A bounded piece that ends in a block with no
    whitespace after it in the text joins the next piece with no space too."""
    ends_sentence: bool = True
    ends_paragraph: bool = False
    streams: Dict[str, List] = dataclasses.field(default_factory=dict)
    """The backend's side streams, in step with :attr:`phonemes`."""
    bounds: Optional[Tuple[Segment, Segment]] = None
    """The backend's start and end symbols, with their stream values, for a
    piece of bounded segments. :attr:`phonemes` holds neither: :meth:`closed`
    writes them around a chunk, so a join or a block works inside them."""

    @classmethod
    def of(cls, segment: Segment) -> "_Piece":
        """*segment* as a piece, without its start and end symbols when it is bounded."""
        streams = segment.streams
        if not segment.bounded:
            return cls(list(segment.phonemes), ends_sentence=segment.ends_sentence,
                       streams={name: list(values) for name, values in streams.items()})
        start = Segment(segment.phonemes[:1], streams={name: values[:1] for name, values in streams.items()})
        end = Segment(segment.phonemes[-1:], streams={name: values[-1:] for name, values in streams.items()})
        return cls(list(segment.phonemes[1:-1]), ends_sentence=segment.ends_sentence,
                   streams={name: list(values[1:-1]) for name, values in streams.items()}, bounds=(start, end))

    def closed(self, space: Segment) -> "_Piece":
        """The piece with its start and end symbols written around it. A *space* before the end symbol goes."""
        if self.bounds is None:
            return self
        start, end = self.bounds
        size = len(self.phonemes)
        if size and self.phonemes[-len(space.phonemes):] == list(space.phonemes):
            size -= len(space.phonemes)
        body = {name: values[:size] for name, values in self.streams.items()}
        piece = dataclasses.replace(self, phonemes=[], streams={})
        for symbols, streams in ((start.phonemes, start.streams), (self.phonemes[:size], body),
                                 (end.phonemes, end.streams)):
            piece.add(symbols, streams)
        return piece

    def add(self, symbols: Sequence[str], streams: Optional[Mapping[str, Sequence]] = None) -> None:
        """Append *symbols*, with the values of *streams*. A stream that *streams* lacks takes 0."""
        streams = streams or {}
        for name in streams.keys() - self.streams.keys():
            self.streams[name] = [0] * len(self.phonemes)
        self.phonemes.extend(symbols)
        for name, values in self.streams.items():
            values.extend(streams.get(name, (0,) * len(symbols)))

    def pop(self) -> None:
        """Remove the last symbol and its stream values."""
        self.phonemes.pop()
        for values in self.streams.values():
            values.pop()


def _leading_marks(text: str, reads_as_word: Callable[[str], bool] = lambda char: False) -> str:
    """The run of closing marks at the start of *text*.

    A closing mark is ``|`` or a mark of the categories that end or close
    (Po, Pe, Pf), such as ``.``, ``…``, ``?``, a closing quote or bracket. A
    symbol that the backend reads as a word, such as dizione's ``%``
    ("percent"), is no mark: *reads_as_word* tells it, and the run ends
    before it.
    """
    count = next((i for i, char in enumerate(text) if (char != "|" and unicodedata.category(char) not in (
        "Po", "Pe", "Pf")) or reads_as_word(char)), len(text))
    return text[:count]


def _opens_word(char: str) -> bool:
    """Whether *char* is a quote or apostrophe that can open a word."""
    return char in _OPENING_MARKS or unicodedata.category(char) in ("Pi", "Pf")


def _marks_after(after: str, reads_as_word: Callable[[str], bool]) -> Tuple[str, str]:
    """The closing marks in the text *after* a block, and the quotes after them that open the next word.

    The closing marks close the block's sentence. They come right after the
    block, or after whitespace, and then they keep the whitespace before
    them, as a backend can read marks after whitespace in another way. A
    symbol that the backend reads as a word ends them: *reads_as_word* tells
    it (see :func:`_leading_marks`). After whitespace, a run of marks glued
    to the next word ends before its first quote or apostrophe: that quote,
    and the quotes after it, open the word, as in ``[[ab]] "Go"`` or
    ``[[ab]] ’tis``.
    """
    marks = _leading_marks(after, reads_as_word)
    rest = after.lstrip()
    if marks or rest == after:
        return marks, ""
    gap, marks = after[:len(after) - len(rest)], _leading_marks(rest, reads_as_word)
    quotes = ""
    if rest[len(marks):len(marks) + 1].strip():
        cut = next((i for i, char in enumerate(marks) if _opens_word(char)), len(marks))
        marks, quotes = marks[:cut], rest[cut:]
        quotes = quotes[:next((i for i, char in enumerate(quotes) if not _opens_word(char)), len(quotes))]
    return gap + marks if marks else "", quotes


def _first_bounds(reads: List[Iterator[_Piece]], start: int) -> Optional[Tuple[Segment, Segment]]:
    """The bounds of the first piece in *reads* from index *start* on, the text parts after a block.

    The piece read to find them stays first in its part.
    """
    for index in range(start, len(reads), 2):
        first = next(reads[index], None)
        if first is not None:
            reads[index] = itertools.chain([first], reads[index])
            return first.bounds
    return None


def _join(pieces: Iterable[_Piece], space: Segment) -> _Piece:
    """*pieces* joined into one by the rules of tts-punctuation.

    A piece that ends in a clause symbol or in the word break *space* joins
    the next piece with no space, and any other piece takes *space* before
    the next, as :func:`~scriptconv.phonemizers.base.join_sentences` joins
    sentences. The start and end symbols of bounded pieces stay out of the
    join, so where two of them join, the inner end and start symbols go with
    their stream values. Every :class:`Chunk` size and
    :meth:`TextFrontend.phonemize_flat` join by this function.
    """
    joined = _Piece([])
    for piece in pieces:
        if not piece.phonemes:
            continue
        if joined.phonemes and not (joined.ends_in_token or joined.phonemes[-1] == space.phonemes[0]):
            joined.add(space.phonemes, space.streams)
        joined.add(piece.phonemes, piece.streams)
        joined.bounds = joined.bounds or piece.bounds
        joined.ends_in_token = piece.ends_in_token
        joined.ends_sentence = piece.ends_sentence
        joined.ends_paragraph = piece.ends_paragraph
    return joined


def _split_blocks(text: str) -> List[str]:
    r"""*text* split around its inline blocks, with text at even indices and blocks at odd ones.

    The result is that of ``re.split(r"(\[\[.*?\]\])", text)``: a block is the
    shortest ``[[...]]`` on one line. The scan is linear. An ``[[`` with no
    ``]]`` after it on its line opens no block, and no later ``[[`` on that
    line can either, so the scan goes on at the next line.
    """
    parts = []
    start = search = 0
    line_end = -1
    while (opening := text.find("[[", search)) != -1:
        if opening > line_end:
            line_end = text.find("\n", opening)
            if line_end == -1:
                line_end = len(text)
        closing = text.find("]]", opening + 2, line_end)
        if closing == -1:
            search = line_end
            continue
        parts += [text[start:opening], text[opening:closing + 2]]
        start = search = closing + 2
    parts.append(text[start:])
    return parts


def _split_blocks_to_read(text: str) -> List[str]:
    """*text* split as by :func:`_split_blocks`, with no empty block.

    An empty block, or one of only whitespace, reads as no text, so the text
    on its two sides joins into one piece.
    """
    parts = _split_blocks(text)
    joined: List[str] = []
    pieces = parts[:1]
    for block, after in zip(parts[1::2], parts[2::2]):
        if block[2:-2].strip():
            joined += ["".join(pieces), block]
            pieces = []
        pieces.append(after)
    joined.append("".join(pieces))
    return joined


class TextFrontend:
    """Text to phonemes through the fixed stage order.

    ``backend`` takes a phonemizer instance. ``None`` builds the one that
    ``config`` names. The frontend reads the backend with
    ``config.keep_punctuation`` and ``config.strict``. When an instance holds
    other values, the frontend reads a shallow copy with the configured values,
    so the caller's instance does not change.

    Raises:
        UnsupportedLanguageError: If the backend does not support the language.
        ImportError: In strict mode, if the diacritizer that the language needs
            is not installed. The message names the extra.
    """

    def __init__(self, config: FrontendConfig, backend: Optional[BasePhonemizer] = None):
        if backend is None:
            if config.phonemizer is None:
                backend = phonemizer_for_lang(config.lang, config.alphabet, model=config.model)
            else:
                backend = get_phonemizer(config.phonemizer, config.alphabet, config.model)
        if (backend.keep_punctuation, backend.strict) != (config.keep_punctuation, config.strict):
            backend = copy.copy(backend)
            backend.keep_punctuation = config.keep_punctuation
            backend.strict = config.strict
        self.config = config
        self.backend = backend
        self._space = backend.word_break()
        stages = self._resolve(None)
        # The Grapheme and Unicode backends take any language and have no get_lang.
        if hasattr(backend, "get_lang"):
            backend.get_lang(stages.lang)
        if config.strict and stages.diacritize:
            package, extra = _DIACRITIZER_PACKAGES.get(
                _diacritizer_family(stages.lang), (None, None))
            if package and importlib.util.find_spec(package) is None:
                raise ImportError(
                    f"diacritization for {stages.lang!r} needs {package} — install "
                    f"with `pip install scriptconv[{extra}]`")

    def with_backend(self, backend: BasePhonemizer) -> "TextFrontend":
        """A frontend with this configuration and another backend instance."""
        return TextFrontend(self.config, backend)

    def phonemize_lazy(self, text: str, stages: Optional[Stages] = None) -> Iterator[List[str]]:
        """Phonemes of *text*, one list per chunk, as each chunk is read.

        :attr:`Stages.chunk` sets the size of a chunk. At every size the
        stages read the text in the same order, the frontend cuts the read
        text into sentences, and a chunk is a sentence, a clause, the
        sentences of a paragraph, or every sentence. The sentences of a chunk
        join by the rule of :meth:`phonemize_flat`. A clause that ends in a
        clause symbol, with another clause after it in its sentence, takes a
        space after the symbol, as inside the sentence. The frontend cuts the
        read text at its paragraph breaks before it cuts sentences, so a
        paragraph break also ends a sentence, as after a title with no full
        stop or after a ``!``. A ``reads_whole_text`` backend reports its own
        paragraph ends.

        A block's symbols join the chunk before the block, and the text after
        a block starts a new sentence, but a new paragraph only after a
        paragraph break. A closing mark after a block, right after it or
        after whitespace, closes the block's sentence, so it goes with the
        block's chunk, and no chunk starts with such a mark. A symbol that the
        backend reads as a word, such as ``%``, is no such mark, and a quote
        after whitespace that opens the next word stays with that word (see
        :func:`_marks_after`). A backend with a mark table gets the marks from
        it, also where no word follows them (see :meth:`_take_marks`). A
        block that starts a sentence after a sentence that ends in a clause
        symbol follows that symbol with no space. A block before the first text is a chunk of its own at
        ``sentence`` and ``clause`` size, with the marks right after it, and
        it starts the chunk after it at ``paragraph`` and ``none`` size. A
        chunk of bounded segments has one start and one end symbol, with the
        block's symbols between them. A chunk that gives no phonemes is not
        yielded.
        """
        for chunk in self._chunk_pieces(text, self._resolve(stages)):
            yield chunk.phonemes

    def phonemize(self, text: str, stages: Optional[Stages] = None) -> List[List[str]]:
        """Phonemes of *text*, one list per chunk."""
        return list(self.phonemize_lazy(text, stages))

    def segments(self, text: str, stages: Optional[Stages] = None) -> Iterator[Segment]:
        """The chunks of :meth:`phonemize_lazy`, each with the backend's side streams.

        The streams of the backend, such as dizione's stress or Shami's
        language ids, stay in step with the symbols at every size. A word
        break that the frontend adds takes the values of the backend's
        :meth:`~scriptconv.phonemizers.base.BasePhonemizer.word_break`, and a
        clause symbol or a block's symbol takes 0 in every stream. Where two
        bounded segments of the backend join, the inner end and start symbols
        go with their stream values. Each chunk is a :class:`~scriptconv.phonemizers.base.Segment`
        whose symbols hold the clause symbols, so its ``mark`` is ``None``.
        """
        for chunk in self._chunk_pieces(text, self._resolve(stages)):
            yield Segment(tuple(chunk.phonemes), None, chunk.ends_sentence,
                          {name: tuple(values) for name, values in chunk.streams.items()},
                          chunk.ends_paragraph, chunk.bounds is not None)

    def phonemize_flat(self, text: str, stages: Optional[Stages] = None) -> List[str]:
        """Phonemes of *text* as one list, for training.

        The list is the sentence chunks of :meth:`phonemize` joined by the
        rule of tts-punctuation, for every backend. A sentence that ends in a
        clause symbol, or in a space, joins the next one with no space, and
        any other sentence takes one space before the next, as
        :func:`~scriptconv.phonemizers.base.join_sentences` joins them. Where
        two bounded segments join, the inner end and start symbols go. So the
        ``none`` size gives this list as its one chunk.
        """
        stages = dataclasses.replace(self._resolve(stages), chunk=Chunk.SENTENCE)
        return _join(self._pieces(text, stages, clauses=False), self._space).closed(self._space).phonemes

    def prepare(self, text: str, stages: Optional[Stages] = None) -> str:
        """*text* after the stages, for an engine that reads text, not phonemes.

        Blocks stay as written, and the chunks stay joined as the text writes
        them. The stages read each piece of text between blocks without the
        whitespace at its edges, and that whitespace stays around the result.
        """
        stages = self._resolve(stages)
        parts = _split_blocks(text)
        for index in range(0, len(parts), 2):
            part = parts[index]
            if core := part.strip():
                start = len(part) - len(part.lstrip())
                parts[index] = (part[:start] + self._staged(core, stages)
                                + part[start + len(core):])
        return "".join(parts)

    def identity(self) -> PhonemizerIdentity:
        """What phonemizes this frontend's language, with :data:`FRONTEND_VERSION`."""
        return dataclasses.replace(self.backend.identity(self._resolve(None).lang),
                                   frontend=FRONTEND_VERSION)

    def register(self, graph: ConversionGraph) -> None:
        """Add a ``text -> <alphabet>`` edge that runs :meth:`phonemize_lazy`.

        The edge gives one phoneme list per sentence, not a string, so it ends
        a route. A ``stages=`` routing context key passes to the call.
        """
        graph.register(Edge("text", self.config.alphabet.value,
                            lambda text, stages=None, **_: self.phonemize_lazy(text, stages)))

    def _resolve(self, stages: Optional[Stages]) -> Stages:
        """The stages of one call, with every value set.

        An explicit value of the call wins, then the frontend's own. The
        resolved ``normalize`` and ``diacritize`` are ``False`` when the
        backend owns the stage.
        """
        own = self.config.stages
        if stages is None:
            stages = own
        lang = stages.lang or own.lang or self.config.lang
        normalize = stages.normalize if stages.normalize is not None else own.normalize
        enabled = stages.diacritize if stages.diacritize is not None else own.diacritize
        if enabled is None:
            from linguatag import lang_distance
            enabled = lang_distance(lang, "ar") <= _ARABIC_DISTANCE
        return Stages(
            normalize=normalize is not False and "normalize" not in self.backend.owned_stages,
            diacritize=enabled and "diacritize" not in self.backend.owned_stages,
            diacritizer_model=stages.diacritizer_model or own.diacritizer_model,
            lang=lang,
            casing=stages.casing or own.casing,
            chunk=stages.chunk or own.chunk or Chunk.SENTENCE,
        )

    def _chunk_pieces(self, text: str, stages: Stages) -> Iterator[_Piece]:
        """The chunks of :meth:`phonemize_lazy`, each with its streams."""
        if stages.chunk in (Chunk.SENTENCE, Chunk.CLAUSE):
            yield from (piece.closed(self._space) for piece in self._pieces(text, stages, stages.chunk == Chunk.CLAUSE)
                        if piece.phonemes)
            return
        paragraph: List[_Piece] = []
        for piece in self._pieces(text, stages, clauses=False):
            paragraph.append(piece)
            if stages.chunk == Chunk.PARAGRAPH and piece.ends_paragraph:
                if (joined := _join(paragraph, self._space)).phonemes:
                    yield joined.closed(self._space)
                paragraph = []
        if (joined := _join(paragraph, self._space)).phonemes:
            yield joined.closed(self._space)

    def _pieces(self, text: str, stages: Stages, clauses: bool) -> Iterator[_Piece]:
        """Steps 1 to 5: the sentences of *text*, or its clauses with *clauses*, with the blocks."""
        parts = _split_blocks_to_read(text)
        if len(parts) == 1:
            yield from self._text_pieces(parts[0], stages, clauses)
            return
        reads = [self._text_pieces(part, stages, clauses) if index % 2 == 0 else iter(())
                 for index, part in enumerate(parts)]
        # A block can extend the piece before it, so that piece is held
        # until the next part is known.
        held = _Piece([])
        text_read, marks, quotes, gap = False, "", "", ""
        for index, part in enumerate(parts):
            if index % 2:
                if marks:
                    # no word follows the marks after the block before
                    self._take_marks(held, None, marks)
                    marks = ""
                if not text_read and held.bounds is None:
                    # a block before the first text has the bounds of the text after it
                    held.bounds = _first_bounds(reads, index + 1)
                self._add_block(held, parts, index, stages)
                marks, quotes = _marks_after(parts[index + 1], self._reads_as_word)
                continue
            after_block = index > 0
            for piece in reads[index]:
                if after_block:
                    # the piece that ends in a block ends a paragraph where a
                    # paragraph break comes before the next word, and nowhere else
                    held.ends_paragraph = bool(_PARAGRAPH_BREAK.search(gap + _WORDLESS_START.match(part)[0]))
                    after_block = False
                text_read = True
                if quotes:
                    self._open_with_quotes(held, piece, quotes)
                    quotes = ""
                if marks:
                    self._take_marks(held, piece, marks)
                    marks = ""
                    if not piece.phonemes:
                        continue
                if held.phonemes:
                    yield held
                held = piece
            gap = gap + part if after_block else part[len(part.rstrip()):]
        if marks:
            self._take_marks(held, None, marks)
        if held.phonemes:
            yield held

    def _take_marks(self, held: _Piece, piece: Optional[_Piece], marks: str) -> None:
        """Move the symbols at the start of *piece* that write *marks* to the end of *held*.

        *held* ends in a block, and *marks* are the closing marks after the
        block in the text (see :func:`_marks_after`). Such a mark closes the
        block's sentence, so it goes with the block, in place of the word
        break before it, as tts-punctuation puts a closing mark with the
        sentence that it ends. A backend with a mark table
        (:meth:`~scriptconv.phonemizers.base.BasePhonemizer.mark_symbols`)
        writes the symbols of its table for the marks after a word, and the
        symbols of the table at the start of *piece* are its read of the marks
        alone. The frontend writes the table, and removes those symbols from
        *piece*. *piece* is ``None`` where no word follows the marks before
        the next block or the end of the text. A backend with no table writes
        symbols whose characters are all in *marks*. A backend that drops the
        marks writes no such symbols, and then *held* keeps its word break.
        """
        phonemes = piece.phonemes if piece is not None else []
        table = self.backend.mark_symbols(marks)
        if table is None:
            count = next((i for i, symbol in enumerate(phonemes) if not set(symbol) <= set(marks.lstrip())),
                         len(phonemes))
            symbols = phonemes[:count]
            streams = {name: values[:count] for name, values in piece.streams.items()} if count else {}
        else:
            symbols, streams = list(table.phonemes), table.streams
            # the backend can read the marks alone as only some of the symbols of its
            # table, as dizione drops ";*" alone as an emoticon
            count = len(symbols) if phonemes[:len(symbols)] == symbols else next(
                (i for i, symbol in enumerate(phonemes) if symbol not in symbols), len(phonemes))
        if not symbols:
            return
        space = list(self._space.phonemes)
        if held.phonemes[-len(space):] == space:
            for _ in space:
                held.pop()
        held.add(symbols, streams)
        if count:
            if phonemes[count:count + len(space)] == space:
                count += len(space)
            del phonemes[:count]
            for values in piece.streams.values():
                del values[:count]
        held.ends_in_token = held.bounds is not None or (
            self._keeps_punctuation() and held.phonemes[-1] in _CLAUSE_TOKENS)

    def _reads_as_word(self, char: str) -> bool:
        """Whether the backend's mark table shows that it reads *char* as a word.

        The table then holds the backend's word break, as dizione writes
        ``<sp> p ɚ s ɛ n t`` for ``%`` after a word. For a backend with no
        table, :meth:`_take_marks` moves only symbols whose characters are in
        the marks, never a word.
        """
        table = self.backend.mark_symbols(char)
        return table is not None and not set(table.phonemes).isdisjoint(self._space.phonemes)

    def _open_with_quotes(self, held: _Piece, piece: _Piece, quotes: str) -> None:
        """Remove the word break at the end of *held* where *piece* starts with the symbols that write *quotes*.

        *held* ends in a block, and *quotes* open the word after it (see
        :func:`_marks_after`). A backend with a mark table writes those
        symbols right after the word before them, with no word break, as
        dizione writes ``ɛ k s " ɡ oʊ`` for ``x "go``. A backend that drops
        the quotes, as dizione drops the apostrophe of ``’tis``, keeps the
        word break.
        """
        table = self.backend.mark_symbols(quotes)
        if table is None or not table.phonemes or piece.phonemes[:len(table.phonemes)] != list(table.phonemes):
            return
        space = list(self._space.phonemes)
        if held.phonemes[-len(space):] == space:
            for _ in space:
                held.pop()
            held.ends_in_token = True

    def _text_pieces(self, text: str, stages: Stages, clauses: bool) -> Iterator[_Piece]:
        """Steps 2 to 5 on text with no block, one piece per sentence, or per clause with *clauses*."""
        if not text.strip():
            return
        if self.backend.reads_whole_text:
            yield from self._whole_text_read(text, stages, clauses)
            return
        if "normalize" in self.backend.owned_stages:
            # The backend reads the text with its own rules, so it gets the
            # sentences as written, cut before casing.
            paragraphs = [[self._read(sentence, stages) for sentence in sentences]
                          for sentences in _paragraph_sentences(text)]
        else:
            paragraphs = _paragraph_sentences(self._read(text, stages))
        # A backend that overrides its output appends no clause symbol, so
        # its marks join as any other symbol.
        tokens = self.backend._keeps_punctuation()
        for sentences in paragraphs:
            for number, sentence in enumerate(sentences, 1):
                yield from self._sentence_pieces(sentence, stages, clauses, tokens,
                                                 ends_paragraph=number == len(sentences))

    def _sentence_pieces(self, sentence: str, stages: Stages, clauses: bool, tokens: bool,
                         ends_paragraph: bool) -> Iterator[_Piece]:
        """Step 5 on one sentence of a backend that does not read whole text, one piece per sentence or clause.

        *tokens* tells whether the backend appends clause symbols.
        """
        texts = _clauses(sentence) if clauses else [sentence]
        for index, part in enumerate(texts):
            if not part.strip():
                continue
            # A chunk never starts with a space, also for a backend that
            # keeps the spaces it reads.
            part = self._diacritize(part, stages).lstrip()
            read = [piece for piece in map(_Piece.of, self.backend.phonemize_segments(part, stages.lang))
                    if piece.phonemes]
            self._check_read(part, [p for piece in read for p in piece.phonemes], stages)
            words_follow = clauses and any(c.isalnum() for c in "".join(texts[index + 1:]))
            for count, piece in enumerate(read, 1):
                piece.ends_in_token = tokens and piece.phonemes[-1] in _CLAUSE_TOKENS
                if count == len(read):
                    if words_follow and piece.ends_in_token:
                        piece.add(self._space.phonemes, self._space.streams)
                    piece.ends_sentence = not words_follow
                    piece.ends_paragraph = ends_paragraph and not words_follow
                yield piece

    def _whole_text_read(self, text: str, stages: Stages, clauses: bool) -> Iterator[_Piece]:
        """Steps 2 to 5 for a ``reads_whole_text`` backend, one piece per sentence, or per segment with *clauses*.

        Above :attr:`FrontendConfig.whole_text_limit` characters, the text is
        first cut at its paragraph breaks, and each cut ends a sentence and a
        paragraph. Each piece is diacritized and read whole, and the backend
        reports its segments. A segment's clause symbol follows it, with a
        space after ``, : ;``. A segment that ends in a clause symbol, with
        another segment after it in its sentence, takes a space after the
        symbol, and the pieces of a sentence join by :func:`_join`.
        """
        text = self._read(text, stages)
        cuts = self._whole_text_pieces(text)
        for cut in cuts:
            if not cut.strip():
                continue
            cut = self._diacritize(cut, stages)
            pieces: List[_Piece] = []
            sentence: List[_Piece] = []
            for segment in self.backend.phonemize_segments(cut, stages.lang):
                if segment.phonemes:
                    if sentence:
                        self._continue_sentence(sentence[-1])
                    sentence.append(self._segment_piece(segment))
                if sentence and segment.ends_sentence:
                    sentence[-1].ends_paragraph = segment.ends_paragraph
                    pieces += sentence if clauses else [_join(sentence, self._space)]
                    sentence = []
            if sentence:
                pieces += sentence if clauses else [_join(sentence, self._space)]
            if not pieces:
                self._check_read(cut, [], stages)
                continue
            if len(cuts) > 1:
                pieces[-1].ends_sentence = pieces[-1].ends_paragraph = True
            yield from pieces

    def _segment_piece(self, segment: Segment) -> _Piece:
        """*segment* with its clause symbol, when the frontend keeps punctuation.

        A bounded segment holds its marks, and its mark only tells that it
        ends in one.
        """
        piece = _Piece.of(segment)
        if segment.bounded:
            piece.ends_in_token = segment.mark is not None
        elif self.backend.keep_punctuation and segment.mark is not None:
            piece.add([segment.mark])
            if segment.mark in _PAUSE_PUNCTUATION:
                piece.add(self._space.phonemes, self._space.streams)
            piece.ends_in_token = True
        return piece

    def _continue_sentence(self, piece: _Piece) -> None:
        """Mark *piece* as a clause that another clause of its sentence follows.

        A clause symbol that the frontend appended takes a space after it, as
        the text writes a space before the next word.
        """
        piece.ends_sentence = False
        if piece.ends_in_token and piece.bounds is None and piece.phonemes[-1] != self._space.phonemes[0]:
            piece.add(self._space.phonemes, self._space.streams)

    @staticmethod
    def _split(text: str, chunk: Chunk) -> List[str]:
        """*text* cut into chunks of the size *chunk*, for the diacritizer of :meth:`prepare`."""
        if chunk == Chunk.NONE:
            return [text]
        if chunk == Chunk.PARAGRAPH:
            return _paragraphs(text)
        sentences = [sentence for paragraph in _paragraph_sentences(text) for sentence in paragraph]
        if chunk == Chunk.CLAUSE:
            return [clause for sentence in sentences for clause in _clauses(sentence)]
        return sentences

    def _whole_text_pieces(self, text: str) -> List[str]:
        """*text* cut at its paragraph breaks when it is longer than :attr:`FrontendConfig.whole_text_limit`."""
        limit = self.config.whole_text_limit
        return [text] if limit is None or len(text) <= limit else _paragraphs(text)

    def _add_block(self, piece: _Piece, parts: List[str], index: int, stages: Stages) -> None:
        """Append the symbols of the inline block at *index* of a split text to *piece*.

        A space, tab or line break before the block in the text, also with
        marks between it and the block, or a space after the block, becomes
        the backend's word break, unless *piece* is empty or already ends in
        one. :meth:`_before_block` reads what comes before the block, and
        :meth:`_mark_after` reads the clause symbol after it. A block whose
        symbols end in a character that is also a clause symbol, with no
        clause symbol after it, takes a word break before the next word,
        because that character ends no sentence. The piece then ends in a
        clause symbol that joins the next sentence with no space only when a
        mark follows the block.

        The block's symbols go inside the start and end symbols of a bounded
        piece. A block before the first text takes the bounds of the text
        after it. The backend writes the marks of a bounded piece itself, so
        the frontend reads no mark around the block: a word break comes
        before the block where the text has whitespace and the piece does not
        end in a mark, and after it where the text has whitespace or a mark.
        :meth:`_take_marks` replaces that word break with the symbols that the
        backend writes for the mark.
        """
        text, after = parts[index - 1], parts[index + 1]
        symbols = parts[index][2:-2].strip()
        phonemes = piece.phonemes
        space, space_streams = self._space.phonemes, self._space.streams
        if piece.bounds is not None:
            if _SPACE_BEFORE_BLOCK.search(text) and phonemes and phonemes[-1] != space[0] and not piece.ends_in_token:
                piece.add(space, space_streams)
            piece.add(symbols)
            piece.ends_in_token = not after[:1].isspace() and not _leading_marks(after)
            if not piece.ends_in_token:
                piece.add(space, space_streams)
            return
        before = self._before_block(phonemes, text, index > 1)
        if before is False:
            piece.pop()
        if _SPACE_BEFORE_BLOCK.search(text) and phonemes and phonemes[-1] != space[0] and not before:
            piece.add(space, space_streams)
        piece.add(symbols)
        mark = self._mark_after(after, index + 2 < len(parts), stages)
        piece.ends_in_token = bool(mark)
        if mark:
            piece.add(mark[0])
            if mark[1:]:
                piece.add(space, space_streams)
        elif after.startswith(" ") or (
                self._keeps_punctuation() and symbols[-1] in _CLAUSE_TOKENS
                and self.backend.remove_punctuation(after).strip()):
            if phonemes[-1] != space[0]:
                piece.add(space, space_streams)

    def _mark_after(self, after: str, block_follows: bool, stages: Stages) -> Optional[str]:
        """The clause symbol in the text *after* a block, and the space after that symbol.

        *block_follows* tells whether a block that holds symbols follows
        *after*. The backend reads the text after a block as a sentence that
        starts with a clause with no words, and drops that clause's symbol. The
        symbol belongs to the clause that the block ends, so the mark is read
        as in the same text with a plain word in place of each block: the
        first sentence after the stages, split into clauses by the backend's
        rules. A space follows ``, : ;``, and it follows ``. ? !`` when the
        sentence holds another clause after the block's. Only a backend that
        keeps punctuation gives a mark.
        """
        if not self._keeps_punctuation():
            return None
        # A letter or digit first gives the clause a word, and no text gives
        # it no mark, so the stages need not run. This assumes that no stage
        # deletes every letter and digit before the mark, that no stage adds
        # a mark in front of the first letter or digit, and that no stage adds
        # a mark to text that holds only words.
        first = after.lstrip()[:1]
        if not first or first.isalnum():
            return None
        text = _BLOCK_WORD + after
        if block_follows:
            text += _BLOCK_WORD
        sentence = self._diacritize(_sentence_tokenize(self._read(text, stages))[0], stages)
        (clause, mark), *rest = split_clauses(sentence)
        if not mark or self.backend.remove_punctuation(clause).casefold() != _BLOCK_WORD:
            return None
        if mark in _PAUSE_PUNCTUATION or any(self.backend.remove_punctuation(c) for c, _ in rest):
            return mark + " "
        return mark

    def _before_block(self, phonemes: List[str], text: str, after_block: bool) -> Optional[bool]:
        """How a block follows *phonemes* and the *text* before it, read as in the plain text.

        *text* reads with a plain word in place of the block, and in front of
        it when *after_block*, for the block before it.

        ``True``: the block starts a sentence after one that ends in a clause
        symbol, so no space comes before it, by the rule of
        :func:`~scriptconv.phonemizers.base.join_sentences`. ``False``: the
        clause symbol at the end of *phonemes* ends no clause in the plain
        text, as after ``Tudo."``, after ``Dr.`` or directly before the block.
        The block continues the clause, so the symbol goes. ``None``: neither.
        Only a backend that keeps punctuation gives ``True`` or ``False``.

        The symbol goes only when it is the mark of the last clause of
        *text*, which the backend writes after that clause. Any other symbol
        is a phoneme, such as an X-SAMPA ``:`` for length, and it stays.
        """
        if not (self._keeps_punctuation() and phonemes
                and phonemes[-1] in _CLAUSE_TOKENS):
            return None
        # The text is read without the stages. This assumes that no stage
        # adds or removes the mark that ends a clause.
        *before, sentence = _sentence_tokenize(
            (_BLOCK_WORD if after_block else "") + text + _BLOCK_WORD)
        clauses = self._clauses_with_words((*before, sentence))
        mark = clauses[-2][1] if len(clauses) > 1 else None
        if self.backend.remove_punctuation(clauses[-1][0]).casefold() != _BLOCK_WORD or not mark:
            read = self._clauses_with_words(_sentence_tokenize(text))
            return False if read and read[-1][1] == phonemes[-1] else None
        return self.backend.remove_punctuation(sentence).strip().casefold() == _BLOCK_WORD or None

    def _keeps_punctuation(self) -> bool:
        """Whether the phonemes carry clause symbols."""
        return self.backend._keeps_punctuation() or (
            self.backend.reads_whole_text and self.backend.keep_punctuation)

    def _clauses_with_words(self, sentences: Iterable[str]) -> List[Tuple[str, Optional[str]]]:
        """The ``(clause, mark)`` pairs of *sentences* whose clause holds a word.

        A clause with no word gives no phonemes, and a sentence with no word
        gives none either, so these are the clauses that the backend reads.
        """
        return [(clause, mark) for sentence in sentences
                for clause, mark in split_clauses(sentence)
                if self.backend.remove_punctuation(clause).strip()]

    def _read(self, text: str, stages: Stages) -> str:
        """Steps 2 and 3 on one piece of text: normalise, then apply casing."""
        if stages.normalize and self.config.normalizer is not None:
            text = self._stage("normalize", stages, self.config.normalizer, text, stages.lang)
        if stages.casing is not None:
            text = self._stage("casing", stages, stages.casing, text)
        return text

    def _diacritize(self, text: str, stages: Stages) -> str:
        """Step 5 on one chunk, before the backend."""
        if stages.diacritize:
            text = self._stage("diacritize", stages, diacritize, text, stages.lang,
                               diacritizer_model=stages.diacritizer_model)
        return text

    def _staged(self, text: str, stages: Stages) -> str:
        """Steps 2 to 5 on one piece of text, with its chunks joined back as the text writes them."""
        text = self._read(text, stages)
        if not stages.diacritize:
            return text
        if self.backend.reads_whole_text:
            chunks = self._whole_text_pieces(text)
        else:
            chunks = self._split(text, stages.chunk)
        return "".join(gap + (self._diacritize(chunk, stages) if chunk.strip() else chunk)
                       for gap, chunk in _with_gaps(text, chunks))

    def _stage(self, name: str, stages: Stages, function: Callable[..., str],
               text: str, *args, **kwargs) -> str:
        """*function* on *text* without the whitespace at its edges, with that whitespace put back around the result.

        Text of only whitespace goes through as it is. A failure continues
        with *text*, or raises in strict mode.
        """
        start, end = len(text) - len(text.lstrip()), len(text.rstrip())
        if start == len(text):
            return text
        try:
            return text[:start] + function(text[start:end], *args, **kwargs) + text[end:]
        except Exception as e:
            if self.config.strict:
                raise StageError(f"{name} failed for lang={stages.lang!r}: {e}") from e
            LOG.warning("%s failed for lang=%r: %s. The text continues without it.",
                        name, stages.lang, e)
            return text

    def _check_read(self, text: str, phonemes: List[str], stages: Stages) -> None:
        """Warn, or raise in strict mode, when text with letters or digits gave no phonemes."""
        if any(c.isalnum() for c in text) and not any(p.strip() for p in phonemes):
            message = f"no phonemes for {text!r} (lang={stages.lang!r})"
            if self.config.strict:
                raise UnreadTextError(message, (text,))
            LOG.warning(message)
