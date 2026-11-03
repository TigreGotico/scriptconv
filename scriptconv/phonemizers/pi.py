"""Pali phonemizer.

Pali in IAST (``ṃ`` or ``ṁ`` for niggahita) through the rule set that
``dhammagift/pali-tts`` feeds to Piper hi_IN voices.

This is a separate route from orthography2ipa, which also answers ``pi``. The
orthography2ipa spec describes Pali phonology. These rules emit the espeak-hi
inventory a Hindi voice was trained on, with a reduced ``ə`` for short ``a``
and a stress mark on the penult when it is heavy, else on the antepenult.
orthography2ipa stays the ``pi`` default; ask for
:data:`~Phonemizer.PALI_TTS` by name to get this string.
"""
import re
from typing import Iterator, List

from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers._vendored import pali_tts

# the clause symbols the rules emit (the values of pali_tts.PUNCT)
_CLAUSE_MARKS = re.compile(r" *[,.?!]+ *")


class PaliPhonemizer(BasePhonemizer):
    """Pali IAST to the IPA string a Piper voice of an Indic language reads.

    The rules are vendored under ``_vendored/pali_tts`` (MIT) and need nothing
    outside the standard library.

    ``profile`` is the espeak language of the target voice: each one knows only
    the symbols that language emits (``hi``, ``mr``, ``ur``, ``ne``, ``ml``,
    ``te``). ``full_a`` speaks short ``a`` as a full vowel instead of ``ə``,
    which the dhammagift server does for every voice because Hindi voices
    swallow ``ə``. ``final_m`` reads word-final niggahita as ``m`` instead of
    ``ŋ``. ``heavy_back`` lets a light antepenult yield its stress to a heavy
    syllable just before it. ``tune`` applies the respellings measured by ear
    on the ``hi_IN-pratham`` voice; they make the string worse for any other
    voice.

    The rules drop a character they have no rule for, digits included, as
    upstream does. Normalize numbers before phonemizing.

    The rules read punctuation: an ellipsis around ``pe`` expands to
    ``peyyāla``, a comma blocks the long-``o`` and hiatus respellings, and a
    quote splits a quotative ``ti`` from its word. So every path hands the
    rules the raw sentence. :attr:`keep_punctuation` decides only whether the
    clause symbols stay in the output; with it on, :meth:`phonemize_string`
    returns the upstream string unchanged.
    """

    _LANGS: List[str] = ["pi"]
    PROFILES: List[str] = list(pali_tts.PROFILES)

    def __init__(self, profile: str = "hi", stress: bool = True,
                 full_a: bool = False, final_m: bool = False,
                 heavy_back: bool = True, tune: bool = False):
        super().__init__(Alphabet.IPA)
        if profile not in pali_tts.PROFILES:
            raise ValueError(f"unknown voice profile {profile!r}; "
                             f"supported profiles are {self.PROFILES}")
        self.profile = profile
        self.stress = stress
        self.full_a = full_a
        self.final_m = final_m
        self.heavy_back = heavy_back
        self.tune = tune

    @classmethod
    def supported_langs(cls) -> List[str]:
        return list(cls._LANGS)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """Validate *target_lang* against the one language these rules cover.

        Raises:
            ValueError: if the language code is not Pali.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def phonemize_string(self, text: str, lang: str = "pi") -> str:
        self.get_lang(lang)
        ipa = pali_tts.to_ipa(text, stress=self.stress, full_a=self.full_a,
                              final_m=self.final_m, lang=self.profile,
                              heavy_back=self.heavy_back)
        if self.tune:
            ipa = pali_tts.tune(ipa)
        if self.keep_punctuation:
            return ipa
        return _CLAUSE_MARKS.sub(" ", ipa).strip()

    def phonemize_lazy(self, text: str, lang: str = "pi") -> Iterator[List[str]]:
        """One phoneme list per sentence, the rules run on the raw sentence."""
        if text and self.normalizer is not None:
            text = self.normalizer(text, lang)
        return self._sentences(text, lang)

    def phonemize_to_list(self, text: str, lang: str = "pi") -> List[str]:
        """The sentences of :meth:`phonemize_lazy`, joined, without normalization."""
        return [p for sentence in self._sentences(text, lang) for p in sentence]

    def _sentences(self, text: str, lang: str) -> Iterator[List[str]]:
        if not text:
            return
        from quebra_frases import sentence_tokenize
        for sentence in sentence_tokenize(text):
            phonemes = self.phonemize_string(sentence, lang)
            if phonemes:
                yield list(phonemes)
