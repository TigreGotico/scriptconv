"""Liberian English (Kolokwa) phonemizer: kolokwa-g2p.

kolokwa-g2p (michsethowusu/kolokwa-g2p, MIT) is a Forward Transformer of the
``phonemize`` package with a pronouncing dictionary of its training words. Its
ONNX export comes from the Hugging Face Hub, from :data:`MODEL_REPO` at
:data:`MODEL_REVISION`, into the shared Hugging Face cache. Each file must have
its pinned sha256. Offline, with no cached copy that passes the check, the
backend raises :class:`~scriptconv.phonemizers.base.ModelUnavailableError`.

The text reads as ``phonemize`` 0.2.4 ``Phonemizer.__call__`` reads it: drop
the characters that are neither alphanumeric nor punctuation, split at spaces
and punctuation, look each word up in the dictionary, else split it at hyphens
and before inner capitals, and predict each part that is not in the dictionary.
"""
import dataclasses
import json
import re
from typing import Optional

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizerIdentity
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.g2pw import _hub_file

__all__ = ["KolokwaPhonemizer", "MODEL_REPO", "MODEL_REVISION", "MODEL_FILES"]

MODEL_REPO = "TigreGotico/kolokwa-g2p-onnx"
MODEL_REVISION = "3729a707e532ba2929c884288bacf5d5d76f7316"
#: path in :data:`MODEL_REPO` -> sha256
MODEL_FILES = {
    "model.onnx": "bf93add9810693828f06485a7f898964bfeb6734e7474935525504a54555b81a",
    "kolokwa.json": "1900134a91e15c405f43360bb8b7adc5ae64bc0bd2a58ddf01516eb9730b77a2",
}

# phonemize's DEFAULT_PUNCTUATION; a space and a hyphen also stay in the text
PUNCTUATION = "().,:?!/–"
_KEPT = set(PUNCTUATION + "- ")
_SPLIT = re.compile(f"([{PUNCTUATION} ])")
# The exported graph reuses a 5000-id buffer. Two ids bound the letters.
_MAX_MODEL_IDS = 5000


def _split_capitals(word: str) -> str:
    """*word* with a hyphen before each capital that does not start a hyphenated part."""
    return "-".join("".join("-" + c if i and c.isupper() else c for i, c in enumerate(part))
                    for part in word.split("-"))


class KolokwaPhonemizer(BasePhonemizer):
    """Liberian English (``lir``) text to IPA with kolokwa-g2p."""

    def __init__(self):
        try:
            import onnxruntime
        except ImportError as e:
            raise ImportError(
                "numpy, onnxruntime and huggingface_hub are required for the Kolokwa "
                "phonemizer. Install them with 'pip install scriptconv[lir]'."
            ) from e
        super().__init__(Alphabet.IPA)
        paths = {name: _hub_file(MODEL_REPO, "model", name, MODEL_REVISION, sha256)
                 for name, sha256 in MODEL_FILES.items()}
        with open(paths["kolokwa.json"], encoding="utf-8") as f:
            tables = json.load(f)
        self.session = onnxruntime.InferenceSession(paths["model.onnx"], providers=["CPUExecutionProvider"])
        self.dictionary = tables["dictionary"]
        self.char_repeats = tables["char_repeats"]
        self.text_tokens = tables["text_tokens"]
        self.text_start = tables["text_start"]
        self.text_end = tables["text_end"]
        self.phonemes = tables["phoneme_tokens"]
        self.phoneme_end = tables["phoneme_end"]
        self.special = set(tables["phoneme_special"])

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """``"en_lr"``, the model key of Liberian English; raises ValueError when *target_lang* is not close to ``lir``."""
        cls.match_lang(target_lang, ["lir"])
        return "en_lr"

    def phonemize_string(self, text: str, lang: str = "lir") -> str:
        self.get_lang(lang)
        text = "".join(c for c in text if c.isalnum() or c in _KEPT)
        return "".join(self._read(word) for word in _SPLIT.split(text) if word)

    def _lookup(self, word: str) -> Optional[str]:
        if not word or word in _KEPT:
            return word
        for form in (word, word.lower(), word.title()):
            if form in self.dictionary:
                return self.dictionary[form]
        return None

    def _read(self, word: str) -> str:
        found = self._lookup(word)
        if found is not None:
            return found
        parts = re.split(r"(-)", _split_capitals(word))
        if len(parts) == 1:
            return self._predict(word)
        return "".join(map(self._read, parts))

    def _predict(self, word: str) -> str:
        """The model's phonemes for *word*: the most likely symbol at each
        position, without padding and repeats, up to the end symbol."""
        import numpy as np

        letters = [self.text_tokens[c.lower()] for c in word if c.lower() in self.text_tokens]
        if not letters:
            return ""
        max_letters = (_MAX_MODEL_IDS - 2) // self.char_repeats
        if len(letters) > max_letters:
            raise ValueError(
                f"Kolokwa reads at most {max_letters} letters in one spelling, "
                f"got {len(letters)}")
        ids = [self.text_start] + [i for i in letters for _ in range(self.char_repeats)] + [self.text_end]
        logits = self.session.run(None, {"text": np.array([ids], dtype=np.int64)})[0][0]
        best = [int(i) for i in logits.argmax(-1) if i != 0]
        symbols = []
        for i, token in enumerate(best):
            if i and token == best[i - 1]:
                continue
            symbols.append(token)
            if token == self.phoneme_end:
                break
        return "".join(self.phonemes[t] for t in symbols if self.phonemes[t] not in self.special)

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the hash of the code on the
        path of this backend, as
        :func:`~scriptconv.phonemizers._revision.code_revision` gives it. That
        code holds the pinned model revision and the sha256 of each model file."""
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        return dataclasses.replace(identity, revision=code_revision(self, identity.lang, {}))
