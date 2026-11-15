"""The text frontend: text stages and a phonemizer backend in one fixed order.

:class:`TextFrontend` takes text to phonemes. Every path runs the same order:

1. Split out inline ``[[phonemes]]`` blocks. No stage reads the text inside a
   block, and its symbols reach the output as written.
2. Run the normalisation hook on the whole text, if the caller set one.
3. Apply casing, if the call sets a casing function.
4. Cut the normalised text into chunks of the size :class:`Chunk` names:
   sentences by default.
5. For each chunk, lazily: diacritize, then run the backend. The backend
   cuts the chunk into clauses and appends the clause symbols.

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
  appends the clause symbols. Above
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
import logging
import re
from typing import Callable, Iterable, Iterator, List, Optional, Tuple

from scriptconv.diacritics import _DIACRITIZER_PACKAGES, _diacritizer_family, diacritize
from scriptconv.graph import ConversionGraph, Edge
from scriptconv.phonemizers.base import (
    _CLAUSE_BREAK,
    _CLAUSE_TOKENS,
    _PAUSE_PUNCTUATION,
    _join,
    BasePhonemizer,
    PhonemizerIdentity,
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

# scripts/time_owner_backends.py: dizione reads 10,000 characters in 146.5 ms and 6,000 in 88 to 97 ms (medians of 5).
WHOLE_TEXT_LIMIT = 6_000
"""The default of :attr:`FrontendConfig.whole_text_limit`."""

# One or more blank lines.
_PARAGRAPH_BREAK = re.compile(r"(\n(?:[^\S\n]*\n)+)")

# The word that stands for a block when the frontend reads the mark after it.
_BLOCK_WORD = "a"
# Text that ends in whitespace and then only marks. The marks join the block
# after them as they join a plain word, and the whitespace stays.
_SPACE_BEFORE_BLOCK = re.compile(r"\s\W*$")

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

    The stage order is the same at every size, and the clause symbols join two
    chunks the same way at every size, so the size moves only the cuts.
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
    """The chunk size. ``None`` takes the frontend's value, and when that is
    ``None`` too, a chunk is a sentence."""


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

    Each clause keeps the marks that end it.
    """
    clauses = []
    start = 0
    for match in _CLAUSE_BREAK.finditer(sentence):
        clauses.append(sentence[start:match.end()])
        start = match.end()
    clauses.append(sentence[start:])
    return clauses


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

        :attr:`Stages.chunk` sets the size of a chunk. At ``sentence`` and
        ``clause`` size, a block's symbols join the chunk before the block,
        and the text after a block starts a new chunk. A block that starts a
        chunk after a chunk that ends in a clause symbol follows that symbol
        with no space, as the two chunks join in :meth:`phonemize_flat`. At
        ``paragraph`` and ``none`` size, the stages read the whole text, and a
        chunk is what :meth:`phonemize_flat` gives for its part of the read
        text. A chunk that gives no phonemes is not yielded.
        """
        stages = self._resolve(stages)
        if stages.chunk in (Chunk.PARAGRAPH, Chunk.NONE):
            text = self._read_around_blocks(text, stages)
            read = dataclasses.replace(stages, normalize=False, casing=None)
            for piece in self._split(text, stages.chunk):
                if phonemes := self._flat(piece, read):
                    yield phonemes
            return
        parts = _split_blocks_to_read(text)
        if len(parts) == 1:
            yield from self._chunks(parts[0], stages)
            return
        # A block can extend the chunk before it, so that chunk is held
        # until the next part is known.
        held: List[str] = []
        for index, part in enumerate(parts):
            if index % 2:
                self._add_block(held, parts, index, stages)
                continue
            for chunk in self._chunks(part, stages):
                if held:
                    yield held
                held = chunk
        if held:
            yield held

    def phonemize(self, text: str, stages: Optional[Stages] = None) -> List[List[str]]:
        """Phonemes of *text*, one list per chunk."""
        return list(self.phonemize_lazy(text, stages))

    def phonemize_flat(self, text: str, stages: Optional[Stages] = None) -> List[str]:
        """Phonemes of *text* as one list, for training.

        The stages run on each piece of text between blocks in the order of
        :meth:`phonemize`: the piece is normalised whole, then diacritized
        chunk by chunk. The backend's ``phonemize_to_list`` reads the piece
        and joins its sentences by the rule of
        :func:`~scriptconv.phonemizers.base.join_sentences`. A
        ``reads_whole_text`` backend reports its segments, and the frontend
        joins them by the same rule. The text after a block starts a new
        sentence, as in :meth:`phonemize`, so one space separates the block
        from it, unless the block ends in a space or in a clause symbol. No
        sentence of :meth:`phonemize` starts with that space. By the same
        rule, a block that starts a sentence after a sentence that ends in a
        clause symbol takes no space before it.
        """
        return self._flat(text, self._resolve(stages))

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

    def _flat(self, text: str, stages: Stages) -> List[str]:
        """:meth:`phonemize_flat` with the stages resolved."""
        parts = _split_blocks_to_read(text)
        phonemes: List[str] = []
        ends_in_token = False
        for index, part in enumerate(parts):
            if index % 2:
                ends_in_token = self._add_block(phonemes, parts, index, stages)
            elif part:
                if self.backend.reads_whole_text:
                    read = _join(self._whole_text_chunks(part, stages))
                else:
                    part = self._staged(part, stages)
                    read = self.backend.phonemize_to_list(part, stages.lang)
                    self._check_read(part, read, stages)
                if read and phonemes and phonemes[-1] != " " and not ends_in_token:
                    phonemes.append(" ")
                phonemes.extend(read)
        return phonemes

    def _chunks(self, text: str, stages: Stages) -> Iterator[List[str]]:
        """Steps 2 to 5 on text with no block, one phoneme list per sentence or clause."""
        if not text.strip():
            return
        if self.backend.reads_whole_text:
            yield from (chunk for chunk, _ in self._whole_text_chunks(
                text, stages, clauses=stages.chunk is Chunk.CLAUSE))
            return
        if "normalize" in self.backend.owned_stages:
            # The backend reads the text with its own rules, so it gets the
            # sentences as written, cut before casing.
            chunks = [self._read(sentence, stages) for sentence in _sentence_tokenize(text)]
            if stages.chunk is Chunk.CLAUSE:
                chunks = [clause for sentence in chunks for clause in _clauses(sentence)]
        else:
            chunks = self._split(self._read(text, stages), stages.chunk)
        for chunk in chunks:
            if not chunk.strip():
                continue
            chunk = self._diacritize(chunk, stages)
            read = [list(phonemes) for phonemes in self.backend.phonemize_lazy(chunk, stages.lang)]
            self._check_read(chunk, [p for phonemes in read for p in phonemes], stages)
            yield from (phonemes for phonemes in read if phonemes)

    @staticmethod
    def _split(text: str, chunk: Chunk) -> List[str]:
        """Step 4: read *text* cut into chunks of the size *chunk*."""
        if chunk is Chunk.NONE:
            return [text]
        if chunk is Chunk.PARAGRAPH:
            return _paragraphs(text)
        sentences = _sentence_tokenize(text)
        if chunk is Chunk.CLAUSE:
            return [clause for sentence in sentences for clause in _clauses(sentence)]
        return sentences

    def _whole_text_chunks(self, text: str, stages: Stages,
                           clauses: bool = False) -> Iterator[Tuple[List[str], bool]]:
        """Steps 2 to 5 for a ``reads_whole_text`` backend, one phoneme list per sentence.

        Above :attr:`FrontendConfig.whole_text_limit` characters, the text is
        first cut at its paragraph breaks, and a paragraph break ends a
        sentence. Each piece is diacritized and read whole, and the backend
        reports its segments. The frontend groups them into sentences, or
        gives each segment alone with *clauses*. A segment's clause symbol
        follows it, with a space after ``, : ;``, and a space separates two
        segments in one sentence. Each sentence comes with whether it ends in
        a clause symbol.
        """
        text = self._read(text, stages)
        keep = self.backend.keep_punctuation
        phonemes: List[str] = []
        ends_in_token = False
        for piece in self._whole_text_pieces(text):
            if not piece.strip():
                continue
            piece = self._diacritize(piece, stages)
            read = False
            for segment in self.backend.phonemize_segments(piece, stages.lang):
                if segment.phonemes:
                    read = True
                    if phonemes and phonemes[-1] != " ":
                        phonemes.append(" ")
                    phonemes.extend(segment.phonemes)
                    ends_in_token = keep and segment.mark is not None
                    if ends_in_token:
                        phonemes.append(segment.mark)
                        if segment.mark in _PAUSE_PUNCTUATION:
                            phonemes.append(" ")
                if phonemes and (clauses or segment.ends_sentence):
                    yield phonemes, ends_in_token
                    phonemes, ends_in_token = [], False
            if not read:
                self._check_read(piece, [], stages)
            if phonemes:
                yield phonemes, ends_in_token
                phonemes, ends_in_token = [], False

    def _whole_text_pieces(self, text: str) -> List[str]:
        """*text* cut at its paragraph breaks when it is longer than :attr:`FrontendConfig.whole_text_limit`."""
        limit = self.config.whole_text_limit
        return [text] if limit is None or len(text) <= limit else _paragraphs(text)

    def _add_block(self, phonemes: List[str], parts: List[str], index: int, stages: Stages) -> bool:
        """Append the symbols of the inline block at *index* of a split text to *phonemes*.

        A space, tab or line break before the block in the text, also with
        marks between it and the block, or a space after the block, becomes a
        space symbol, unless *phonemes* is empty or
        already ends in a space. :meth:`_before_block` reads what comes before
        the block, and :meth:`_mark_after` reads the clause symbol after it. A
        block whose symbols end in a character that is also a clause symbol,
        with no clause symbol after it, takes a space before the next word,
        because that character ends no sentence. Returns whether *phonemes*
        ends in a clause symbol that joins the next sentence with no space.
        """
        text, after = parts[index - 1], parts[index + 1]
        symbols = parts[index][2:-2].strip()
        before = self._before_block(phonemes, text, index > 1)
        if before is False:
            phonemes.pop()
        if _SPACE_BEFORE_BLOCK.search(text) and phonemes and phonemes[-1] != " " and not before:
            phonemes.append(" ")
        phonemes.extend(symbols)
        mark = self._mark_after(after, index + 2 < len(parts), stages)
        if mark:
            phonemes.extend(mark)
            return True
        if after.startswith(" ") or (
                self._keeps_punctuation() and symbols[-1] in _CLAUSE_TOKENS
                and self.backend.remove_punctuation(after).strip()):
            if phonemes[-1] != " ":
                phonemes.append(" ")
        return False

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

    def _read_around_blocks(self, text: str, stages: Stages) -> str:
        """*text* with steps 2 and 3 on each piece between blocks, and the blocks as written."""
        parts = _split_blocks(text)
        return "".join(part if index % 2 else self._read(part, stages)
                       for index, part in enumerate(parts))

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
        """*function* on *text*. A failure continues with *text*, or raises in strict mode."""
        try:
            return function(text, *args, **kwargs)
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
