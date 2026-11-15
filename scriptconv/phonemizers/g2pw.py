"""Mandarin pinyin symbols from the g2pW polyphone model: ``Phonemizer.G2PW``.

g2pW (Chen et al., "g2pW: A Conditional Weighted Softmax BERT for Polyphone
Disambiguation in Mandarin", INTERSPEECH 2022) reads each polyphonic
character in the context of its sentence with a BERT model, and reads the
other characters from tables. :mod:`scriptconv.phonemizers._thirdparty.g2pw`
runs it on onnxruntime, with no torch.

The backend writes each syllable as three symbols: the pinyin initial, the
final and the tone digit 1 to 5. A syllable with no initial takes ``Ø``. The
final writes ü as ``v``. The symbols, the split of a syllable and the marks
that stay come from ``src/piper/phonemize_chinese.py`` of OHF-Voice/piper1-gpl
at commit d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, a file whose header says:
"Partially written by ChatGPT (December 2025). This code is Apache 2.0
licensed." These are :data:`PINYIN_INITIALS`, :data:`SYMBOLS`,
:func:`_normalize_syllable`, :func:`_split_syllable` and the loop of
:meth:`G2PWPhonemizer._sentence_symbols`.

The backend does not read digits. Numbers, dates and units are the
normalisation stage, which the caller runs before the backend. A digit gives
no symbol.

The model files come from the Hugging Face Hub at a fixed revision, into the
shared Hugging Face cache:

- ``g2pw.tar.gz`` of the dataset rhasspy/piper-checkpoints (MIT, as its card
  states): the g2pW ONNX model, ``config.py`` and the polyphonic and
  monophonic character lists. The weights are those of g2pW (Apache-2.0,
  https://huggingface.co/YC-Chen/g2pW).
- ``tokenizer.json`` of google-bert/bert-base-chinese (Apache-2.0).

Offline, with no cached copy, the backend raises
:class:`~scriptconv.phonemizers.base.ModelUnavailableError`.
"""
import ast
import os
import re
import tarfile
from typing import Iterator, List, Optional, Tuple

from quebra_frases import sentence_tokenize

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    ModelUnavailableError,
    PhonemizedChunks,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["G2PWPhonemizer", "PINYIN_INITIALS", "SYMBOLS"]

#: ``(repo_id, repo_type, filename, revision)`` of the g2pW model archive.
MODEL_ARCHIVE = ("rhasspy/piper-checkpoints", "dataset", "zh/zh_CN/_resources/g2pw.tar.gz",
                 "581dcfb1856912507627724d4ab2817a20e889ca")
#: ``(repo_id, repo_type, filename, revision)`` of the bert-base-chinese tokenizer.
TOKENIZER = ("google-bert/bert-base-chinese", "model", "tokenizer.json",
             "8f23c25b06e129b6c986331a13d8d025a92cf0ea")

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


def _hub_file(repo_id: str, repo_type: str, filename: str, revision: str) -> str:
    """The local path of a file of the Hub, downloaded into the shared cache if needed."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        return hf_hub_download(repo_id, filename, repo_type=repo_type, revision=revision)
    except LocalEntryNotFoundError as e:
        raise ModelUnavailableError(
            f"{repo_id}/{filename} at revision {revision} is not in the Hugging Face "
            f"cache and cannot be downloaded: {e}") from e


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
        """The symbols of one sentence."""
        symbols: List[str] = []
        for syllable, char in zip(self.converter(sentence)[0], sentence):
            if syllable is None:
                if char in _KEPT:
                    symbols.append(char)
                continue
            syllable = _normalize_syllable(syllable)
            initial, final, tone = _split_syllable(syllable)
            if not final:
                symbols.append(syllable)
                continue
            symbols += [initial or "Ø", final, tone]
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
