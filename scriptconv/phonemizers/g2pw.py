"""Mandarin pinyin symbols from the g2pW polyphone model: ``Phonemizer.G2PW``.

g2pW (Chen et al., "g2pW: A Conditional Weighted Softmax BERT for Polyphone
Disambiguation in Mandarin", INTERSPEECH 2022) reads each polyphonic
character in the context of its sentence with a BERT model, and reads the
other characters from tables. :mod:`scriptconv.phonemizers._thirdparty.g2pw`
runs it on onnxruntime, with no torch.

The backend writes a syllable as three symbols: the Hanyu Pinyin initial
(ISO 7098), the final and the tone digit 1 to 5. A syllable with no initial
takes ``Ø``. The final writes ü as ``v``, as the g2pW reading table
``bopomofo_to_pinyin_wo_tune_dict.json`` does. Five rows of that table do not
split into an initial and a final of :data:`SYMBOLS`. ``n`` and ``ê`` give
one symbol, the syllable with its tone digit, such as ``n2``. ``hm``, ``hng``
and ``ng`` give three symbols, ``h m``, ``h ng`` or ``n g`` and the tone
digit, and ``m``, ``ng`` and ``g`` are not finals.

The backend does not read digits. Numbers, dates and units are the
normalisation stage, which the caller runs before the backend. A digit gives
no symbol: the backend logs a warning that names it, or raises
:class:`~scriptconv.phonemizers.base.UnreadTextError` when
:attr:`~scriptconv.phonemizers.base.BasePhonemizer.strict` is set.

The model files come from the Hugging Face Hub at a fixed revision, into the
shared Hugging Face cache:

- ``g2pw.tar.gz`` of the dataset rhasspy/piper-checkpoints (MIT, as its card
  states): the g2pW ONNX model, ``config.py`` and the polyphonic and
  monophonic character lists. The weights are those of g2pW (Apache-2.0,
  https://huggingface.co/YC-Chen/g2pW).
- ``tokenizer.json`` of google-bert/bert-base-chinese (Apache-2.0).

Each file must have its pinned sha256. A cached file with another sha256 is
downloaded again once. Offline, with no cached copy or with no copy that
passes the check, the backend raises
:class:`~scriptconv.phonemizers.base.ModelUnavailableError`.
"""
import ast
import hashlib
import logging
import os
import re
import tarfile
from typing import Iterator, List, Optional, Tuple

from quebra_frases import sentence_tokenize

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    ModelUnavailableError,
    PhonemizedChunks,
    UnreadTextError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["G2PWPhonemizer", "PINYIN_INITIALS", "SYMBOLS"]

LOG = logging.getLogger(__name__)

#: ``(repo_id, repo_type, filename, revision, sha256)`` of the g2pW model archive.
MODEL_ARCHIVE = ("rhasspy/piper-checkpoints", "dataset", "zh/zh_CN/_resources/g2pw.tar.gz",
                 "581dcfb1856912507627724d4ab2817a20e889ca",
                 "252c6f561c11014fbb243d70aec993a816d82109887b91edcda0261ab9967060")
#: ``(repo_id, repo_type, filename, revision, sha256)`` of the bert-base-chinese tokenizer.
TOKENIZER = ("google-bert/bert-base-chinese", "model", "tokenizer.json",
             "8f23c25b06e129b6c986331a13d8d025a92cf0ea",
             "55c5edcfb8936895e019b2d8f97dcb547734f25b29f95009155f4c8c15649aae")

#: The pinyin initials, longest first, so that ``zh`` matches before ``z``.
PINYIN_INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k",
                   "h", "j", "q", "x", "r", "z", "c", "s", "y", "w")

#: Every symbol of the inventory: the initials and ``Ø``, the finals, the
#: tones, and the marks of a pause.
SYMBOLS = (
    ("Ø",) + PINYIN_INITIALS
    + ("a", "o", "e", "ai", "ei", "ao", "ou", "an", "en", "ang", "eng", "ong",
       "i", "ia", "ie", "iao", "iu", "ian", "in", "iang", "ing", "iong",
       "u", "ua", "uo", "uai", "ui", "uan", "un", "uang", "ueng",
       "v", "ve", "van", "vn", "er", "ue")
    + ("1", "2", "3", "4", "5")
    + ("。", ".", "？", "?", "！", "!", "—", "…", "、", "，", ",", "：", ":", "；", ";", " ")
)

# A character with no reading stays when it is one symbol of the inventory
# and not a digit: a digit with no reading is unread text, not a tone.
_KEPT = frozenset(symbol for symbol in SYMBOLS if len(symbol) == 1 and not symbol.isdigit())
_QUOTES = re.compile('[“”"]')
_SYLLABLE = re.compile(r"^([a-züv:]+?)([1-5])$")
_PINYIN = re.compile(r"^([a-zvü]+?)([1-5])$")
_MODEL_FILES = ("g2pw.onnx", "config.py", "POLYPHONIC_CHARS.txt", "MONOPHONIC_CHARS.txt")


def _normalize_syllable(syllable: str) -> str:
    """*syllable* with ü and ``u:`` written ``v``, when it is pinyin with a tone digit."""
    match = _SYLLABLE.match(syllable)
    if not match:
        return syllable
    return match.group(1).replace("u:", "v").replace("ü", "v") + match.group(2)


def _split_syllable(syllable: str) -> Tuple[str, str, Optional[str]]:
    """The initial, the final and the tone of *syllable*: ``hang2`` gives ``h``, ``ang``, ``2``.

    A syllable with no initial gives ``""`` for it. A syllable that is not
    pinyin with a tone digit gives ``("", "", None)``.
    """
    match = _PINYIN.match(syllable)
    if not match:
        return "", "", None
    base, tone = match.groups()
    initial = next((candidate for candidate in PINYIN_INITIALS if base.startswith(candidate)), "")
    return initial, base[len(initial):], tone


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hub_file(repo_id: str, repo_type: str, filename: str, revision: str, sha256: str) -> str:
    """The local path of a file of the Hub with the sha256 *sha256*, in the shared cache.

    The file is downloaded when it is not cached. A cached file with another
    sha256 is downloaded again once, unless the Hub is offline.

    Raises:
        ModelUnavailableError: If no copy with the sha256 is cached or can be downloaded.
    """
    from huggingface_hub import constants, hf_hub_download
    name = f"{repo_id}/{filename} at revision {revision}"

    def download(force: bool) -> str:
        try:
            return hf_hub_download(repo_id, filename, repo_type=repo_type, revision=revision,
                                   force_download=force)
        except Exception as e:
            raise ModelUnavailableError(f"{name} is not in the Hugging Face cache with "
                                        f"sha256 {sha256} and cannot be downloaded: {e}") from e

    path = download(force=False)
    digest = _sha256(path)
    if digest == sha256:
        return path
    cause = f"the cached file {path} has sha256 {digest}, not {sha256}"
    if constants.HF_HUB_OFFLINE:
        raise ModelUnavailableError(f"{name}: {cause}, and the Hugging Face Hub is offline")
    LOG.warning("%s: %s; downloading it again", name, cause)
    path = download(force=True)
    digest = _sha256(path)
    if digest != sha256:
        raise ModelUnavailableError(
            f"{name}: the downloaded file {path} has sha256 {digest}, not {sha256}")
    return path


def _model_config(source: str) -> dict:
    """The settings that ``config.py`` assigns, read without running it."""
    config = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            config[node.targets[0].id] = ast.literal_eval(node.value)
    return config


def _load_converter():
    """The g2pW converter with the pinned model and tokenizer."""
    try:
        import huggingface_hub  # noqa: F401
        import onnxruntime
        from tokenizers import Tokenizer

        from scriptconv.phonemizers._thirdparty.g2pw import DEFAULT_CONFIG, G2PWConverter
    except ImportError:
        raise ImportError(
            "g2pW phonemization needs onnxruntime, numpy, tokenizers and "
            "huggingface_hub — install with `pip install scriptconv[zh-phonemizers]`"
        ) from None
    files = {}
    with tarfile.open(_hub_file(*MODEL_ARCHIVE), "r:gz") as archive:
        for member in archive:
            name = os.path.basename(member.name)
            if member.isfile() and name in _MODEL_FILES:
                files[name] = archive.extractfile(member).read()
    tokenizer = Tokenizer.from_file(_hub_file(*TOKENIZER))
    # From tokenizers 1.0 a tokenizer encodes only once compiled.
    if hasattr(tokenizer, "compile"):
        tokenizer = tokenizer.compile()
    options = onnxruntime.SessionOptions()
    options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
    options.intra_op_num_threads = 2
    session = onnxruntime.InferenceSession(files["g2pw.onnx"], sess_options=options,
                                           providers=["CPUExecutionProvider"])
    config = _model_config(files["config.py"].decode("utf-8"))

    def pairs(name: str) -> List[List[str]]:
        return [line.split("\t") for line in files[name].decode("utf-8").strip().split("\n")]

    return G2PWConverter(session, tokenizer, pairs("POLYPHONIC_CHARS.txt"),
                         pairs("MONOPHONIC_CHARS.txt"),
                         {key: config[key] for key in DEFAULT_CONFIG if key in config})


class G2PWPhonemizer(BasePhonemizer):
    """Mandarin as pinyin initials, finals and tone digits, with g2pW reading the polyphones.

    Simplified and traditional characters both read. A mark that ends a
    clause or a sentence, and a space, stay as symbols (see :data:`SYMBOLS`),
    so the backend keeps its own punctuation and ignores
    :attr:`~BasePhonemizer.keep_punctuation`. A Latin letter that is a symbol,
    such as ``a`` or ``b``, also stays. The straight and curly double quotes
    are removed before the model reads the text.

    :meth:`phonemize_lazy` yields one list of symbols per sentence, as
    quebra-frases splits the text. :meth:`phonemize_string` joins the symbols
    with a space.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.PINYIN):
        _check_alphabet(self, alphabet, [Alphabet.PINYIN])
        super().__init__(alphabet)
        self.converter = _load_converter()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["zh"])

    def _sentence_symbols(self, sentence: str) -> List[str]:
        """The symbols of one sentence.

        A digit gives no symbol. The backend logs a warning that names the
        digits, or raises :class:`UnreadTextError` in strict mode.
        """
        symbols: List[str] = []
        unread: List[str] = []
        for syllable, char in zip(self.converter(sentence)[0], sentence):
            if syllable is None:
                if char in _KEPT:
                    symbols.append(char)
                elif char.isdigit():
                    unread.append(char)
                continue
            syllable = _normalize_syllable(syllable)
            initial, final, tone = _split_syllable(syllable)
            if not final:
                symbols.append(syllable)
                continue
            symbols += [initial or "Ø", final, tone]
        if unread:
            message = (f"g2pW reads no digit, so {''.join(unread)!r} of {sentence!r} gives no "
                       "symbol; numbers belong to the normalisation stage")
            if self.strict:
                raise UnreadTextError(message, tuple(unread))
            LOG.warning(message)
        return symbols

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """The symbols of each sentence of *text*, one sentence at a time.

        The ``normalizer`` hook runs first, when it is set. A sentence with no
        symbol is not yielded.
        """
        self.get_lang(lang)
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        for sentence in sentence_tokenize(_QUOTES.sub("", text)):
            symbols = self._sentence_symbols(sentence)
            if symbols:
                yield symbols

    def phonemize(self, text: str, lang: str) -> PhonemizedChunks:
        return list(self.phonemize_lazy(text, lang))

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        """The symbols of the sentences of *text* in one list, without the ``normalizer`` hook."""
        self.get_lang(lang)
        if not text:
            return []
        return [symbol for sentence in sentence_tokenize(_QUOTES.sub("", text))
                for symbol in self._sentence_symbols(sentence)]

    def phonemize_string(self, text: str, lang: str) -> str:
        return " ".join(self.phonemize_to_list(text, lang))
