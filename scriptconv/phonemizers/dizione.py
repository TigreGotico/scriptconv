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
engine as written.
"""
import dataclasses
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Dict, Iterator, List, Optional, Union

from scriptconv.phonemizers._thirdparty import dizione
from scriptconv.phonemizers._thirdparty.dizione.engine import Phonemizer as DizioneEngine
from scriptconv.phonemizers._thirdparty.dizione.symbols import (
    PHONE_SET,
    STRESS_MARKS,
    UNK,
    Phonemized,
    tokenize,
)
from scriptconv.phonemizers.base import (
    BasePhonemizer,
    MissingLanguageError,
    PhonemizerIdentity,
    UnsupportedLanguageError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["DizionePhonemizer", "Phonemized", "DATA_DIR"]

DATA_DIR = Path(dizione.__file__).parent / "built"
"""dizione's built data, shipped in the wheel: the files of ``phonemizer/`` of
n4ze3m/tiny-voca at revision ``e5f9b11651a4db525fb207a56a91e4df2d1dd387``."""

# The marks after which dizione's token stream starts a new sentence.
_SENTENCE_MARKS = frozenset({".", "?", "!", "\u2026"})


class DizionePhonemizer(BasePhonemizer):
    """dizione: American English text to IPA, and to dizione's own tokens.

    :meth:`phonemize_string` writes IPA. A stress mark stands directly before
    its vowel, as dizione writes it. A word break is a space. The control
    symbols (``<bos>``, ``<eos>``, ``<pad>``, ``<sp>``) are not written, and
    neither is punctuation, because ``.`` is the IPA syllable break. A phone
    from an override that is not in dizione's inventory is written as given.
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
            marks.
    """

    owned_stages: ClassVar[frozenset[str]] = frozenset({"normalize"})

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

    @cached_property
    def fingerprint(self) -> str:
        """dizione's build fingerprint: its version, data, tables and code."""
        return dizione.identity(self.data_dir)["fingerprint"]

    def identity(self, lang: str) -> PhonemizerIdentity:
        """What phonemizes *lang*, with dizione's build fingerprint as ``revision``."""
        return dataclasses.replace(super().identity(lang), revision=self.fingerprint)

    def _ipa_sentences(self, text: str) -> List[str]:
        """The IPA of each sentence of *text*, as dizione reads it."""
        if not text.strip():
            return []
        pieces = self.engine.pieces(text)
        if not any(word for is_mark, words in pieces if not is_mark for word in words):
            return []
        phonemized = tokenize(pieces)
        unknown = iter(phonemized.unknown)
        sentences: List[str] = []
        words: List[str] = []
        word = ""
        for symbol, stress in zip(phonemized.symbols, phonemized.stress):
            if symbol in PHONE_SET:
                word += STRESS_MARKS.get(stress, "") + symbol
                continue
            if symbol == UNK:
                word += next(unknown)
                continue
            if word:
                words.append(word)
                word = ""
            if symbol in _SENTENCE_MARKS and words:
                sentences.append(" ".join(words))
                words = []
        if words:
            sentences.append(" ".join(words))
        return sentences

    def phonemize_string(self, text: str, lang: str) -> str:
        self.get_lang(lang)
        return " ".join(self._ipa_sentences(text))

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """The IPA of each sentence of *text*, as a list of characters.

        dizione reads the whole text and splits the sentences itself, so an
        abbreviation such as ``Mrs.`` ends no sentence.
        """
        self.get_lang(lang)
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        for sentence in self._ipa_sentences(text):
            yield list(sentence)
