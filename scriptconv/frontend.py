"""The text frontend: text stages and a phonemizer backend in one fixed order.

:class:`TextFrontend` takes text to phonemes. Every path runs the same order:

1. Split out inline ``[[phonemes]]`` blocks. No stage reads the text inside a
   block, and its symbols reach the output as written.
2. Split the text into sentences. :meth:`TextFrontend.prepare` and
   :meth:`TextFrontend.phonemize_flat` take the text whole.
3. Run the normalisation hook, if the caller set one.
4. Apply casing, if the call sets a casing function.
5. Diacritize.
6. Run the backend.

The frontend skips a stage that the backend names in ``owned_stages``, because
the backend runs it itself. scriptconv does not normalise text. The hook is
off by default, and :func:`spoken_normalizer` returns ``text2spoken.normalize``
for it.

With ``strict=False`` a failed stage logs a warning and the text continues
without that stage. With ``strict=True`` it raises :class:`StageError`.
"""
import copy
import dataclasses
import importlib.util
import logging
from typing import Callable, Iterator, List, Optional

from scriptconv.diacritics import _DIACRITIZER_PACKAGES, _diacritizer_family, diacritize
from scriptconv.graph import ConversionGraph, Edge
from scriptconv.phonemizers.base import (
    BasePhonemizer,
    PhonemizerIdentity,
    StageError,
    UnreadTextError,
)
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.registry import get_phonemizer, phonemizer_for_lang

__all__ = ["Stages", "FrontendConfig", "TextFrontend", "spoken_normalizer"]

LOG = logging.getLogger(__name__)

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


def _block_phonemes(parts: List[str], index: int) -> List[str]:
    """The symbols of the inline block at *index* of a split text.

    A space before or after the block in the text becomes a space symbol.
    """
    phonemes = [" "] if parts[index - 1].endswith(" ") else []
    phonemes.extend(parts[index][2:-2].strip())
    if parts[index + 1].startswith(" "):
        phonemes.append(" ")
    return phonemes


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
        """Phonemes of *text*, one list per sentence, as each sentence is read.

        A block's symbols join the sentence before the block, and the text
        after a block starts a new sentence. A sentence that gives no phonemes
        is not yielded.
        """
        stages = self._resolve(stages)
        parts = _split_blocks(text)
        if len(parts) == 1:
            yield from self._sentences(text, stages)
            return
        # A block can extend the sentence before it, so that sentence is held
        # until the next part is known.
        held: List[str] = []
        for index, part in enumerate(parts):
            if index % 2:
                held.extend(_block_phonemes(parts, index))
                continue
            for sentence in self._sentences(part, stages):
                if held:
                    yield held
                held = sentence
        if held:
            yield held

    def phonemize(self, text: str, stages: Optional[Stages] = None) -> List[List[str]]:
        """Phonemes of *text*, one list per sentence."""
        return list(self.phonemize_lazy(text, stages))

    def phonemize_flat(self, text: str, stages: Optional[Stages] = None) -> List[str]:
        """Phonemes of *text* as one list, for training.

        The text is not split into sentences. The backend's
        ``phonemize_to_list`` reads each piece of text between blocks.
        """
        stages = self._resolve(stages)
        parts = _split_blocks(text)
        phonemes: List[str] = []
        for index, part in enumerate(parts):
            if index % 2:
                phonemes.extend(_block_phonemes(parts, index))
            elif part:
                part = self._run_stages(part, stages)
                read = self.backend.phonemize_to_list(part, stages.lang)
                self._check_read(part, read, stages)
                phonemes.extend(read)
        return phonemes

    def prepare(self, text: str, stages: Stages = Stages(normalize=False)) -> str:
        """*text* after the stages, for an engine that reads text, not phonemes.

        The text is not split into sentences, and blocks stay as written.
        """
        stages = self._resolve(stages)
        parts = _split_blocks(text)
        return "".join(part if index % 2 or not part else self._run_stages(part, stages)
                       for index, part in enumerate(parts))

    def identity(self) -> PhonemizerIdentity:
        """What phonemizes this frontend's language."""
        return self.backend.identity(self._resolve(None).lang)

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
        resolved ``diacritize`` is ``False`` when the backend owns the stage.
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
            normalize=normalize is not False,
            diacritize=enabled and "diacritize" not in self.backend.owned_stages,
            diacritizer_model=stages.diacritizer_model or own.diacritizer_model,
            lang=lang,
            casing=stages.casing or own.casing,
        )

    def _sentences(self, text: str, stages: Stages) -> Iterator[List[str]]:
        """Steps 2 to 6 on text with no block."""
        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError(
                "sentence chunking needs quebra-frases — install with "
                "`pip install scriptconv[phonemizers]`") from None
        for sentence in sentence_tokenize(text):
            if not sentence.strip():
                continue
            sentence = self._run_stages(sentence, stages)
            chunks = [list(chunk) for chunk in self.backend.phonemize_lazy(sentence, stages.lang)]
            self._check_read(sentence, [p for chunk in chunks for p in chunk], stages)
            yield from (chunk for chunk in chunks if chunk)

    def _run_stages(self, text: str, stages: Stages) -> str:
        """Steps 3 to 5 on one piece of text."""
        if stages.normalize and self.config.normalizer is not None:
            text = self._stage("normalize", stages, self.config.normalizer, text, stages.lang)
        if stages.casing is not None:
            text = self._stage("casing", stages, stages.casing, text)
        if stages.diacritize:
            text = self._stage("diacritize", stages, diacritize, text, stages.lang,
                               diacritizer_model=stages.diacritizer_model)
        return text

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
