"""Phonemizer contract and base implementations.

The phonemizers are wrappers around external engines behind optional extras;
the zero-dependency core holds no grapheme-to-phoneme rules. The
``phonemizers`` extra provides sentence chunking (``quebra_frases``) and
language matching (``linguatag``).

Normalization is injected, not built in: ``normalizer=``, a
``(text, lang) -> str`` callable, runs inside ``phonemize_lazy``. Without it
the raw text is phonemized as written, so text with digits can read
differently here than through a TTS stack that injects its own normalizer.
"""
import abc
import dataclasses
import functools
import inspect
import re
import string
import unicodedata
from importlib import metadata
from types import MappingProxyType
from typing import Callable, ClassVar, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Tuple, Literal, Union

from scriptconv.phonemizers.enums import Alphabet
from scriptconv.version import VERSION_STR

# list of (substring, terminator, end_of_sentence) tuples.
TextChunks = List[Tuple[str, str, bool]]
# list of (phonemes, terminator, end_of_sentence) tuples.
RawPhonemizedChunks = List[Tuple[str, str, bool]]

PhonemizedChunks = list[list[str]]

# Clause punctuation kept by ``keep_punctuation``, mapped to the symbol a voice
# is trained on: the six clause types Piper appends after each espeak-ng clause
# (piper-phonemize ``src/phonemize.cpp``). A comma, colon and semicolon take a
# space after them. The Arabic-script marks map onto the same symbols.
CLAUSE_PUNCTUATION = {".": ".", "?": "?", "!": "!", ",": ",", ":": ":", ";": ";",
                      "\u060c": ",", "\u061b": ";", "\u061f": "?"}
_PAUSE_PUNCTUATION = {",", ":", ";"}
_CLAUSE_TOKENS = frozenset(CLAUSE_PUNCTUATION.values())
# A mark read as "!" or "?" between two letters is no clause break, but it separates two words.
_SEPARATING_MARKS = frozenset(mark for mark, symbol in CLAUSE_PUNCTUATION.items()
                              if symbol in ("!", "?"))
# The Unicode hyphens. Between two letters each one is read as "-".
_HYPHENS = frozenset("-\u2010\u2011\ufe63\uff0d")
# The dashes. Between two words, as in "Lisboa–Porto", a dash separates them.
_DASHES = frozenset("\u2012\u2013\u2014\u2015\u2e3a\u2e3b\ufe31\ufe32\ufe58")
# A clause ends at punctuation followed by whitespace, as in espeak-ng, so the
# "," in "10,4" or the ":" in "16:30" never splits. A lone "." is left to the
# sentence tokenizer, which knows abbreviations. An ellipsis or "|" ends a
# clause with no symbol. A match starts only where a run of marks starts and
# must reach whitespace, so the split takes linear time. Group 1 is the break:
# the first clause-ending mark of the run through the end of the run.
_CLAUSE_BREAK = re.compile(
    r"(?<![^\w\s])(?=[^\w\s]*+\s)[^\w\s]*?((?:\.\.|\u2026|[,:;!?|\u060c\u061b\u061f])[^\w\s]*+)")
# Starts only where a run of marks starts, so a long run is read once.
_TRAILING_PUNCTUATION = re.compile(r"(?<![^\w\s])[^\w\s]++\s*+$")
# One or more blank lines: a paragraph break.
_PARAGRAPH_BREAK = re.compile(r"(\n(?:[^\S\n]*\n)+)")
_LANG_FLAGS = re.compile(r"\([^)]+\)")
_WHITESPACE = re.compile(r"\s")
# The text before the first letter or digit: whitespace and marks.
_WORDLESS_START = re.compile(r"[\W_]*")
# Primary language tags whose question mark is ";".
_GREEK_TAGS = frozenset({"el", "ell", "gre"})
# The stress mark that the diacritize stage writes after a stressed vowel.
STRESS_MARK = "\u0301"
# The methods through which text reaches a backend.
_TEXT_METHODS = ("phonemize_string", "phonemize_to_list", "phonemize", "phonemize_lazy",
                 "phonemize_segments")


def join_sentences(sentences: Iterable[List[str]], keep_punctuation: bool = True) -> List[str]:
    """Per-sentence phonemes joined into one flat training stream, as Piper flattens them.

    A sentence that ends in a clause symbol (with *keep_punctuation*) or in a
    space joins the next one directly; any other sentence takes one space
    before the next. No sentence starts with a space. This function does not
    see the text, so it adds the space even where the text writes none, as
    after Chinese ``。``; :meth:`BasePhonemizer.phonemize_to_list` reads the
    text and does not. A phoneme written with a clause symbol's character,
    such as ``":"`` for vowel length, counts as that symbol here.
    """
    return _join((sentence, keep_punctuation and bool(sentence)
                  and sentence[-1] in _CLAUSE_TOKENS, True) for sentence in sentences)


def _join(sentences: Iterable[Tuple[List[str], bool, bool]]) -> List[str]:
    """``(phonemes, ends_in_token, spaced)`` sentences joined by the rule of :func:`join_sentences`.

    *spaced* tells whether the text writes whitespace before the sentence; without it no space is added.
    """
    phonemes: List[str] = []
    joins = True
    for sentence, ends_in_token, spaced in sentences:
        if not sentence:
            continue
        if spaced and not joins:
            phonemes.append(" ")
        phonemes.extend(sentence)
        joins = ends_in_token or sentence[-1] == " "
    return phonemes


def _clause_breaks_as_spaces(phonemes: str) -> str:
    """*phonemes* with each line break between clauses, as espeak-ng prints them, read as one space."""
    if "\n" not in phonemes:
        return phonemes
    return " ".join(line.strip() for line in phonemes.split("\n") if line.strip())


def _between_letters(text: str, index: int, is_letter: Callable[[str], bool] = str.isalpha) -> bool:
    """Whether the character at *index* of *text* stands between two letters.

    The letter before it may carry combining marks, such as a stress mark
    (U+0301). *is_letter* tells what counts as a letter: ``str.isalnum``
    counts a digit too.
    """
    if not 0 < index < len(text) - 1 or not is_letter(text[index + 1]):
        return False
    letter = index - 1
    while letter > 0 and unicodedata.category(text[letter]).startswith("M"):
        letter -= 1
    return is_letter(text[letter])


def _clause_mark(punctuation: str) -> Optional[str]:
    """The symbol a run of clause-final punctuation is kept as, if any."""
    if ".." in punctuation or "\u2026" in punctuation:
        return None
    for char in punctuation:
        if char in CLAUSE_PUNCTUATION:
            return CLAUSE_PUNCTUATION[char]
    return None


def split_clauses(sentence: str) -> List[Tuple[str, Optional[str]]]:
    """Split one sentence into ``(clause, mark)`` pairs.

    ``mark`` is the symbol from :data:`CLAUSE_PUNCTUATION` that ends the
    clause, or ``None`` when the clause ends without one (no punctuation, an
    ellipsis, ``|``). The clause text still carries its own punctuation.
    """
    clauses: List[Tuple[str, Optional[str]]] = []
    start = 0
    for match in _CLAUSE_BREAK.finditer(sentence):
        clauses.append((sentence[start:match.start(1)], _clause_mark(match.group(1))))
        start = match.end()
    tail = sentence[start:]
    trailing = _TRAILING_PUNCTUATION.search(tail)
    clauses.append((tail, _clause_mark(trailing.group()) if trailing else None))
    return clauses


class FrontendError(ValueError):
    """Text could not become phonemes."""


class UnsupportedLanguageError(FrontendError):
    """A backend has no support for the language it was given."""


class StageError(FrontendError):
    """A text stage failed in strict mode."""


class UnreadTextError(FrontendError):
    """Text reached no phoneme in strict mode.

    ``unread`` holds the pieces of text that gave no phonemes.
    """

    def __init__(self, message: str, unread: Tuple[str, ...] = ()):
        super().__init__(message)
        self.unread = tuple(unread)


class ModelUnavailableError(FrontendError):
    """A model is not cached and cannot be fetched offline."""


@dataclasses.dataclass(frozen=True)
class PhonemizerIdentity:
    """What produced a phoneme sequence, for a voice to record and compare."""

    backend: str
    """The registry name, ``"tugaphone"``."""
    distribution: str
    """The distribution that holds the engine, ``"tugaphone"``."""
    version: str
    """The engine's version. For espeak-ng, the version of the binary."""
    lang: str
    """The resolved lect, ``"pt-PT-x-porto"``."""
    revision: Optional[str] = None
    """A hash of the spec, code and data that give the phonemes, when the
    backend has one: the orthography2ipa spec revision, dizione's build
    fingerprint, or the hash of the code and data on the path of an in-tree
    backend. For any other engine, the hash holds the engine version in place
    of the engine's files.

    Its meaning depends on :attr:`frontend`. With ``frontend`` ``None``, a
    backend called directly, it is the backend's own revision. With
    ``frontend`` set, it is the frontend revision with the ``sc2:`` prefix.
    That revision covers the backend revision plus the frontend stage modules
    and output settings, and text2spoken's revision when the normaliser is
    :func:`~scriptconv.frontend.spoken_normalizer`. It is ``None`` when the
    backend has no revision or scriptconv cannot vouch for a stage.

    Two identities compare by ``revision`` only when both have ``frontend``
    ``None`` or both have it set. A consumer that recorded a backend identity
    compares it with ``backend.identity(lang)``, not with
    :meth:`~scriptconv.frontend.TextFrontend.identity`."""
    frontend: Optional[int] = None
    """The version of the stage order of :class:`~scriptconv.frontend.TextFrontend`.
    ``None`` for a backend called directly; it tells what :attr:`revision`
    holds, the backend's own revision when ``None`` and the frontend revision
    when set."""

    def differs_from(self, other: "PhonemizerIdentity") -> Tuple[str, ...]:
        """Names of the fields that differ from *other*, ``revision`` first.

        ``revision`` outranks ``version``: when both sides hold the same
        revision, the spec that gives the phonemes did not change, so a
        ``version`` difference is not reported.
        """
        same_spec = self.revision is not None and self.revision == other.revision
        names = [field.name for field in dataclasses.fields(self)
                 if getattr(self, field.name) != getattr(other, field.name)
                 and not (same_spec and field.name == "version")]
        return tuple(sorted(names, key=lambda name: name != "revision"))


@dataclasses.dataclass(frozen=True)
class Segment:
    """One sentence or clause of a text that a backend reads whole.

    :meth:`BasePhonemizer.phonemize_segments` yields these in reading order.
    """

    phonemes: Tuple[str, ...]
    """The output symbols, as :meth:`BasePhonemizer.phonemize_lazy` yields them."""
    mark: Optional[str] = None
    """The clause symbol that ends the segment, a value of
    :data:`CLAUSE_PUNCTUATION`, or ``None``. The frontend appends it when it
    keeps punctuation, except to a bounded segment, which holds its marks
    among its own symbols."""
    ends_sentence: bool = True
    """Whether the segment ends a sentence."""
    streams: Mapping[str, Tuple] = dataclasses.field(default_factory=dict)
    """Side streams of the backend, such as stress, each in step with :attr:`phonemes`."""
    ends_paragraph: bool = False
    """Whether a blank line follows the segment. Only a segment that ends a sentence ends a paragraph."""
    bounded: bool = False
    """Whether :attr:`phonemes` starts with the backend's start symbol and ends
    with its end symbol, as ``<bos>`` and ``<eos>``. Where the frontend joins
    two bounded segments, the inner end and start symbols go with their stream
    values, and a segment with no mark takes :meth:`~BasePhonemizer.word_break`."""
    text: Optional[str] = None
    """The text the backend read for the segment, after the frontend's text
    stages and without an appended clause mark; ``None`` when the backend cannot say."""


class MissingLanguageError(ValueError):
    """No language reached :meth:`BasePhonemizer.match_lang`: the target was ``None``, ``""`` or ``"und"``.

    This is a defect of the caller, not a language the backend lacks.
    """


def _primary_subtag(lang: str) -> str:
    """The lowercase primary subtag of *lang*, for exact matching: ``ber`` never matches ``be``."""
    return lang.lower().replace("_", "-").split("-")[0]


def _check_alphabet(phonemizer, alphabet: Alphabet,
                    supported: List[Alphabet]) -> None:
    """Raise :class:`ValueError` naming *alphabet* and the *supported* ones when *phonemizer* cannot emit it."""
    if alphabet not in supported:
        raise ValueError(
            f"{type(phonemizer).__name__} cannot emit "
            f"{Alphabet(alphabet).value!r}; supported alphabets are "
            f"{[Alphabet(a).value for a in supported]}")


# The packages that hold the wrappers under a copyleft or a non-commercial
# licence. Code vendored there reports the package, not scriptconv.
_SISTER_DISTRIBUTIONS = {"scriptconv_copyleft": "scriptconv-copyleft",
                         "scriptconv_nonfree": "scriptconv-nonfree"}


def _without_unread_stress_mark(method: Callable) -> Callable:
    """*method* with the stress mark removed from its text where the backend does not read it."""
    parameter = inspect.signature(method).parameters.get("lang")
    default_lang = None if parameter is None or parameter.default is parameter.empty else parameter.default

    @functools.wraps(method)
    def read(self, text, *args, **kwargs):
        lang = args[0] if args else kwargs.get("lang", default_lang)
        if text and lang and STRESS_MARK in text and not self.reads_stress_mark(lang):
            from scriptconv.diacritics import replace_stress_mark
            text = replace_stress_mark(text, lang)
        return method(self, text, *args, **kwargs)

    return read


@functools.lru_cache(maxsize=None)
def _declared(langs: frozenset, lang: str) -> bool:
    """True when linguatag matches *lang* to one of *langs*, as :meth:`BasePhonemizer.match_lang` does."""
    return bool(langs) and BasePhonemizer._match_lang(lang, sorted(langs))[1] <= 10


class BasePhonemizer(metaclass=abc.ABCMeta):
    keep_punctuation: bool = False
    """Keep clause punctuation (``, . ? ! : ;``) in the phoneme output.

    When on, :meth:`phonemize_to_list` and :meth:`phonemize_lazy` phonemize
    clause by clause and append each clause's symbol the way Piper does. A
    backend that overrides either method ignores the flag, so training and
    synthesis never disagree.
    """

    strict: bool = False
    """Raise :class:`UnreadTextError` when a pinyin backend meets a syllable
    that is not pinyin, or a digit it cannot read; off, it logs a warning and
    drops it. Only the Chinese pinyin backends and G2PW read the field.
    """

    owned_stages: ClassVar[frozenset[str]] = frozenset()
    """Stages this backend always runs itself: ``"normalize"``, ``"diacritize"`` or both.

    A stage that runs only with an optional dependency is not owned.
    """

    reads_whole_text: ClassVar[bool] = False
    """The backend reads the whole text and reports its own sentence and clause
    marks through :meth:`phonemize_segments`.

    :class:`~scriptconv.frontend.TextFrontend` then does not cut the text into
    sentences for it. Only a backend that owns ``normalize`` sets it.
    """

    engine_distribution: ClassVar[Optional[str]] = None
    """The distribution that holds the engine; ``None`` for code inside the
    package that holds the wrapper (scriptconv, scriptconv-copyleft or scriptconv-nonfree)."""

    stress_mark_langs: ClassVar[frozenset[str]] = frozenset()
    """Languages in which this backend reads the stress mark (U+0301 after a vowel) as stress.

    ``scripts/probe_stress_marks.py`` decides the declaration. In a language of
    :data:`scriptconv.diacritics.STRESS_LANGS` that is not declared, the mark
    is removed from the text before the backend reads it.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in _TEXT_METHODS:
            if name in cls.__dict__:
                method = cls.__dict__[name]
                if not inspect.isfunction(method):
                    raise TypeError(f"{cls.__qualname__}.{name} must be an instance method that takes "
                                    f"(self, text, lang), so that the stress mark is removed from its text "
                                    f"in a language the backend does not read it in")
                setattr(cls, name, _without_unread_stress_mark(method))

    def __init__(self, alphabet: Alphabet = Alphabet.UNICODE,
                 normalizer: Optional[Callable[[str, str], str]] = None):
        super().__init__()
        self.alphabet = alphabet
        self.normalizer = normalizer

    @abc.abstractmethod
    def phonemize_string(self, text: str, lang: str) -> str:
        raise NotImplementedError

    def reads_stress_mark(self, lang: str) -> bool:
        """True when this backend reads the stress mark in *lang*, as :attr:`stress_mark_langs` declares."""
        return _declared(self.stress_mark_langs, lang)

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        """Phonemes of *text* as one flat list, without the ``normalizer`` hook.

        The list is the sentences of :meth:`phonemize_lazy` joined by the rule
        of :func:`join_sentences`, with a space between two sentences only
        where the text writes whitespace. A line break a backend prints between
        clauses becomes one space. A backend that overrides
        :meth:`phonemize_lazy` gives the whole text read by :meth:`phonemize_string`.
        """
        if self._keeps_punctuation():
            return _join(self._punctuated_sentences(text, lang))
        if type(self).phonemize_lazy is not BasePhonemizer.phonemize_lazy:
            return list(_clause_breaks_as_spaces(self.phonemize_string(text, lang)))
        return _join(self._bare_sentences(text, lang))

    def phonemize(self, text: str, lang: str) -> PhonemizedChunks:
        """One phoneme list per sentence; empty text gives none."""
        return list(self.phonemize_lazy(text, lang))

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """One phoneme list per sentence, each read only when the caller pulls it.

        The ``normalizer`` hook and the sentence split run over the whole text first.
        """
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        if self._keeps_punctuation():
            yield from (phonemes for phonemes, _, _ in self._punctuated_sentences(text, lang))
        else:
            yield from (phonemes for phonemes, _, _ in self._bare_sentences(text, lang))

    def phonemize_segments(self, text: str, lang: str) -> Iterator[Segment]:
        """The segments of *text* in reading order.

        A backend that sets :attr:`reads_whole_text` overrides this method and
        cuts its output at its own marks. For any other backend a segment is a
        sentence of :meth:`phonemize_lazy`, and :attr:`Segment.text` is the
        stripped *text* only when there is one segment.

        Raises:
            NotImplementedError: If the backend reads whole text and does not
                override this method.
        """
        if self.reads_whole_text:
            raise NotImplementedError(f"{type(self).__name__} reads whole text and gives no segments")
        segments = [Segment(tuple(phonemes)) for phonemes in self.phonemize_lazy(text, lang)]
        if len(segments) == 1:
            segments[0] = dataclasses.replace(segments[0], text=text.strip())
        yield from segments

    def word_break(self) -> Segment:
        """The symbol that separates two words in this backend's output, with its stream values.

        The frontend writes it between two pieces with no clause symbol and
        around an inline block. A stream that the segment lacks takes 0.
        """
        return Segment((" ",))

    def mark_symbols(self, marks: str) -> Optional[Segment]:
        """The symbols that this backend writes for *marks* after a word, with their stream values, or ``None``.

        *marks* is a run of closing marks, such as ``...`` or ``?!``, or a
        quote that opens the next word, with any whitespace before them. The
        frontend reads it for the marks after an inline block.
        """
        return None

    def _bare_sentences(self, text: str, lang: str) -> Iterator[Tuple[List[str], bool, bool]]:
        """Per-sentence phonemes, each chunk of :meth:`chunk_text` read alone without punctuation.

        In Greek a ``;`` is the question mark, so it ends the sentence. The
        tags ``el``, ``ell`` and ``gre`` name Greek. A backend that owns
        ``normalize`` reads each chunk stripped but with its punctuation. Each
        sentence comes with the flags of :meth:`_punctuated_sentences`, and
        never ends in a token.
        """
        question_semicolon = _primary_subtag(lang) in _GREEK_TAGS
        sentence: List[List[str]] = []
        # where the sentence's first word with phonemes starts, and where the last sentence with phonemes ends
        word: Optional[int] = None
        end = cursor = 0
        for chunk, punct, eos in self.chunk_text(text):
            found = cursor
            if chunk:
                found = text.find(chunk, cursor)
                cursor = found + len(chunk)
            read = (chunk.strip() if "normalize" in self.owned_stages
                    else self.remove_punctuation(chunk))
            # drop the (lang) flags that espeak-ng writes around words of another language
            phoneme_str = _LANG_FLAGS.sub("", _clause_breaks_as_spaces(self.phonemize_string(read, lang)))
            if phoneme_str and word is None:
                word = found + _WORDLESS_START.match(chunk).end()
            sentence.append(list(phoneme_str))
            if eos or (question_semicolon and punct == ";"):
                phonemes = join_sentences(sentence, keep_punctuation=False)
                # the gap is searched only for a sentence with phonemes, so each character is read once
                yield phonemes, False, bool(phonemes and _WHITESPACE.search(text, end, word))
                if phonemes:
                    end = cursor
                sentence = []
                word = None

    def _keeps_punctuation(self) -> bool:
        cls = type(self)
        return (self.keep_punctuation
                and cls.phonemize_to_list is BasePhonemizer.phonemize_to_list
                and cls.phonemize_lazy is BasePhonemizer.phonemize_lazy)

    def _punctuated_sentences(self, text: str, lang: str) -> Iterator[Tuple[List[str], bool, bool]]:
        """Per-sentence phonemes with each clause's symbol appended.

        Each clause is read alone without punctuation (a backend that owns
        ``normalize`` reads it stripped but with its punctuation), then its
        symbol follows: bare for ``. ? !``, with a space for ``, : ;``. A space
        separates two clauses of one sentence. Each sentence comes with whether
        it ends in an appended symbol, and whether the text writes whitespace
        between it and the last sentence that gave phonemes.
        """
        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None
        end = cursor = 0
        for sentence in sentence_tokenize(text):
            start = text.find(sentence, cursor)
            cursor = start + len(sentence)
            phonemes: List[str] = []
            ends_in_token = False
            for clause, mark in split_clauses(sentence):
                clause = (clause.strip() if "normalize" in self.owned_stages
                          else self.remove_punctuation(clause))
                if not clause:
                    continue
                phoneme_str = _LANG_FLAGS.sub("", self.phonemize_string(clause, lang))
                clause_phonemes = list(_clause_breaks_as_spaces(phoneme_str))
                if not clause_phonemes:
                    continue
                # the next clause starts a new word, as the text writes it
                if phonemes and phonemes[-1] != " ":
                    phonemes.append(" ")
                phonemes.extend(clause_phonemes)
                ends_in_token = bool(mark)
                if mark:
                    phonemes.append(mark)
                    if mark in _PAUSE_PUNCTUATION:
                        phonemes.append(" ")
            if phonemes:
                word = start + _WORDLESS_START.match(sentence).end()
                yield phonemes, ends_in_token, bool(_WHITESPACE.search(text, end, word))
                end = cursor

    @staticmethod
    def _match_lang(target_lang: str, valid_langs: Union[str, List[str]]):
        """Closest supported language and its distance (linguatag closest_lang)."""
        from linguatag import closest_lang, lang_distance
        if isinstance(valid_langs, str):
            valid_langs = [valid_langs]
        if target_lang in valid_langs:
            return target_lang, 0
        best_lang = closest_lang(target_lang, valid_langs, max_distance=10)
        if best_lang is None:
            return "und", 10000
        return best_lang, lang_distance(target_lang, best_lang)

    @staticmethod
    def match_lang(target_lang: str, valid_langs: List[str]) -> str:
        """The supported language in *valid_langs* closest to *target_lang*.

        Raises:
            MissingLanguageError: If no language reached the matcher at all
                (``None``/``""``/``"und"``).
            UnsupportedLanguageError: If the language code is unsupported.
        """
        if target_lang in (None, "", "und"):
            raise MissingLanguageError(
                f"no language provided to phonemize: {target_lang!r}")
        lang, score = BasePhonemizer._match_lang(target_lang, valid_langs)
        if score > 10:
            raise UnsupportedLanguageError(f"unsupported language code: {target_lang}")
        return lang

    def _engine_release(self) -> Tuple[str, str]:
        """The distribution that produced the phonemes, and its version."""
        if self.engine_distribution is not None:
            return self.engine_distribution, metadata.version(self.engine_distribution)
        sister = _SISTER_DISTRIBUTIONS.get(type(self).__module__.partition(".")[0])
        if sister is not None:
            return sister, metadata.version(sister)
        return "scriptconv", VERSION_STR

    def _revision_arguments(self) -> Dict[str, object]:
        """The constructor arguments, as JSON values, that change the output. They join the revision."""
        return {}

    def _identity_settings(self) -> Dict[str, object]:
        """The settings on the instance, as JSON values, that change
        :meth:`identity` besides the constructor arguments. They join the key
        of the identity cache."""
        return {}

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        """The distributions whose own revision, or version, the identity of
        this backend holds for *lang*.
        :func:`~scriptconv.phonemizers._revision.code_revision` leaves their
        versions out of the hash. For an engine outside scriptconv it is the
        engine's distribution, whose version :meth:`identity` puts in the settings."""
        if self.engine_distribution is None:
            return frozenset()
        return frozenset({self._engine_release()[0]})

    def identity(self, lang: str) -> PhonemizerIdentity:
        """What phonemizes *lang* here: the engine, its version, the lect and the revision.

        ``revision`` is the hash of the code and data on the path of this
        backend, as :func:`~scriptconv.phonemizers._revision.code_revision`
        gives it, with :meth:`_identity_settings` in the settings. For an
        engine outside scriptconv, the settings also hold the engine's
        distribution and version. So a change of the scriptconv code on the
        path, as ``base.py`` or ``diacritics.py``, changes the revision, and
        so does a release of the engine or of a distribution under it, as the
        sentence splitter.

        Raises:
            ImportError: If the engine is not installed.
            UnsupportedLanguageError: If the backend does not support *lang*.
        """
        from scriptconv.phonemizers._revision import code_revision
        from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY
        names = {cls_name: member.value
                 for member, (_, cls_name, _) in PHONEMIZER_REGISTRY.items()}
        backend = next((names[cls.__name__] for cls in type(self).__mro__
                        if cls.__name__ in names), type(self).__name__)
        distribution, version = self._engine_release()
        # Grapheme, Unicode and Phonetisaurus backends take any language.
        resolved = self.get_lang(lang) if hasattr(self, "get_lang") else lang
        settings = self._identity_settings()
        if self.engine_distribution is not None:
            settings = {**settings, distribution: version}
        return PhonemizerIdentity(backend, distribution, version, resolved,
                                  code_revision(self, resolved, settings))

    @staticmethod
    def remove_punctuation(text):
        """*text* without Unicode punctuation (category P), stripped.

        An apostrophe or hyphen between two letters stays ("don't"), and any
        Unicode hyphen there becomes ``-``. Any mark between two digits stays
        ("16:30", "10,4"). A hyphen between a letter and a digit ("COVID-19")
        or a dash between two words ("Lisboa–Porto") becomes a space, and so
        does a run of marks read as ``!`` or ``?`` between a letter or digit
        and a letter ("Sim!Não").
        """
        out = []
        chars = list(text)
        separates = False
        for i, c in enumerate(chars):
            if c in ("'", "’") and _between_letters(text, i):
                out.append(c)
                continue
            if c in _HYPHENS and _between_letters(text, i):
                out.append("-")
                continue
            if c in _SEPARATING_MARKS:
                if i == 0 or chars[i - 1] not in _SEPARATING_MARKS:
                    end = i
                    while end < len(chars) and chars[end] in _SEPARATING_MARKS:
                        end += 1
                    letter = i - 1
                    while letter > 0 and unicodedata.category(chars[letter]).startswith("M"):
                        letter -= 1
                    separates = (i > 0 and chars[letter].isalnum()
                                 and end < len(chars) and chars[end].isalpha())
                    if separates:
                        out.append(" ")
                if separates:
                    continue
            if 0 < i < len(chars) - 1 \
                    and chars[i - 1].isdigit() and chars[i + 1].isdigit():
                out.append(c)
                continue
            if (c in _HYPHENS or c in _DASHES) and _between_letters(text, i, str.isalnum):
                out.append(" ")
                continue
            if unicodedata.category(c).startswith("P"):
                continue
            out.append(c)
        return "".join(out).strip()

    @staticmethod
    def chunk_text(text: str, delimiters: Optional[List[str]] = None) -> TextChunks:
        """Split *text* into sentences, and each sentence at *delimiters*.

        *delimiters* defaults to ``[":", ";", "...", "|"]``. ``:`` and ``;`` cut
        only before whitespace or the end; any other delimiter cuts unless it
        stands between two digits. Each chunk is ``(text, terminator,
        end_of_sentence)``, the text stripped, the terminator the delimiter
        after it or the sentence's final ASCII punctuation (``"."`` when there
        is none). Empty *text* gives one empty chunk.
        """
        if not text:
            return [('', '', True)]

        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None

        # ":" and ";" cut only before whitespace, so "16:30" and the Bengali "নি:সন্দেহে" stay whole
        alternatives = []
        for delimiter in delimiters or [":", ";", "...", "|"]:
            escaped = re.escape(delimiter)
            alternatives.append(f"{escaped}(?=\\s|$)" if delimiter in (":", ";")
                                else f"(?:(?<!\\d){escaped}|{escaped}(?!\\d))")
        splitter = re.compile(f"({'|'.join(alternatives)})")
        results: TextChunks = []
        for sentence in sentence_tokenize(text):
            default_punc = sentence[-1] if sentence and sentence[-1] in string.punctuation else "."
            parts = splitter.split(sentence)
            for i in range(0, len(parts), 2):
                delimiter = parts[i + 1] if i + 1 < len(parts) else default_punc
                results.append((parts[i].strip(), delimiter.strip(), i + 2 >= len(parts)))
        return results


class GraphemePhonemizer(BasePhonemizer):
    """The text itself as the phonemes, after the character rules below.

    A hyphen between two letters stays, as in ``motse-moholo``; any other
    hyphen becomes a space. ``stress_notation`` writes the stress mark of a
    :data:`scriptconv.diacritics.STRESS_LANGS` language: ``"acute"`` keeps
    U+0301, ``"plus"`` writes ``+`` before the stressed vowel (``прив+ет``),
    and ``"none"`` removes it. In any other language an acute is spelling and stays.
    """
    STRESS_NOTATIONS = ("acute", "plus", "none")
    whitespace_re = re.compile(r"\s+")

    lowercase: bool = True
    """Lowercase the text before the character rules."""
    in_word_chars: str = "-"
    """Characters that stay as written between two letters. Elsewhere
    :attr:`replace_chars` applies to them."""
    replace_chars: Mapping[str, str] = MappingProxyType({";": ",", "-": " ", ":": ","})
    """Each character and the text that replaces it."""
    drop_chars: str = '<>()[]"'
    """Characters removed after :attr:`replace_chars`."""
    _RULES = ("lowercase", "in_word_chars", "replace_chars", "drop_chars", "whitespace_re")

    def __init__(self, alphabet: Alphabet = Alphabet.UNICODE,
                 normalizer: Optional[Callable[[str, str], str]] = None,
                 stress_notation: str = "acute", *,
                 lowercase: Optional[bool] = None,
                 in_word_chars: Optional[str] = None,
                 replace_chars: Optional[Mapping[str, str]] = None,
                 drop_chars: Optional[str] = None):
        """Each character rule that is not None replaces the class default for this instance, as in
        ``GraphemePhonemizer(in_word_chars="")``, which turns every hyphen into a space."""
        if stress_notation not in self.STRESS_NOTATIONS:
            raise ValueError(f"stress_notation must be one of {self.STRESS_NOTATIONS}, "
                             f"not {stress_notation!r}")
        super().__init__(alphabet, normalizer)
        self.stress_notation = stress_notation
        rules = {"lowercase": lowercase, "in_word_chars": in_word_chars,
                 "replace_chars": None if replace_chars is None else dict(replace_chars),
                 "drop_chars": drop_chars}
        for name, value in rules.items():
            if value is not None:
                setattr(self, name, value)

    def reads_stress_mark(self, lang: str) -> bool:
        """The output writes the mark, in every language, unless the notation is ``"none"``."""
        return self.stress_notation != "none"

    def _revision_arguments(self) -> Dict[str, object]:
        return {"stress_notation": self.stress_notation}

    def phonemize_string(self, text: str, lang: str) -> str:
        """*text* after the character rules; *lang* matters only for the ``"plus"`` stress notation."""
        if self.lowercase:
            text = text.lower()
        text = "".join(char if char in self.in_word_chars and _between_letters(text, i)
                       else self.replace_chars.get(char, char)
                       for i, char in enumerate(text))
        text = text.translate(dict.fromkeys(map(ord, self.drop_chars)))
        text = self.whitespace_re.sub(" ", text).strip()
        if self.stress_notation == "plus":
            from scriptconv.diacritics import replace_stress_mark
            text = replace_stress_mark(text, lang, before="+")
        return text

    def _identity_settings(self) -> Dict[str, object]:
        """Each character rule and the whitespace pattern, when set on the
        instance to a value other than the class default."""
        settings = {name: getattr(self, name) for name in self._RULES
                    if name in vars(self) and getattr(self, name) != getattr(type(self), name)}
        if "replace_chars" in settings:
            settings["replace_chars"] = dict(settings["replace_chars"])
        if "whitespace_re" in settings:
            settings["whitespace_re"] = [settings["whitespace_re"].pattern, settings["whitespace_re"].flags]
        return settings


class UnicodeCodepointPhonemizer(BasePhonemizer):
    """The codepoints of the text in a Unicode normal form; NFD splits accents into their own codepoints."""

    def __init__(self, form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFD"):
        self.form = form
        super().__init__(Alphabet.UNICODE)

    def reads_stress_mark(self, lang: str) -> bool:
        """The output is the text's codepoints, so the mark is one of them in every language."""
        return True

    def _revision_arguments(self) -> Dict[str, object]:
        return {"form": self.form}

    def phonemize_string(self, text: str, lang: str) -> str:
        """*text* in the normal form :attr:`form`; *lang* is ignored."""
        return unicodedata.normalize(self.form, text)
