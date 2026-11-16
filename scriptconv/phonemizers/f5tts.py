"""The text tokens of the F5-TTS voices: the text as written, marks included.

An F5-TTS voice reads text tokens from a vocabulary of characters, so its
input contract is the text itself, with its capitals, quotes and every mark.
Its inference code maps each token through ``vocab.txt`` and gives id 0 to a
token that the vocabulary lacks. Two text functions exist upstream:

- SWivid/F5-TTS at commit 600e5fd runs ``convert_char_to_pinyin``
  (``src/f5_tts/model/utils.py``) on the reference and generation text in
  ``infer_batch_process`` (``src/f5_tts/infer/utils_infer.py``). It turns each
  hanzi into a pinyin syllable and keeps every other character.
  F5-TTS v1 Base and the fine-tunes that run its inference code read these
  tokens. :class:`F5TTSPinyinPhonemizer` gives them, from the port in
  :mod:`scriptconv.phonemizers._thirdparty.f5tts`.
- SWivid/Habibi-TTS at commit 9274498 and silma-ai/silma-tts at commit
  2816b5a pass the text string as it is (``infer_batch_process`` in
  ``src/habibi_tts/infer/utils_infer.py`` and
  ``src/silma_tts/infer/utils_infer.py``), so each character is one token.
  :class:`F5TTSCharPhonemizer` gives them.

The tokens keep the marks of the text, so these backends read each sentence
whole and override :meth:`phonemize_lazy`, as the frontend contract asks of a
backend that needs the characters ``remove_punctuation`` drops. The frontend
therefore appends no clause symbol, and ``keep_punctuation`` changes nothing.
The text arrives normalised: neither backend owns ``normalize``.
"""
from typing import Iterator, List

from scriptconv.phonemizers.base import BasePhonemizer, Segment, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["F5TTSCharPhonemizer", "F5TTSPinyinPhonemizer"]


class F5TTSCharPhonemizer(BasePhonemizer):
    """One token for each character of the text, as Habibi-TTS and SILMA TTS read it.

    The backend takes any language, because the voice's vocabulary decides
    which characters it reads.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.UNICODE):
        _check_alphabet(self, alphabet, [Alphabet.UNICODE])
        super().__init__(alphabet)

    def text_tokens(self, text: str) -> List[str]:
        """The tokens of *text*."""
        return list(text)

    def reads_stress_mark(self, lang: str) -> bool:
        """The tokens are the text as written, so a stress mark stays a token, in every language."""
        return True

    def phonemize_string(self, text: str, lang: str) -> str:
        return "".join(self.text_tokens(text))

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        return self.text_tokens(text)

    def phonemize_lazy(self, text: str, lang: str) -> Iterator[List[str]]:
        """The tokens of each sentence of *text*, one sentence at a time, marks included."""
        if not text:
            return
        if self.normalizer is not None:
            text = self.normalizer(text, lang)
        try:
            from quebra_frases import sentence_tokenize
        except ImportError:
            raise ImportError("sentence chunking needs quebra-frases — install with "
                              "`pip install scriptconv[phonemizers]`") from None
        for sentence in sentence_tokenize(text):
            if tokens := self.text_tokens(sentence):
                yield tokens

    def mark_symbols(self, marks: str) -> Segment:
        """The tokens of *marks*: the marks are tokens of their own, as the text writes them."""
        return Segment(tuple(self.text_tokens(marks)))


class F5TTSPinyinPhonemizer(F5TTSCharPhonemizer):
    """The tokens of F5-TTS ``convert_char_to_pinyin``: a pinyin syllable for each hanzi, every other character as itself.

    rjieba segments the text. Each hanzi gives a space and its pinyin syllable
    in the TONE3 style of pypinyin, with tone sandhi. A ``;`` becomes ``,``
    and curly quotes become straight quotes. A segment of ASCII characters
    with more than one character follows a space, unless the token before it
    is a space, ``:``, ``'`` or ``"``.
    """

    engine_distribution = "pypinyin"

    def __init__(self, alphabet: Alphabet = Alphabet.UNICODE):
        try:
            import rjieba  # noqa: F401
            import pypinyin  # noqa: F401
        except ImportError:
            raise ImportError("the F5-TTS pinyin tokens need rjieba and pypinyin — install with "
                              "`pip install scriptconv[zh-phonemizers]`") from None
        super().__init__(alphabet)

    def text_tokens(self, text: str) -> List[str]:
        from scriptconv.phonemizers._thirdparty.f5tts import convert_char_to_pinyin
        return convert_char_to_pinyin(text)
