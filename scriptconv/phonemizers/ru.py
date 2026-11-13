"""Russian phonemizers.

Currently one backend: the Vosk-TTS front-end, wrapping the vendored
:mod:`scriptconv.phonemizers._thirdparty.vosk_g2p` rules so the alphacep
Russian voices can be driven from text without the ``vosk-tts`` package.
"""
import re
from typing import Dict, Iterator, List, Optional

from quebra_frases import sentence_tokenize

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizedChunks
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers._thirdparty.vosk_g2p import convert, load_pronunciations, vowels

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

    A stress-marked word (``сег+одня``) is where it differs from ``vosk_tts``,
    which never finds such a word in the dictionary.  Here the word is looked
    up without its marks, and a dictionary pronunciation is used when it
    stresses each marked vowel.  For a homograph the mark picks the entry, so
    ``з+амок`` and ``зам+ок`` read differently.  When no entry stresses the
    marked vowels, the rules read the marks.

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
    # The diacritize stage (stressonnx) writes a combining acute (U+0301) after
    # the stressed vowel. The vosk rules read a "+" before it instead, so the
    # acute becomes a "+", and a "+" already there is kept once. An acute after
    # any other character marks no vowel and is dropped.
    _ACUTE = "\u0301"
    _ACUTE_STRESS = re.compile(r"\+?([" + "".join(vowels) + "])" + _ACUTE)
    # One match per vowel letter, with the "+" marks before it.
    _MARKED_VOWEL = re.compile(r"\+*[" + "".join(vowels) + "]")

    def __init__(self, alphabet: Alphabet = Alphabet.VOSK,
                 model: Optional[str] = None):
        if alphabet != Alphabet.VOSK:
            raise ValueError(
                "VoskPhonemizer emits the vosk-tts phoneme inventory, not "
                f"{Alphabet(alphabet).value!r} — use Alphabet.VOSK")
        self._dict_path = model
        self._dictionary: Optional[dict] = None  # lazy: dictionaries are large
        self._variants: Dict[str, List[List[str]]] = {}
        super().__init__(alphabet)

    @property
    def dictionary(self) -> dict:
        """The loaded ``word -> [phoneme, …]`` map (empty without a path)."""
        if self._dictionary is None:
            self._dictionary, self._variants = load_pronunciations(self._dict_path)
        return self._dictionary

    def _stressed_entry(self, word: str) -> Optional[List[str]]:
        """The dictionary pronunciation of a ``+``-marked word that agrees
        with its marks, or None.

        The k-th vowel letter of the word is the k-th vowel phoneme of an entry
        (vowel phonemes end in their stress digit), so an entry whose vowel
        count differs from the word's never matches.  An entry that stresses
        exactly the marked vowels wins; otherwise the most probable entry that
        stresses each marked vowel, as a compound with a second stress does.
        """
        plain = word.replace("+", "")
        if plain not in self.dictionary:
            return None
        marks = [v.startswith("+") for v in self._MARKED_VOWEL.findall(word)]
        if not any(marks):
            return None
        fallback = None
        for phones in self._variants.get(plain, [self.dictionary[plain]]):
            stress = [p.endswith("1") for p in phones if p[-1] in "01"]
            if len(stress) != len(marks) or not all(s for s, m in zip(stress, marks) if m):
                continue
            if stress == marks:
                return phones
            fallback = fallback or phones
        return fallback

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ru-RU"])

    def _g2p_tokens(self, text: str) -> List[str]:
        """Word/punctuation stream -> Vosk phoneme tokens (no BOS/EOS/blanks)."""
        tokens: List[str] = []
        # the em dash is a pause, and vosk only knows the ASCII hyphen
        text = text.replace("—", "-").lower()
        text = self._ACUTE_STRESS.sub(r"+\1", text).replace(self._ACUTE, "")
        for word in self._SPLIT.split(text):
            if word == "":
                continue
            if self._SPLIT.match(word) or word == "-":
                # space or punctuation: kept verbatim as a pause token
                tokens.append(word)
            elif word in self.dictionary:
                tokens.extend(self.dictionary[word])
            elif "+" in word and (phones := self._stressed_entry(word)):
                tokens.extend(phones)
            else:
                tokens.extend(convert(word).split())
        return tokens

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """Sentence-level lists of Vosk phoneme tokens, one sentence at a time.

        Punctuation is preserved (it drives pausing); each sentence becomes one
        synthesis chunk.  Multi-character tokens (``sch``, ``bj``, ``a1``) stay
        whole, so :meth:`BasePhonemizer.phonemize_lazy`'s per-character split of
        the phoneme *string* is deliberately bypassed — splitting ``s h`` into
        characters would later fold back into ``sh`` (ш), a different phoneme.
        """
        self.get_lang(lang)
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        for sentence in sentence_tokenize(text):
            tokens = self._g2p_tokens(sentence)
            if tokens:
                yield tokens

    def phonemize(self, text: str, lang: str) -> PhonemizedChunks:
        """Sentence-level lists of Vosk phoneme tokens."""
        return list(self.phonemize_lazy(text, lang))

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        self.get_lang(lang)
        return self._g2p_tokens(text.lower())

    def phonemize_string(self, text: str, lang: str) -> str:
        return " ".join(self.phonemize_to_list(text, lang))
