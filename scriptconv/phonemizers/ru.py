"""Russian phonemizer for the alphacep Vosk-TTS voices.

It wraps the vendored :mod:`scriptconv.phonemizers._thirdparty.vosk_g2p` rules,
so the voices read text without the ``vosk-tts`` package.
"""
import re
from typing import Dict, Iterator, List, Optional

from quebra_frases import sentence_tokenize

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizedChunks
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers._thirdparty.vosk_g2p import convert, load_pronunciations, vowels

__all__ = ["VoskPhonemizer"]


class VoskPhonemizer(BasePhonemizer):
    """Russian text to the Vosk phoneme inventory (``a0``, ``bj``, ``sch`` …), as ``vosk_tts`` reads it.

    Each word comes from the voice's pronunciation ``dictionary``, else from
    the rules of :func:`~scriptconv.phonemizers._thirdparty.vosk_g2p.convert`.
    Spaces and punctuation stay as their own tokens, the pauses Vosk reads. The
    ``^`` and ``$`` markers and the blanks between phonemes belong to the
    consumer's tokenizer, so they are not emitted.

    Unlike ``vosk_tts``, a stress-marked word (``сег+одня``) is looked up
    without its marks, and a dictionary entry is used when it stresses each
    marked vowel, so ``з+амок`` and ``зам+ок`` read differently. When no entry
    agrees, the rules read the marks.

    Args:
        alphabet (Alphabet): must be :attr:`Alphabet.VOSK`.
        model (Optional[str]): path to the voice's ``dictionary`` file. Without
            it, only the rules are used. scriptconv never downloads it.
    """

    # The split of vosk_tts. The group keeps spaces and punctuation as pause tokens.
    _SPLIT = re.compile(r'([,.?!;:"() ])')
    # The diacritize stage (stressonnx) writes a combining acute (U+0301) after
    # the stressed vowel. The vosk rules read a "+" before it instead, so the
    # acute becomes a "+", and a "+" already there is kept once. An acute after
    # any other character marks no vowel and is dropped.
    _ACUTE = "\u0301"
    _ACUTE_STRESS = re.compile(r"\+?([" + "".join(vowels) + "])" + _ACUTE)
    # One match per vowel letter, with the "+" marks before it.
    _MARKED_VOWEL = re.compile(r"\+*[" + "".join(vowels) + "]")
    # scripts/probe_stress_marks.py: the mark moves the stress, and nothing else
    stress_mark_langs = frozenset({"ru"})

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
        """The dictionary pronunciation of a ``+``-marked word that agrees with its marks, or None.

        The k-th vowel letter is the k-th vowel phoneme of an entry (a vowel
        phoneme ends in its stress digit). An entry that stresses exactly the
        marked vowels wins, else the most probable entry that stresses each
        marked vowel, as a compound with a second stress does.
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
            if not word:
                continue
            if self._SPLIT.match(word) or word == "-":
                tokens.append(word)
            elif word in self.dictionary:
                tokens.extend(self.dictionary[word])
            elif "+" in word and (phones := self._stressed_entry(word)):
                tokens.extend(phones)
            else:
                tokens.extend(convert(word).split())
        return tokens

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """One list of Vosk phoneme tokens per sentence, with its punctuation.

        A token such as ``sch`` stays whole: the per-character split of
        :meth:`BasePhonemizer.phonemize_lazy` would turn ``s h`` into ``sh``
        (ш), a different phoneme.
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
