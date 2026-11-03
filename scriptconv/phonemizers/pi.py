"""Pali phonemizer.

Pali in IAST (``ṃ`` or ``ṁ`` for niggahita) through the rule set that
``dhammagift/pali-tts`` feeds to Piper hi_IN voices.

This is a separate route from orthography2ipa, which also answers ``pi``. The
orthography2ipa spec describes Pali phonology. These rules emit the espeak-hi
inventory a Hindi voice was trained on, with a reduced ``ə`` for short ``a``
and a stress mark on the syllable a Hindi reader would stress. orthography2ipa
stays the ``pi`` default; ask for :data:`~Phonemizer.PALI_TTS` by name to get
this string.
"""
from typing import List

from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers._vendored import pali_tts


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
        return pali_tts.tune(ipa) if self.tune else ipa
