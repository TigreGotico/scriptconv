"""American English phonemizer: dizione.

dizione (https://github.com/n4ze3m/dizione, Apache-2.0) reads American English
text into phonemes. It looks words up in a dictionary built from CMUdict, picks
the reading of a homograph from the words around it, guesses unknown words with
a small model, and reads numbers, dates, money, units and abbreviations by its
own text rules. Its code is vendored under
:mod:`scriptconv.phonemizers._thirdparty.dizione`, and its built data
(dictionary, model and homograph weights) ships in ``built/`` beside it.

dizione reads the text itself, so this backend owns the ``normalize`` stage and
gets the text with its punctuation: ``"Dr. Patel paid $12.99"`` reaches the
engine as written. It reads whole text (``reads_whole_text``):
:class:`~scriptconv.frontend.TextFrontend` gives it the whole text, and dizione
cuts its own output at its own sentence and clause marks, so an abbreviation
such as ``Mrs.`` ends no sentence.
"""
import re
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union

try:
    import numpy  # noqa: F401  # the vendored model imports it at module level
except ImportError as e:
    raise ImportError(
        "numpy is required for the dizione phonemizer, whose model guesses the words that its dictionary "
        "lacks. Install it with 'pip install numpy' (or 'pip install scriptconv[en-phonemizers]')."
    ) from e

from scriptconv.phonemizers._thirdparty import dizione
from scriptconv.phonemizers._thirdparty.dizione.engine import Phonemizer as DizioneEngine
from scriptconv.phonemizers._thirdparty.dizione.homographs import SENTENCE_END
from scriptconv.phonemizers._thirdparty.dizione.symbols import (
    BOS,
    EOS,
    PHONE_SET,
    SP,
    STRESS_MARKS,
    SYMBOL_TO_ID,
    UNK,
    Phonemized,
    tokenize,
)
from scriptconv.phonemizers.base import (
    _PARAGRAPH_BREAK,
    _SEPARATING_MARKS,
    CLAUSE_PUNCTUATION,
    BasePhonemizer,
    MissingLanguageError,
    Segment,
    UnsupportedLanguageError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["DizionePhonemizer", "Phonemized", "DATA_DIR"]

DATA_DIR = Path(dizione.__file__).parent / "built"
"""dizione's built data, shipped in the wheel: the files of ``phonemizer/`` of
n4ze3m/tiny-voca at revision ``e5f9b11651a4db525fb207a56a91e4df2d1dd387``."""

# A run of marks that the clause table reads as "!" or "?" between two
# letters, as in "Sim!Não!": no clause break, but a word break.
_SEPARATING_RUN = re.compile(
    r"(?<=[^\W\d_])[" + re.escape("".join(sorted(_SEPARATING_MARKS))) + r"]+(?=[^\W\d_])")
# The marks that close a quotation or a bracket. They stay with the clause
# that ends before them, as the clause split of the frontend keeps them.
_QUOTES = frozenset({'"', "'"})
_DOUBLE_QUOTE = '"'
_CLOSING_BRACKET = ")"
# The word before the marks when dizione reads its mark table.
_MARK_WORD = "x"
# A sentence mark at the end of a text, with only closing marks after it.
_ENDS_IN_SENTENCE_MARK = re.compile(r"[.?!][^\w\s]*\s*$")
# The longest word of dizione's lexicon, "antidisestablishmentarianism" (28
# letters). A longer spelling is no word that dizione reads whole: the
# unknown-word model reads it, and the aligner then matches its letters to its
# phones with a dynamic program whose table holds one cell per letter and per
# phone, so a long run of letters exhausts the memory of the machine. Such a
# spelling is read in pieces of at most this many characters.
_MAX_WORD_LENGTH = 28


class _BoundedEngine(DizioneEngine):
    """dizione's engine, reading a spelling longer than :data:`_MAX_WORD_LENGTH` in pieces.

    Each piece is read as :meth:`word` reads a word, and the phonemes of the
    pieces join with no space, as dizione joins the parts of a hyphenated word
    (``sentence.groups``). A spelling that a table holds whole, such as a user
    override, is read whole.
    """

    def word(self, word):
        if len(word) <= _MAX_WORD_LENGTH or word in self._cache:
            return super().word(word)
        known = self.known(word)
        if known is not None:
            result = (known, "dictionary")
        else:
            result = (tuple(phone for start in range(0, len(word), _MAX_WORD_LENGTH)
                            for phone in self.word(word[start:start + _MAX_WORD_LENGTH])[0]),
                      "pieces")
        self._cache[word] = result
        return result


class DizionePhonemizer(BasePhonemizer):
    """dizione: American English text to IPA, and to dizione's own tokens.

    :meth:`phonemize_string` writes IPA. A stress mark stands directly before
    its vowel, as dizione writes it. A word break is a space. The control
    symbols (``<bos>``, ``<eos>``, ``<pad>``, ``<sp>``) are not written, and
    neither is punctuation, because ``.`` is the IPA syllable break.
    :meth:`tokens` returns dizione's own token sequence, with the ids, the
    punctuation and the stress stream.

    Args:
        alphabet: must be :attr:`Alphabet.IPA`.
        data_dir: a directory that holds dizione's built data. ``None`` reads
            the data that ships with scriptconv, :data:`DATA_DIR`.
        overrides: pronunciations that win over every other source, as
            dizione's ``Phonemizer(overrides=...)`` takes them: a mapping
            ``{word: pronunciation}``, a path to a table, or the text of a
            table. A pronunciation is CMUdict notation or phones with stress
            marks. A phone outside dizione's inventory raises ``ValueError``.
        tokens: :meth:`phonemize_segments` yields dizione's own tokens, not
            IPA. Each segment is a clause with its own ``<bos>`` and
            ``<eos>`` (``bounded``), its punctuation symbols, its mark, and
            the ``ids`` and ``stress`` streams, so that
            :meth:`TextFrontend.segments <scriptconv.frontend.TextFrontend.segments>`
            gives a voice the ids and stress of each chunk. The IPA methods
            do not change.

    A ``!`` or ``?`` between two letters with no space after it, as in
    ``Sim!Não!``, is no clause mark: dizione reads it as a space, so it gives
    no symbol (tts-punctuation). The methods read the text that way,
    :meth:`tokens` too.
    """

    owned_stages: ClassVar[frozenset[str]] = frozenset({"normalize"})
    reads_whole_text: ClassVar[bool] = True

    def __init__(self, alphabet: Alphabet = Alphabet.IPA,
                 data_dir: Optional[Union[str, Path]] = None,
                 overrides: Optional[Union[Dict[str, str], str, Path]] = None,
                 tokens: bool = False):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        super().__init__(alphabet)
        self.data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self.engine = _BoundedEngine(self.data_dir, overrides=overrides)
        self.tokens_mode = tokens

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """*target_lang* as a standard tag, when it is American English.

        A tag with no region takes its default region, so ``en`` is ``en-GB``
        and is refused.

        Raises:
            MissingLanguageError: If no language is given.
            UnsupportedLanguageError: If the tag is not English of the US.
        """
        if target_lang in (None, "", "und"):
            raise MissingLanguageError(f"no language provided to phonemize: {target_lang!r}")
        from linguatag import closest_lang, with_default_region
        tag = with_default_region(target_lang)
        if closest_lang(tag, ["en-US"], max_distance=0) is None:
            raise UnsupportedLanguageError(
                f"unsupported language code: {target_lang}; dizione reads en-US only")
        return tag

    def tokens(self, text: str) -> Phonemized:
        """dizione's token sequence for *text*: symbols, ids and stress.

        The result is what ``dizione.phonemize`` returns: the ids index
        ``dizione.symbols.SYMBOLS``, and the stress is 0 (none), 1 (primary)
        or 2 (secondary) for each symbol.

        Raises:
            ValueError: If the text is empty or has nothing to pronounce.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must not be empty")
        return tokenize(self.engine.pieces(_SEPARATING_RUN.sub(" ", text)))

    def token_segments(self, text: str) -> List[Phonemized]:
        """dizione's token sequence for *text*, cut into sentences.

        dizione reads the whole text once, as :meth:`tokens` does, and the
        sequence is cut at its clause marks as :meth:`phonemize_segments` cuts
        it. The clauses of one sentence are joined: the inner ``<eos>``
        ``<bos>`` pairs go, with their ids and stress. So each sentence has
        its own ``<bos>`` and ``<eos>``, and its ids, stress and unknown
        phones are those of its part of the whole sequence. Joined the same
        way, the sentences are :meth:`tokens`.

        Raises:
            ValueError: If the text is empty or has nothing to pronounce.
        """
        whole = self.tokens(text)
        closes = _quote_closes(self._rewrite(_SEPARATING_RUN.sub(" ", text), whole.symbols), whole.symbols)
        sentences: List[Phonemized] = []
        clauses: List[Phonemized] = []
        for clause, (_, _, _, ends_sentence) in zip(_token_clauses(whole, closes),
                                                     _clause_spans(whole.symbols, closes)):
            clauses.append(clause)
            if ends_sentence:
                sentences.append(_join_tokens(clauses))
                clauses = []
        return sentences

    def _clauses(self, text: str, tokens: bool = False) -> Iterator[Segment]:
        """Each clause of *text*, as :func:`_clause_spans` cuts dizione's tokens.

        A clause is IPA with a ``stress`` stream, or with *tokens* dizione's
        own tokens, bounded, with ``ids`` and ``stress`` streams.
        """
        if not text.strip():
            return
        text = _SEPARATING_RUN.sub(" ", text)
        pieces = self.engine.pieces(text)
        if not any(word for is_mark, words in pieces if not is_mark for word in words):
            return
        whole = tokenize(pieces)
        rewritten = self._rewrite(text, whole.symbols)
        paragraph_ends = _paragraph_ends(rewritten, pieces, whole.symbols)
        for start, end, mark, ends_sentence in _clause_spans(whole.symbols,
                                                             _quote_closes(rewritten, whole.symbols)):
            ends_paragraph = ends_sentence and any(place in paragraph_ends for place in range(start, end))
            if tokens:
                yield Segment((BOS, *whole.symbols[start:end], EOS), mark, ends_sentence,
                              {"ids": (whole.ids[0], *whole.ids[start:end], whole.ids[-1]),
                               "stress": (0, *whole.stress[start:end], 0)},
                              ends_paragraph, bounded=True)
            else:
                phonemes, stress = _ipa(whole.symbols[start:end], whole.stress[start:end])
                yield Segment(phonemes, mark, ends_sentence, {"stress": stress}, ends_paragraph)

    def _rewrite(self, text: str, symbols: Tuple[str, ...]) -> str:
        """*text* as dizione's rules rewrite it, when its token sequence *symbols* needs it, else ``""``.

        The tokens hold no whitespace, so they show neither a blank line nor
        which way a ``"`` faces. The rewritten text shows both, and one
        rewrite serves :func:`_paragraph_ends` and :func:`_quote_closes`.
        """
        if _PARAGRAPH_BREAK.search(text) or _DOUBLE_QUOTE in symbols:
            return self.engine.normalizer.rewrite(text)
        return ""

    def _ipa_sentences(self, text: str) -> List[str]:
        """The IPA of each sentence of *text*, as dizione reads it."""
        sentences: List[str] = []
        clauses: List[str] = []
        for clause in self._clauses(text):
            if clause.phonemes:
                clauses.append("".join(clause.phonemes))
            if clause.ends_sentence and clauses:
                sentences.append(" ".join(clauses))
                clauses = []
        if clauses:
            sentences.append(" ".join(clauses))
        return sentences

    def phonemize_segments(self, text: str, lang: str) -> Iterator[Segment]:
        """The IPA of each clause of *text*, read whole in one pass.

        dizione reports every mark, so a segment is a clause. A clause ends
        after a run of ``, . ? ! ; :`` that follows a sound, and it ends a
        sentence when the run holds ``.``, ``?`` or ``!``, as dizione's
        homograph rules read a sentence. A full stop that dizione reads as part
        of an abbreviation, as in ``Mrs.``, ends nothing. A closing quotation
        mark or bracket after the run stays with the clause. Each segment has
        a ``stress`` stream in step with its characters: the stress of the
        phone that a character writes, and 0 for a space. A sentence that a
        blank line follows ends a paragraph. With ``tokens=True`` the
        segments are dizione's tokens, as the class describes.
        """
        self.get_lang(lang)
        yield from self._clauses(text, self.tokens_mode)

    def word_break(self) -> Segment:
        """``<sp>`` with its id with ``tokens=True``, else a space."""
        if self.tokens_mode:
            return Segment((SP,), streams={"ids": (SYMBOL_TO_ID[SP],), "stress": (0,)})
        return Segment((" ",), streams={"stress": (0,)})

    def mark_symbols(self, marks: str) -> Optional[Segment]:
        """dizione's tokens for *marks* after a word with ``tokens=True``, else ``None``.

        They are the tokens after the word in dizione's own read of the word
        and the marks, so dizione reads ``...`` as ``…``, a closing ``»`` or
        ``”`` as ``"``, and a repeated mark once. dizione reads some runs
        alone as an emoticon, so the marks are not read alone. Without
        ``tokens=True`` the frontend writes the clause symbols, so dizione
        has no table.
        """
        if not self.tokens_mode:
            return None
        start = self._mark_word_length
        read = self.tokens(_MARK_WORD + marks)
        return Segment(read.symbols[start:-1], streams={"ids": read.ids[start:-1], "stress": read.stress[start:-1]})

    @cached_property
    def _mark_word_length(self) -> int:
        """The number of tokens before the marks in dizione's read of the word of the mark table and the marks."""
        return len(self.tokens(_MARK_WORD).symbols) - 1

    def phonemize_string(self, text: str, lang: str) -> str:
        self.get_lang(lang)
        return " ".join(self._ipa_sentences(text))

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """The IPA of each sentence of *text*, as a list of characters.

        dizione reads the whole text and ends a sentence at ``.``, ``?`` or
        ``!``, as its homograph rules do. A full stop that dizione reads as part
        of an abbreviation, as in ``Mrs.``, ends no sentence.
        """
        self.get_lang(lang)
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        for sentence in self._ipa_sentences(text):
            yield list(sentence)


def _paragraph_ends(rewritten: str, pieces: list, symbols: Tuple[str, ...]) -> Set[int]:
    """The places in *symbols* of the sentence marks that a paragraph break follows.

    dizione reads a blank line as a space, so it reports no paragraph. The
    *rewritten* text keeps each blank line, and each ``.``, ``?`` and ``!`` of
    it is a sentence mark of *pieces*, in order. A blank line ends a paragraph
    after the mark before it, when only closing marks stand between the two
    and a sound comes before the mark. A blank line that the rules read away,
    as in ``Jan.\n\n5``, ends nothing. When the marks of the rewritten text
    and of *pieces* differ in number, no blank line ends a paragraph. One pass
    over the text maps every blank line to its mark.
    """
    if not _PARAGRAPH_BREAK.search(rewritten):
        return set()
    places = _sentence_mark_places(pieces, symbols)
    if sum(rewritten.count(mark) for mark in SENTENCE_END) != len(places):
        return set()
    first_sound = next(index for index, symbol in enumerate(symbols) if symbol in PHONE_SET or symbol == UNK)
    ends = set()
    count = position = 0
    for match in _PARAGRAPH_BREAK.finditer(rewritten):
        count += sum(rewritten.count(mark, position, match.start()) for mark in SENTENCE_END)
        if count and places[count - 1] > first_sound and \
                _ENDS_IN_SENTENCE_MARK.search(rewritten, position, match.start()):
            ends.add(places[count - 1])
        position = match.start()
    return ends


def _sentence_mark_places(pieces: list, symbols: Tuple[str, ...]) -> List[int]:
    """The place in *symbols*, the token sequence of *pieces*, of each ``.``, ``?`` and ``!`` of *pieces*.

    ``tokenize`` writes a mark that repeats the symbol before it once, so
    such a mark shares the place of the mark before it.
    """
    found = (index for index, symbol in enumerate(symbols) if symbol in SENTENCE_END)
    places: List[int] = []
    previous = None
    for is_mark, value in pieces:
        if not is_mark:
            if value:
                previous = None
            continue
        if value in SENTENCE_END:
            places.append(places[-1] if value == previous else next(found))
        previous = value
    return places


def _quote_closes(rewritten: str, symbols: Tuple[str, ...]) -> Optional[List[bool]]:
    """For each ``"`` of *symbols*, whether it closes a quotation.

    The token sequence holds no spaces, so it cannot tell a closing quotation
    mark from an opening one. The text as dizione's rules rewrite it,
    *rewritten*, can: a ``"`` that follows a space, an opening bracket or the
    start of the text opens a quotation, and any other closes one. Each ``"``
    of the rewritten text is a ``"`` of *symbols*, in order. When the two
    differ in number, the result is ``None``.
    """
    if _DOUBLE_QUOTE not in symbols:
        return None
    places = [index for index, char in enumerate(rewritten) if char == _DOUBLE_QUOTE]
    if len(places) != symbols.count(_DOUBLE_QUOTE):
        return None
    return [index > 0 and not rewritten[index - 1].isspace() and rewritten[index - 1] not in "([{"
            for index in places]


def _clause_spans(symbols: Tuple[str, ...],
                  closes: Optional[List[bool]] = None) -> List[Tuple[int, int, Optional[str], bool]]:
    """``(start, end, mark, ends_sentence)`` of each clause of a token sequence.

    The spans cover the sequence without its ``<bos>`` and ``<eos>``. A clause
    ends after a run of clause marks that follows a sound. Its mark is the
    first mark of the run, as :data:`CLAUSE_PUNCTUATION` reads it, and it ends
    a sentence when the run holds ``.``, ``?`` or ``!``. A closing bracket, or
    a quotation mark that closes a quotation, is part of the run, so a clause
    mark after it stays with the clause too, and no clause starts with a
    closing mark. *closes* tells, for each ``"``, whether it closes a quotation;
    without it, and for ``'``, a quotation mark closes when an odd number of
    the same mark comes before it. Marks after the last sound stay with the
    last clause, and the last clause ends a sentence.
    """
    last = len(symbols) - 1
    spans: List[Tuple[int, int, Optional[str], bool]] = []
    seen = dict.fromkeys(_QUOTES, 0)

    def closing(quote: str) -> bool:
        if quote == _DOUBLE_QUOTE and closes is not None:
            return closes[seen[quote]]
        return seen[quote] % 2 == 1

    start, index, sound = 1, 1, False
    while index < last:
        symbol = symbols[index]
        if symbol in PHONE_SET or symbol == UNK:
            sound = True
        elif symbol in seen:
            seen[symbol] += 1
        elif sound and symbol in CLAUSE_PUNCTUATION:
            end = index
            while end < last and (symbols[end] in CLAUSE_PUNCTUATION or symbols[end] == _CLOSING_BRACKET
                                  or symbols[end] in seen and closing(symbols[end])):
                if symbols[end] in seen:
                    seen[symbols[end]] += 1
                end += 1
            ends_sentence = any(mark in SENTENCE_END for mark in symbols[index:end])
            spans.append((start, end, CLAUSE_PUNCTUATION[symbol], ends_sentence))
            start, index, sound = end, end, False
            continue
        index += 1
    if sound or not spans:
        spans.append((start, last, None, True))
    else:
        start, _, mark, _ = spans[-1]
        spans[-1] = (start, last, mark, True)
    return spans


def _token_clauses(whole: Phonemized, closes: Optional[List[bool]] = None) -> List[Phonemized]:
    """*whole* cut at :func:`_clause_spans`, each clause with its own ``<bos>`` and ``<eos>``."""
    unknown = iter(whole.unknown)
    clauses = []
    for start, end, _, _ in _clause_spans(whole.symbols, closes):
        symbols = (BOS, *whole.symbols[start:end], EOS)
        clauses.append(Phonemized(
            symbols, (whole.ids[0], *whole.ids[start:end], whole.ids[-1]),
            (0, *whole.stress[start:end], 0),
            tuple(next(unknown) for symbol in symbols if symbol == UNK)))
    return clauses


def _join_tokens(parts: List[Phonemized]) -> Phonemized:
    """*parts* as one sequence: each inner ``<eos>`` ``<bos>`` pair goes, with its ids and stress."""
    last = len(parts) - 1

    def inner(sequences: Iterator[tuple]) -> tuple:
        return tuple(value for index, sequence in enumerate(sequences)
                     for value in sequence[0 if index == 0 else 1:None if index == last else -1])

    return Phonemized(inner(part.symbols for part in parts), inner(part.ids for part in parts),
                      inner(part.stress for part in parts),
                      tuple(phone for part in parts for phone in part.unknown))


def _ipa(symbols: Tuple[str, ...], stress: Tuple[int, ...]) -> Tuple[Tuple[str, ...], Tuple[int, ...]]:
    """The IPA characters of a run of tokens, and the stress of each character.

    A stress mark stands before its vowel and takes the vowel's stress. Any
    symbol that is not a phone ends a word, and one space separates two words.
    """
    chars: List[str] = []
    levels: List[int] = []
    in_word = False
    for symbol, level in zip(symbols, stress):
        if symbol not in PHONE_SET:
            in_word = False
            continue
        if chars and not in_word:
            chars.append(" ")
            levels.append(0)
        written = STRESS_MARKS.get(level, "") + symbol
        chars.extend(written)
        levels.extend([level] * len(written))
        in_word = True
    return tuple(chars), tuple(levels)
