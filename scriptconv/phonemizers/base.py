"""Phonemizer contract and base implementations.

Phonemization (orthography → sound) is out of scope for scriptconv's
zero-dependency core; this subpackage holds *wrappers* around external
phonemizer engines behind optional extras — the same boundary as
:mod:`scriptconv.readings` wrapping reading dictionaries.  No
grapheme-to-phoneme rules are implemented in the core; in-tree
implementations live under ``_thirdparty`` with their provenance, installed
only with the ``phonemizers`` extras.

The ``phonemizers`` base extra provides sentence chunking (``quebra_frases``)
and language matching (``langcodes``).

**Normalization is injectable, not built in.**  TTS stacks normalize numbers,
dates and abbreviations before phonemizing; that requires language resources
scriptconv does not ship.  Pass ``normalizer=`` (a ``(text, lang) -> str``
callable) at construction to run it inside ``phonemize_lazy``; without it the
raw text is phonemized as-is.  Downstream TTS injects its own normalizer, so
calling a wrapper through scriptconv directly and through a TTS stack can
legitimately differ on text containing digits.
"""
import abc
import re
import string
import unicodedata
from typing import Callable, Iterator, List, Optional, Tuple, Literal, Union

from scriptconv.phonemizers.enums import Alphabet

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
# A clause ends at punctuation followed by whitespace, as in espeak-ng, so the
# "," in "10,4" or the ":" in "16:30" never splits. A lone "." is left to the
# sentence tokenizer, which knows abbreviations; inside a sentence an ellipsis
# or "|" still ends a clause, as in chunk_text, but carries no symbol (espeak-ng
# reads an ellipsis as a spoken-name pause, which Piper does not keep).
_CLAUSE_BREAK = re.compile(r"(?:\.\.+|\u2026|[,:;!?|\u060c\u061b\u061f])[^\w\s]*(?=\s)")
_TRAILING_PUNCTUATION = re.compile(r"[^\w\s]+\s*$")
_LANG_FLAGS = re.compile(r"\([^)]+\)")


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
        clauses.append((sentence[start:match.start()], _clause_mark(match.group())))
        start = match.end()
    tail = sentence[start:]
    trailing = _TRAILING_PUNCTUATION.search(tail)
    clauses.append((tail, _clause_mark(trailing.group()) if trailing else None))
    return clauses


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


class BasePhonemizer(metaclass=abc.ABCMeta):
    keep_punctuation: bool = False
    """Keep clause punctuation (``, . ? ! : ;``) in the phoneme output.

    Off by default, so voices trained without punctuation receive exactly the
    sequences they were trained on. When on, :meth:`phonemize_to_list` and
    :meth:`phonemize_lazy` phonemize clause by clause and append each clause's
    symbol the way Piper does, and the two return the same phonemes for the
    same text. A backend that overrides either method owns its own output and
    ignores this flag, since honouring it on one side only would make training
    and synthesis disagree.
    """

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

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        """Phonemes of *text* as one flat list, without normalization.

        Clause breaks that a backend prints as ``"\\n"`` (espeak-ng does at
        every comma, question mark and exclamation mark) are not phonemes and
        are dropped; with :attr:`keep_punctuation` the clause's punctuation
        takes their place.
        """
        if self._keeps_punctuation():
            return [p for sentence in self._punctuated_sentences(text, lang)
                    for p in sentence]
        return [p for p in self.phonemize_string(text, lang) if p != "\n"]

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
            yield from self._punctuated_sentences(text, lang)
            return
        for chunk, punct, eos in self.chunk_text(text):
            phoneme_str = self.phonemize_string(self.remove_punctuation(chunk), lang)
            # Filter out (lang) switch (flags) that surround words from languages
            # other than the current voice — mirrors _process_phones().
            phoneme_str = re.sub(r"\([^)]+\)", "", phoneme_str)
            # phonemize() marks every chunk as end-of-sentence, so each chunk is
            # its own sentence.
            yield list(phoneme_str)

    def _keeps_punctuation(self) -> bool:
        cls = type(self)
        return (self.keep_punctuation
                and cls.phonemize_to_list is BasePhonemizer.phonemize_to_list
                and cls.phonemize_lazy is BasePhonemizer.phonemize_lazy)

    def _punctuated_sentences(self, text: str, lang: str) -> Iterator[List[str]]:
        """Per-sentence phonemes with each clause's punctuation appended.

        Each clause is phonemized on its own with its punctuation removed, so
        the backend sees the same words in training and in synthesis, and the
        clause's symbol is appended after it: bare for ``. ? !``, followed by a
        space for ``, : ;``.
        """
        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None
        for sentence in sentence_tokenize(text):
            phonemes: List[str] = []
            for clause, mark in split_clauses(sentence):
                clause = self.remove_punctuation(clause)
                if not clause:
                    continue
                phoneme_str = _LANG_FLAGS.sub("", self.phonemize_string(clause, lang))
                clause_phonemes = [p for p in phoneme_str if p != "\n"]
                if not clause_phonemes:
                    continue
                phonemes.extend(clause_phonemes)
                if mark:
                    phonemes.append(mark)
                    if mark in _PAUSE_PUNCTUATION:
                        phonemes.append(" ")
            if phonemes:
                yield phonemes

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
        """Closest supported language and its distance (langcodes tag_distance)."""
        from langcodes import tag_distance
        if isinstance(valid_langs, str):
            valid_langs = [valid_langs]
        if target_lang in valid_langs:
            return target_lang, 0
        best_lang, best_distance = "und", 10000000
        for l in valid_langs:
            try:
                distance = tag_distance(l, target_lang)
            except Exception:
                try:
                    distance = tag_distance(l.split("-")[0], target_lang)
                except Exception:
                    continue
            if distance < best_distance:
                best_lang, best_distance = l, distance
        if best_distance <= 10:
            return best_lang, best_distance
        return "und", 10000

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
            ValueError: If the language code is unsupported.
        """
        if target_lang in (None, "", "und"):
            raise MissingLanguageError(
                f"no language provided to phonemize: {target_lang!r}")
        lang, score = BasePhonemizer._match_lang(target_lang, valid_langs)
        if score > 10:
            # raise an error for unsupported language
            raise ValueError(f"unsupported language code: {target_lang}")
        return lang

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
        """
        out = []
        chars = list(text)
        for i, c in enumerate(chars):
            if c in ("'", "’", "-") and 0 < i < len(chars) - 1 \
                    and chars[i - 1].isalpha() and chars[i + 1].isalpha():
                out.append(c)
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
    of characters.
    """
    # Regular expression matching whitespace:
    whitespace_re = re.compile(r"\s+")

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
        text = text.lower()
        text = text.replace(";", ",")
        text = text.replace("-", " ")
        text = text.replace(":", ",")
        text = re.sub(r"[\<\>\(\)\[\]\"]+", "", text)
        text = re.sub(self.whitespace_re, " ", text).strip()
        return text


class UnicodeCodepointPhonemizer(BasePhonemizer):
    """Phonemes = codepoints
    normalization also splits accents and punctuation into it's own codepoints
    """

    def __init__(self, form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFD"):
        self.form = form
        super().__init__(Alphabet.UNICODE)

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
