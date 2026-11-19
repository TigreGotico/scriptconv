"""Phonemizer contract and base implementations.

This subpackage holds scriptconv's phonemizer integrations: *wrappers* around
external phonemizer engines behind optional extras — the same boundary as
:mod:`scriptconv.readings` wrapping reading dictionaries.  The zero-dependency
core stays free of them, and no grapheme-to-phoneme rules are implemented in
the core; in-tree
implementations live under ``_thirdparty`` with their provenance, installed
only with the ``phonemizers`` extras.

The ``phonemizers`` base extra provides sentence chunking (``quebra_frases``)
and language matching (``linguatag``).

**Normalization is injectable, not built in.**  TTS stacks normalize numbers,
dates and abbreviations before phonemizing; that requires language resources
scriptconv does not ship.  Pass ``normalizer=`` (a ``(text, lang) -> str``
callable) at construction to run it inside ``phonemize_lazy``; without it the
raw text is phonemized as-is.  Downstream TTS injects its own normalizer, so
calling a wrapper through scriptconv directly and through a TTS stack can
legitimately differ on text containing digits.
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
# is trained on. These are the six clause types Piper appends after every
# espeak-ng clause (piper-phonemize ``src/phonemize.cpp``): a full stop,
# question mark and exclamation mark stand alone, a comma, colon and semicolon
# are followed by a space. Arabic script has its own comma, semicolon and
# question mark; they map onto the same symbols.
CLAUSE_PUNCTUATION = {".": ".", "?": "?", "!": "!", ",": ",", ":": ":", ";": ";",
                      "\u060c": ",", "\u061b": ";", "\u061f": "?"}
_PAUSE_PUNCTUATION = {",", ":", ";"}
_CLAUSE_TOKENS = frozenset(CLAUSE_PUNCTUATION.values())
# A mark that the table reads as "!" or "?", between two letters with no space
# after it, is no clause break, but it still separates two words.
_SEPARATING_MARKS = frozenset(mark for mark, symbol in CLAUSE_PUNCTUATION.items()
                              if symbol in ("!", "?"))
# A clause ends at punctuation followed by whitespace, as in espeak-ng, so the
# "," in "10,4" or the ":" in "16:30" never splits. A lone "." is left to the
# sentence tokenizer, which knows abbreviations; inside a sentence an ellipsis
# or "|" still ends a clause, as in chunk_text, but carries no symbol (espeak-ng
# reads an ellipsis as a spoken-name pause, which Piper does not keep).
# A match starts only where a run of marks starts, and the run must reach
# whitespace, so each run is read a fixed number of times and the split takes
# linear time. Group 1 is the break: the first mark of the run that ends a
# clause, through the end of the run.
_CLAUSE_BREAK = re.compile(
    r"(?<![^\w\s])(?=[^\w\s]*+\s)[^\w\s]*?((?:\.\.|\u2026|[,:;!?|\u060c\u061b\u061f])[^\w\s]*+)")
# Starts only where a run of marks starts, so a long run is read once.
_TRAILING_PUNCTUATION = re.compile(r"(?<![^\w\s])[^\w\s]++\s*+$")
# One or more blank lines: a paragraph break.
_PARAGRAPH_BREAK = re.compile(r"(\n(?:[^\S\n]*\n)+)")
_LANG_FLAGS = re.compile(r"\([^)]+\)")
# The stress mark that the diacritize stage (stressonnx) writes after a stressed vowel.
STRESS_MARK = "\u0301"
# The methods through which text reaches a backend.
_TEXT_METHODS = ("phonemize_string", "phonemize_to_list", "phonemize", "phonemize_lazy",
                 "phonemize_segments")


def join_sentences(sentences: Iterable[List[str]], keep_punctuation: bool = True) -> List[str]:
    """Per-sentence phonemes joined into one flat training stream.

    A sentence that ends in a clause token joins the next one with no space,
    as Piper flattens its sentences. A sentence that ends in a space also
    joins with no space. Every other sentence, as one the sentence tokenizer
    ends at an ASCII "...", takes one space before the next sentence, so its
    last word stays apart from the first word of the next sentence. No
    sentence starts with a space, because a voice never saw a space at the
    start of an utterance, so the space exists only here.

    Without *keep_punctuation* no sentence ends in a token, so one space
    separates every two sentences. With it, a sentence that ends in a clause
    symbol (``. ? ! , : ;``) counts as ending in a token. A phoneme written
    with the same character, such as an ASCII ``":"`` for vowel length, counts
    the same way. :meth:`BasePhonemizer.phonemize_to_list` knows which symbols
    it appended, so it joins its own sentences without that ambiguity.
    """
    return _join((sentence, keep_punctuation and bool(sentence)
                  and sentence[-1] in _CLAUSE_TOKENS) for sentence in sentences)


def _join(sentences: Iterable[Tuple[List[str], bool]]) -> List[str]:
    """``(phonemes, ends_in_token)`` sentences joined by the rule of :func:`join_sentences`."""
    phonemes: List[str] = []
    joins = True
    for sentence, ends_in_token in sentences:
        if not sentence:
            continue
        if not joins:
            phonemes.append(" ")
        phonemes.extend(sentence)
        joins = ends_in_token or sentence[-1] == " "
    return phonemes


def _clause_breaks_as_spaces(phonemes: str) -> str:
    """*phonemes* with each clause break that a backend prints as a line break read as one space.

    espeak-ng prints each clause on its own line. The next clause starts a new
    word, so a break between two clauses is a space, and never a double one.
    """
    if "\n" not in phonemes:
        return phonemes
    return " ".join(line.strip() for line in phonemes.split("\n") if line.strip())


def _between_letters(text: str, index: int) -> bool:
    """Whether the character at *index* of *text* stands between two letters.

    The letter before it may carry combining marks, such as a stress mark (U+0301).
    """
    if not 0 < index < len(text) - 1 or not text[index + 1].isalpha():
        return False
    letter = index - 1
    while letter > 0 and unicodedata.category(text[letter]).startswith("M"):
        letter -= 1
    return text[letter].isalpha()


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
    backend.

    Its meaning depends on :attr:`frontend`. With ``frontend`` ``None``, a
    backend called directly, it is the backend's own revision. With
    ``frontend`` set, it is the frontend revision with the ``sc1:`` prefix.
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
    keeps punctuation. A bounded segment holds its marks among its own
    symbols, so the frontend appends nothing to it, and the mark tells only
    that the segment ends at a mark."""
    ends_sentence: bool = True
    """Whether the segment ends a sentence."""
    streams: Mapping[str, Tuple] = dataclasses.field(default_factory=dict)
    """Side streams of the backend, such as stress, each in step with :attr:`phonemes`."""
    ends_paragraph: bool = False
    """Whether a paragraph break (one or more blank lines) follows the
    segment in the text. Only a segment that ends a sentence ends a
    paragraph."""
    bounded: bool = False
    """Whether the first symbol of :attr:`phonemes` is the backend's start
    symbol and the last its end symbol, as ``<bos>`` and ``<eos>``. Where the
    frontend joins two bounded segments, the inner end and start symbols go,
    with their stream values. A segment with no mark then takes the
    backend's :meth:`~BasePhonemizer.word_break` before the next one."""
    text: Optional[str] = None
    """The source text of the segment after the frontend's text stages
    (casing, normalise, diacritize), as the backend read it; it never holds a
    clause mark that the frontend appends; ``None`` when the backend cannot
    say."""


class MissingLanguageError(ValueError):
    """No language reached :meth:`BasePhonemizer.match_lang` at all.

    Raised for ``None``/``""``/``"und"`` targets, which is a distinct failure
    from an unsupported-but-present tag: it means whatever called into the
    phonemizer never determined a language for the text, an upstream
    config/data defect rather than a phonemizer capability gap.
    """


def _primary_subtag(lang: str) -> str:
    """Lowercase, ``_``→``-`` normalized primary language subtag.

    Used for exact-match language routing (e.g. registry lang defaults,
    diacritization backend selection) rather than ``str.startswith``, so
    e.g. Berber (``ber``) never false-matches Belarusian (``be``).
    """
    return lang.lower().replace("_", "-").split("-")[0]


def _check_alphabet(phonemizer, alphabet: Alphabet,
                    supported: List[Alphabet]) -> None:
    """Reject an output alphabet a wrapper cannot emit, with a usable message.

    Wrappers used to guard this with a bare ``assert``, which surfaced as an
    ``AssertionError`` carrying an empty message — the caller learned nothing
    about which alphabet it asked for or which ones exist. That matters because
    :func:`~scriptconv.phonemizers.registry.get_phonemizer` injects its own
    ``alphabet=`` default into every constructor that declares the parameter,
    so an unsupported default is hit by ordinary registry use, not just by
    callers passing an odd value.
    """
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

    Off by default, so voices trained without punctuation receive exactly the
    sequences they were trained on. When on, :meth:`phonemize_to_list` and
    :meth:`phonemize_lazy` phonemize clause by clause and append each clause's
    symbol the way Piper does. With the flag on or off,
    :meth:`phonemize_to_list` of a text is the sentences that
    :meth:`phonemize_lazy` yields for it, joined by the rule of
    :func:`join_sentences`. :meth:`phonemize_lazy` first runs the
    ``normalizer`` hook, and :meth:`phonemize_to_list` does not, so with a
    hook the two read the same text only when the caller normalizes first.
    A backend that overrides either method owns its own output and
    ignores this flag, since honouring it on one side only would make training
    and synthesis disagree.
    """

    strict: bool = False
    """Raise :class:`UnreadTextError` when a pinyin backend meets a syllable
    that is not pinyin, or a digit it cannot read.

    Subclasses of
    :class:`~scriptconv.phonemizers.zh.BaseChinesePinyinPhonemizer` read this
    field when they write IPA, for a syllable that is not pinyin.
    :class:`~scriptconv.phonemizers.g2pw.G2PWPhonemizer` reads it for a
    digit, which gives no symbol. With the field off, they log a warning and
    drop the syllable or the digit. Every other backend ignores the field.
    :class:`~scriptconv.frontend.TextFrontend` sets it from
    ``FrontendConfig.strict``.
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
    """The distribution that holds the engine. ``None`` means code inside
    scriptconv, or inside the scriptconv-copyleft or scriptconv-nonfree
    package that holds the wrapper. It is declared, because the module of a
    wrapper class names scriptconv and not the engine that produced the
    phonemes."""

    stress_mark_langs: ClassVar[frozenset[str]] = frozenset()
    """Languages in which this backend reads the stress mark (U+0301 after a vowel) as stress.

    ``scripts/probe_stress_marks.py`` gives the declaration: only a language
    in which the mark moves the stress to the marked vowel, and changes
    nothing else, is declared. For a language of
    :data:`scriptconv.diacritics.STRESS_LANGS` that the backend does not
    declare, the backend removes the mark from its text before it reads it.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # every text path, also one that a backend overrides, reads the mark as declared
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
        # optional (text, lang) -> str hook run before chunking; see module
        # docstring — scriptconv performs no normalization of its own
        self.normalizer = normalizer

    @abc.abstractmethod
    def phonemize_string(self, text: str, lang: str) -> str:
        raise NotImplementedError

    def reads_stress_mark(self, lang: str) -> bool:
        """True when this backend reads the stress mark in *lang*, as :attr:`stress_mark_langs` declares."""
        return _declared(self.stress_mark_langs, lang)

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        """Phonemes of *text* as one flat list, without normalization.

        The list is the sentences of :meth:`phonemize` joined by the rule of
        :func:`join_sentences`, so a voice trains on the sequences that
        synthesis gives it. Without :attr:`keep_punctuation` no punctuation
        reaches the list, and one space separates two sentences. With it, each
        clause's symbol comes before its space, and a sentence that ends in an
        appended symbol joins the next one with no space. Clause breaks that a
        backend prints as ``"\\n"`` are not phonemes: each becomes one space,
        because the next clause starts a new word. A backend that overrides
        :meth:`phonemize_lazy` keeps its own synthesis, so its list is the
        whole text read by :meth:`phonemize_string`.
        """
        if self._keeps_punctuation():
            return _join(self._punctuated_sentences(text, lang))
        if type(self).phonemize_lazy is not BasePhonemizer.phonemize_lazy:
            return list(_clause_breaks_as_spaces(self.phonemize_string(text, lang)))
        return join_sentences(self._bare_sentences(text, lang), keep_punctuation=False)

    def phonemize(self, text: str, lang: str) -> PhonemizedChunks:
        # PhonemizedChunks is list[list[str]]; empty text yields no
        # sentences. (Returning the raw (str, str, bool) tuple form here
        # corrupted the type and broke callers that mutate each sentence,
        # e.g. inline ``[[phoneme]]`` blocks in TTSVoice.phonemize.)
        return list(self.phonemize_lazy(text, lang))

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """Lazy, per-sentence variant of :meth:`phonemize`.

        Yields one phoneme list per sentence-level chunk, invoking the
        (potentially expensive) ``phonemize_string`` only as each sentence is
        pulled from the generator. This lets a caller start synthesizing
        sentence 1 before sentence 2 has been phonemized, cutting
        time-to-first-audio.

        Normalization and chunking still run over the *whole* text up front (both
        are cheap and order-sensitive), so ``list(self.phonemize_lazy(text)) ==
        self.phonemize(text)`` holds for any input.
        """
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        if self._keeps_punctuation():
            yield from (phonemes for phonemes, _ in self._punctuated_sentences(text, lang))
        else:
            yield from self._bare_sentences(text, lang)

    def phonemize_segments(self, text: str, lang: str) -> Iterator[Segment]:
        """The segments of *text* in reading order, read in one pass.

        A backend that sets :attr:`reads_whole_text` overrides this method and
        cuts its own output at its own sentence and clause marks. The segment
        text holds no punctuation: the mark that ends a segment is in
        :attr:`Segment.mark`.

        For any other backend, :class:`~scriptconv.frontend.TextFrontend`
        calls this method on each sentence or clause, and a segment is a
        sentence of :meth:`phonemize_lazy`. A backend with side streams, or
        with its own start and end symbols, overrides it to give them. A
        single segment carries the input *text* (stripped) as its
        :attr:`Segment.text`; when the backend yields more than one, the
        segment text is ``None``.

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

        :class:`~scriptconv.frontend.TextFrontend` writes it where it joins
        two pieces with no clause symbol between them, and around an inline
        block. A stream that the segment lacks takes 0.
        """
        return Segment((" ",))

    def mark_symbols(self, marks: str) -> Optional[Segment]:
        """The symbols that this backend writes for *marks* after a word, with their stream values, or ``None``.

        This is the backend's mark table. *marks* is a run of closing marks,
        such as ``.``, ``...`` or ``?!``, or a quote that opens the next word,
        with the whitespace before them in the text, if any.
        :class:`~scriptconv.frontend.TextFrontend` reads it for the marks
        after an inline block, and writes the symbols of the table after the
        block. ``None`` declares no table.
        """
        return None

    def _bare_sentences(self, text: str, lang: str) -> Iterator[List[str]]:
        """Per-sentence phonemes, with the punctuation removed before the backend.

        The backend reads each chunk of :meth:`chunk_text` alone. A ``:``,
        ``;``, ``...`` or ``|`` inside a sentence is a clause break, so it is a
        space, as a ``,`` is. In ``el`` a ``;`` is the question mark, so it
        ends the sentence.

        A backend that owns ``normalize`` reads the text with its own rules, so
        its chunk reaches it as written, stripped of outer whitespace, with the
        punctuation that its normaliser reads.
        """
        question_semicolon = _primary_subtag(lang) == "el"
        sentence: List[List[str]] = []
        for chunk, punct, eos in self.chunk_text(text):
            read = (chunk.strip() if "normalize" in self.owned_stages
                    else self.remove_punctuation(chunk))
            phoneme_str = _clause_breaks_as_spaces(self.phonemize_string(read, lang))
            # Filter out (lang) switch (flags) that surround words from languages
            # other than the current voice — mirrors _process_phones().
            phoneme_str = re.sub(r"\([^)]+\)", "", phoneme_str)
            sentence.append(list(phoneme_str))
            if eos or (question_semicolon and punct == ";"):
                yield join_sentences(sentence, keep_punctuation=False)
                sentence = []

    def _keeps_punctuation(self) -> bool:
        cls = type(self)
        return (self.keep_punctuation
                and cls.phonemize_to_list is BasePhonemizer.phonemize_to_list
                and cls.phonemize_lazy is BasePhonemizer.phonemize_lazy)

    def _punctuated_sentences(self, text: str, lang: str) -> Iterator[Tuple[List[str], bool]]:
        """Per-sentence phonemes with each clause's punctuation appended.

        Each clause is phonemized on its own with its punctuation removed, so
        the backend sees the same words in training and in synthesis, and the
        clause's symbol is appended after it: bare for ``. ? !``, followed by a
        space for ``, : ;``. A space also separates a clause from the next one
        in the same sentence, after any symbol or none. No sentence starts with
        a space: :func:`join_sentences` adds the space between two sentences.
        Each sentence comes with whether it ends in an appended symbol.

        A backend that owns ``normalize`` reads the text with its own rules, so
        each clause reaches it as written, stripped of outer whitespace, with
        the punctuation that its normaliser reads; the base still appends the
        clause symbol.
        """
        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None
        for sentence in sentence_tokenize(text):
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
                yield phonemes, ends_in_token

    @staticmethod
    def _process_phones(raw_phones: RawPhonemizedChunks) -> PhonemizedChunks:
        """Text to phonemes grouped by sentence."""
        all_phonemes: list[list[str]] = []
        sentence_phonemes: list[str] = []
        for phonemes_str, terminator_str, end_of_sentence in raw_phones:
            # Filter out (lang) switch (flags).
            # These surround words from languages other than the current voice.
            phonemes_str = re.sub(r"\([^)]+\)", "", phonemes_str)
            sentence_phonemes.extend(list(phonemes_str))
            if end_of_sentence:
                all_phonemes.append(sentence_phonemes)
                sentence_phonemes = []
        if sentence_phonemes:
            all_phonemes.append(sentence_phonemes)
        return all_phonemes

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
        """
        Validates and returns the closest supported language code.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: The validated language code.

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
            # raise an error for unsupported language
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
        """The constructor arguments, as JSON values, that rebuild this backend
        in the probe of :func:`~scriptconv.phonemizers._revision.code_revision`."""
        return {}

    def _identity_settings(self) -> Dict[str, object]:
        """The settings on the instance, as JSON values, that change
        :meth:`identity` besides the constructor arguments. They join the key
        of the identity cache."""
        return {}

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        """The distributions whose own revision the identity of this backend
        holds for *lang*. The probe of
        :func:`~scriptconv.phonemizers._revision.code_revision` leaves their
        files out of the hash."""
        return frozenset()

    def identity(self, lang: str) -> PhonemizerIdentity:
        """What phonemizes *lang* here: the engine, its version and the lect.

        Raises:
            ImportError: If the engine is not installed.
            UnsupportedLanguageError: If the backend does not support *lang*.
        """
        from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY
        names = {cls_name: member.value
                 for member, (_, cls_name, _) in PHONEMIZER_REGISTRY.items()}
        backend = next((names[cls.__name__] for cls in type(self).__mro__
                        if cls.__name__ in names), type(self).__name__)
        distribution, version = self._engine_release()
        # Grapheme, Unicode and Phonetisaurus backends take any language.
        resolved = self.get_lang(lang) if hasattr(self, "get_lang") else lang
        return PhonemizerIdentity(backend, distribution, version, resolved)

    @staticmethod
    def remove_punctuation(text):
        """
        Removes punctuation characters from a string, based on unicode punctuation
        categories (P*) rather than ASCII-only ``string.punctuation``. This also strips
        non-ASCII punctuation such as Arabic ``،``/``؟`` and curly quotes.

        Apostrophes and hyphens sandwiched between letters (e.g. "don't", "well-known")
        are preserved so contractions and compounds aren't broken apart, and any
        punctuation character sandwiched between two digits (e.g. the ":" in a clock
        time "16:30", the "," in "10,4", the "." in "92.073", the "-" in "1139-1185")
        is preserved so the per-language normalizers still see it as a single token,
        matching the digit:digit exemption in ``chunk_text``.

        A mark that :data:`CLAUSE_PUNCTUATION` reads as ``!`` or ``?``, such as
        the Arabic ``؟``, between two letters, as in "Sim!Não", still
        separates two words, so a run of them becomes one space.
        """
        out = []
        chars = list(text)
        separates = False
        for i, c in enumerate(chars):
            if c in ("'", "’", "-") and _between_letters(text, i):
                out.append(c)
                continue
            if c in _SEPARATING_MARKS:
                if i == 0 or chars[i - 1] not in _SEPARATING_MARKS:
                    end = i
                    while end < len(chars) and chars[end] in _SEPARATING_MARKS:
                        end += 1
                    letter = i - 1
                    while letter > 0 and unicodedata.category(chars[letter]).startswith("M"):
                        letter -= 1
                    separates = (i > 0 and chars[letter].isalpha()
                                 and end < len(chars) and chars[end].isalpha())
                    if separates:
                        out.append(" ")
                if separates:
                    continue
            if 0 < i < len(chars) - 1 \
                    and chars[i - 1].isdigit() and chars[i + 1].isdigit():
                out.append(c)
                continue
            if unicodedata.category(c).startswith("P"):
                continue
            out.append(c)
        return "".join(out).strip()

    @staticmethod
    def chunk_text(text: str, delimiters: Optional[List[str]] = None) -> TextChunks:
        """
        Split input text into sentence-aware chunks using sentence tokenization and optional intra-sentence delimiters.

        Parameters:
            text (str): Input text to split. If empty, returns a single empty chunk.
            delimiters (Optional[List[str]]): List of substring delimiters to split sentences by (defaults to [":", ";", "...", "|"]).

        Returns:
            TextChunks: A list of tuples (substring, terminator, end_of_sentence) where:
                - `substring` is the chunk text with surrounding whitespace removed,
                - `terminator` is the delimiter that followed the substring or the sentence-final punctuation if none matched,
                - `end_of_sentence` is `True` for the final chunk of a tokenized sentence, `False` otherwise.
        """
        if not text:
            return [('', '', True)]

        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None

        results: TextChunks = []
        delimiters = delimiters or [":", ";", "...", "|"]

        # Create a regex pattern that matches any of the delimiters. A
        # delimiter sitting directly between two digits (eg. the ":" in a
        # clock time "16:30" or a score "3:2") is not a sentence-internal
        # boundary, so it is only excluded when *both* neighbours are
        # digits — a delimiter with a digit on just one side (eg. "12: ")
        # still splits as before.
        def _delim_alt(delimiter: str) -> str:
            escaped = re.escape(delimiter)
            return f"(?:(?<!\\d){escaped}|{escaped}(?!\\d))"

        delimiter_pattern = _delim_alt(delimiters[0])
        for delimiter in delimiters[1:]:
            delimiter_pattern += f"|{_delim_alt(delimiter)}"

        for sentence in sentence_tokenize(text):
            # Default punctuation if no specific punctuation found
            default_punc = sentence[-1] if sentence and sentence[-1] in string.punctuation else "."

            # Use regex to split the sentence by any of the delimiters
            parts = re.split(f'({delimiter_pattern})', sentence)

            # Group parts into chunks (text + delimiter)
            chunks = []
            for i in range(0, len(parts), 2):
                # If there's a delimiter after the text, use it
                delimiter = parts[i + 1] if i + 1 < len(parts) else default_punc

                # Last chunk is marked as complete
                is_last = (i + 2 >= len(parts))

                chunks.append((parts[i].strip(), delimiter.strip(), is_last))

            results.extend(chunks)

        return results


class GraphemePhonemizer(BasePhonemizer):
    """
    A phonemizer class that treats input text as graphemes (characters).
    It performs text normalization and returns the normalized text as a string
    of characters. A hyphen between two letters is part of the word, as in
    ``motse-moholo``, so it stays. Any other hyphen becomes a space.

    ``stress_notation`` is how the output writes the stress mark (U+0301
    after a vowel) of a :data:`scriptconv.diacritics.STRESS_LANGS` language:
    ``"acute"`` keeps U+0301, ``"plus"`` writes ``+`` before the stressed
    vowel (``прив+ет``), and ``"none"`` removes the mark. In any other
    language an acute is spelling and stays.
    """
    STRESS_NOTATIONS = ("acute", "plus", "none")
    # Regular expression matching whitespace:
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
    _RULES = ("lowercase", "in_word_chars", "replace_chars", "drop_chars")

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
        """
        Normalizes input text by applying a series of transformations
        and returns it as a sequence of graphemes.

        Parameters:
            text (str): Input text to be converted to graphemes.
            lang (str): The language code (ignored for grapheme phonemization,
                        but required by BasePhonemizer).

        Returns:
            str: A normalized string of graphemes.
        """
        if self.lowercase:
            text = text.lower()
        text = "".join(char if char in self.in_word_chars and _between_letters(text, i)
                       else self.replace_chars.get(char, char)
                       for i, char in enumerate(text))
        text = text.translate(dict.fromkeys(map(ord, self.drop_chars)))
        text = re.sub(self.whitespace_re, " ", text).strip()
        if self.stress_notation == "plus":
            from scriptconv.diacritics import replace_stress_mark
            text = replace_stress_mark(text, lang, before="+")
        return text

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the hash of the code and data
        on the path of this backend, as
        :func:`~scriptconv.phonemizers._revision.code_revision` gives it. A
        character rule set on the instance joins the hash."""
        from scriptconv.phonemizers._revision import code_revision
        revision = code_revision(self, lang, self._identity_settings())
        return dataclasses.replace(super().identity(lang), revision=revision)

    def _identity_settings(self) -> Dict[str, object]:
        """Each character rule set on the instance to a value other than the class default."""
        settings = {name: getattr(self, name) for name in self._RULES
                    if name in vars(self) and getattr(self, name) != getattr(type(self), name)}
        if "replace_chars" in settings:
            settings["replace_chars"] = dict(settings["replace_chars"])
        return settings


class UnicodeCodepointPhonemizer(BasePhonemizer):
    """Phonemes = codepoints
    normalization also splits accents and punctuation into it's own codepoints
    """

    def __init__(self, form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFD"):
        self.form = form
        super().__init__(Alphabet.UNICODE)

    def reads_stress_mark(self, lang: str) -> bool:
        """The output is the text's codepoints, so the mark is one of them in every language."""
        return True

    def _revision_arguments(self) -> Dict[str, object]:
        return {"form": self.form}

    def phonemize_string(self, text: str, lang: str) -> str:
        # Phonemes = codepoints
        """
        Normalize the input text to Unicode NFD so phonemes correspond to individual Unicode codepoints.

        Parameters:
            text (str): The input string to normalize.
            lang (str): Language code (ignored by this implementation).

        Returns:
            str: The input text normalized to Unicode NFD, with combining marks separated into distinct codepoints.
        """
        return unicodedata.normalize(self.form, text)

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the hash of the code and data
        on the path of this backend and of its normalisation form, as
        :func:`~scriptconv.phonemizers._revision.code_revision` gives it."""
        from scriptconv.phonemizers._revision import code_revision
        revision = code_revision(self, lang, {})
        return dataclasses.replace(super().identity(lang), revision=revision)
