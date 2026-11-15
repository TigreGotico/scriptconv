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
import dataclasses
import hashlib
import json
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Dict, Iterator, List, Optional, Tuple, Union

from scriptconv.phonemizers._thirdparty import dizione
from scriptconv.phonemizers._thirdparty.dizione.engine import Phonemizer as DizioneEngine
from scriptconv.phonemizers._thirdparty.dizione.homographs import SENTENCE_END
from scriptconv.phonemizers._thirdparty.dizione.symbols import (
    BOS,
    EOS,
    PHONE_SET,
    STRESS_MARKS,
    UNK,
    Phonemized,
    tokenize,
)
from scriptconv.phonemizers.base import (
    CLAUSE_PUNCTUATION,
    BasePhonemizer,
    MissingLanguageError,
    PhonemizerIdentity,
    Segment,
    UnsupportedLanguageError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["DizionePhonemizer", "Phonemized", "DATA_DIR"]

DATA_DIR = Path(dizione.__file__).parent / "built"
"""dizione's built data, shipped in the wheel: the files of ``phonemizer/`` of
n4ze3m/tiny-voca at revision ``e5f9b11651a4db525fb207a56a91e4df2d1dd387``."""


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
    """

    owned_stages: ClassVar[frozenset[str]] = frozenset({"normalize"})
    reads_whole_text: ClassVar[bool] = True

    def __init__(self, alphabet: Alphabet = Alphabet.IPA,
                 data_dir: Optional[Union[str, Path]] = None,
                 overrides: Optional[Union[Dict[str, str], str, Path]] = None):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        super().__init__(alphabet)
        self.data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self.engine = DizioneEngine(self.data_dir, overrides=overrides)

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
        return tokenize(self.engine.pieces(text))

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
        sentences: List[Phonemized] = []
        clauses: List[Phonemized] = []
        for clause, (_, _, _, ends_sentence) in zip(_token_clauses(whole),
                                                     _clause_spans(whole.symbols)):
            clauses.append(clause)
            if ends_sentence:
                sentences.append(_join_tokens(clauses))
                clauses = []
        return sentences

    @cached_property
    def fingerprint(self) -> str:
        """dizione's build fingerprint: its version, data, tables and code."""
        return dizione.identity(self.data_dir)["fingerprint"]

    def identity(self, lang: str) -> PhonemizerIdentity:
        """What phonemizes *lang*.

        ``revision`` is dizione's build fingerprint. When overrides take effect,
        from ``overrides=`` or from the file that ``DIZIONE_OVERRIDES`` names,
        ``revision`` is the sha256 of the fingerprint and of the overrides, so
        phonemes read with two sets of overrides never mix.
        """
        engine = self.engine
        names = {" ".join(key): engine.names[key] for key in engine.user_names}
        revision = self.fingerprint
        if engine.overrides or names:
            overrides = json.dumps({"words": engine.overrides, "names": names},
                                   sort_keys=True, ensure_ascii=False)
            digest = hashlib.sha256(overrides.encode()).hexdigest()
            revision = hashlib.sha256(f"{revision}\n{digest}".encode()).hexdigest()
        return dataclasses.replace(super().identity(lang), revision=revision)

    def _clauses(self, text: str) -> Iterator[Segment]:
        """The IPA of each clause of *text*, as :func:`_clause_spans` cuts dizione's tokens."""
        if not text.strip():
            return
        pieces = self.engine.pieces(text)
        if not any(word for is_mark, words in pieces if not is_mark for word in words):
            return
        whole = tokenize(pieces)
        for start, end, mark, ends_sentence in _clause_spans(whole.symbols):
            phonemes, stress = _ipa(whole.symbols[start:end], whole.stress[start:end])
            yield Segment(phonemes, mark, ends_sentence, {"stress": stress})

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
        of an abbreviation, as in ``Mrs.``, ends nothing. Each segment has a
        ``stress`` stream in step with its characters: the stress of the phone
        that a character writes, and 0 for a space.
        """
        self.get_lang(lang)
        yield from self._clauses(text)

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


def _clause_spans(symbols: Tuple[str, ...]) -> List[Tuple[int, int, Optional[str], bool]]:
    """``(start, end, mark, ends_sentence)`` of each clause of a token sequence.

    The spans cover the sequence without its ``<bos>`` and ``<eos>``. A clause
    ends after a run of clause marks that follows a sound. Its mark is the
    first mark of the run, as :data:`CLAUSE_PUNCTUATION` reads it, and it ends
    a sentence when the run holds ``.``, ``?`` or ``!``. Marks after the last
    sound stay with the last clause, and the last clause ends a sentence.
    """
    last = len(symbols) - 1
    spans: List[Tuple[int, int, Optional[str], bool]] = []
    start, index, sound = 1, 1, False
    while index < last:
        symbol = symbols[index]
        if symbol in PHONE_SET or symbol == UNK:
            sound = True
        elif sound and symbol in CLAUSE_PUNCTUATION:
            end = index
            while end < last and symbols[end] in CLAUSE_PUNCTUATION:
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


def _token_clauses(whole: Phonemized) -> List[Phonemized]:
    """*whole* cut at :func:`_clause_spans`, each clause with its own ``<bos>`` and ``<eos>``."""
    unknown = iter(whole.unknown)
    clauses = []
    for start, end, _, _ in _clause_spans(whole.symbols):
        symbols = (BOS, *whole.symbols[start:end], EOS)
        clauses.append(Phonemized(
            symbols, (whole.ids[0], *whole.ids[start:end], whole.ids[-1]),
            (0, *whole.stress[start:end], 0),
            tuple(next(unknown) for symbol in symbols if symbol == UNK)))
    return clauses


def _join_tokens(parts: List[Phonemized]) -> Phonemized:
    """*parts* as one sequence: each inner ``<eos>`` ``<bos>`` pair goes, with its ids and stress."""
    def inner(field: str) -> tuple:
        return tuple(value for index, part in enumerate(parts)
                     for value in getattr(part, field)[0 if index == 0 else 1:
                                                       None if index == len(parts) - 1 else -1])

    return Phonemized(inner("symbols"), inner("ids"), inner("stress"),
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
