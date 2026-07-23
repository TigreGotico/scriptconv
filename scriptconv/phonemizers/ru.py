"""Russian phonemizers.

Currently one backend: the Vosk-TTS front-end, wrapping the vendored
:mod:`scriptconv.phonemizers._thirdparty.vosk_g2p` rules so the alphacep
Russian voices can be driven from text without the ``vosk-tts`` package.
"""
import re
from typing import List, Optional

from quebra_frases import sentence_tokenize

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizedChunks
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers._thirdparty.vosk_g2p import convert, load_dictionary

__all__ = ["VoskPhonemizer"]


class VoskPhonemizer(BasePhonemizer):
    """
    Russian phonemizer for the Vosk-TTS voices (alphacep).

    It reproduces ``vosk_tts``'s grapheme-to-phoneme exactly: each word is
    looked up in the voice's pronunciation ``dictionary`` (word -> phonemes),
    falling back to the rule-based
    :func:`~scriptconv.phonemizers._thirdparty.vosk_g2p.convert` for
    out-of-dictionary words.  Spaces and punctuation are kept as their own
    tokens (Vosk feeds them to the model as short/long pauses); the BOS ``^`` /
    EOS ``$`` markers and the inter-phoneme blanks belong to the consumer's
    tokenizer, so they are *not* emitted here.

    The output is the Vosk phoneme inventory (``a0``, ``bj``, ``sch`` …), not
    IPA, so the only supported alphabet is :attr:`Alphabet.VOSK` — like
    Cotovía, this backend is eligible only when its own notation is requested.

    The dictionary is optional: without it the rules alone still produce usable
    Russian (only the curated stress and exception entries are lost).
    scriptconv never downloads anything — the caller resolves the file and
    passes its path as ``model`` (the registry's ``phonemizer_model`` knob).

    Args:
        alphabet (Alphabet): must be :attr:`Alphabet.VOSK`.
        model (Optional[str]): path to the voice's ``dictionary`` file.  When
            absent or missing, only the rule-based fallback is used.
    """

    # Matches the per-character split used by vosk_tts: spaces and punctuation
    # are captured so they survive as standalone pause tokens.
    _SPLIT = re.compile(r'([,.?!;:"() ])')

    def __init__(self, alphabet: Alphabet = Alphabet.VOSK,
                 model: Optional[str] = None):
        if alphabet != Alphabet.VOSK:
            raise ValueError(
                "VoskPhonemizer emits the vosk-tts phoneme inventory, not "
                f"{Alphabet(alphabet).value!r} — use Alphabet.VOSK")
        self._dict_path = model
        self._dictionary: Optional[dict] = None  # lazy: dictionaries are large
        super().__init__(alphabet)

    @property
    def dictionary(self) -> dict:
        """The loaded ``word -> [phoneme, …]`` map (empty without a path)."""
        if self._dictionary is None:
            self._dictionary = load_dictionary(self._dict_path)
        return self._dictionary

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ru-RU"])

    def _g2p_tokens(self, text: str) -> List[str]:
        """Word/punctuation stream -> Vosk phoneme tokens (no BOS/EOS/blanks)."""
        tokens: List[str] = []
        # the em dash is a pause, and vosk only knows the ASCII hyphen
        text = text.replace("—", "-")
        for word in self._SPLIT.split(text.lower()):
            if word == "":
                continue
            if self._SPLIT.match(word) or word == "-":
                # space or punctuation: kept verbatim as a pause token
                tokens.append(word)
            elif word in self.dictionary:
                tokens.extend(self.dictionary[word])
            else:
                tokens.extend(convert(word).split())
        return tokens

    def phonemize(self, text: str, lang: str) -> PhonemizedChunks:
        """Sentence-level lists of Vosk phoneme tokens.

        Punctuation is preserved (it drives pausing); each sentence becomes one
        synthesis chunk.  Multi-character tokens (``sch``, ``bj``, ``a1``) stay
        whole, so :meth:`BasePhonemizer.phonemize`'s per-character split is
        deliberately bypassed.
        """
        self.get_lang(lang)
        if not text:
            return []
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        results: PhonemizedChunks = []
        for sentence in sentence_tokenize(text):
            tokens = self._g2p_tokens(sentence)
            if tokens:
                results.append(tokens)
        return results

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        self.get_lang(lang)
        return self._g2p_tokens(text.lower())

    def phonemize_string(self, text: str, lang: str) -> str:
        return " ".join(self.phonemize_to_list(text, lang))
