"""Berber phonemizers.

Kabyle (``kab``) through the rule set that ``agbalu/Matoub-82M`` was fitted on.

This is deliberately a separate route from :class:`AfricaG2PPhonemizer`, which
also answers ``kab``. The two are different phonemizers and their output
differs, so they are not interchangeable:

===============  ===========================  ==============
text             africa-g2p                   Matoub
===============  ===========================  ==============
``taddart``      ``t a ð ð a r t``            ``θædːærθ``
``ameqqran``     ``a m ə q q r a n``          ``æməqːræn``
``aqcic``        ``a q ʃ i ʃ``                ``ɑqʃiʃ``
===============  ===========================  ==============

africa-g2p does not spirantise the initial ``t``, writes gemination as a
doubled symbol rather than length, and does not back ``/a/`` beside a backing
consonant. A caller driving Matoub-82M needs the Matoub string: the other one
carries symbols that model has no embedding row for.
"""
from typing import List

from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet


class MatoubKabylePhonemizer(BasePhonemizer):
    """Kabyle Latin orthography to the IPA string ``agbalu/Matoub-82M`` reads.

    The rules are vendored under ``_vendored/matoub_kab`` (Apache-2.0, the same
    licence as this repository) and need nothing outside the standard library.

    The rules raise on a character they have no rule for, and that is kept on
    purpose. The upstream file records that silent deletion already cost three
    Kabyle consonants once, so an unknown symbol is reported rather than
    dropped.
    """

    _LANGS: List[str] = ["kab"]

    def __init__(self):
        super().__init__(Alphabet.IPA)

    @classmethod
    def supported_langs(cls) -> List[str]:
        return list(cls._LANGS)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """Validate *target_lang* against the one language these rules cover.

        Raises:
            ValueError: if the language code is not Kabyle.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def phonemize_string(self, text: str, lang: str = "kab") -> str:
        self.get_lang(lang)
        from scriptconv.phonemizers._vendored.matoub_kab import phonemize

        return phonemize(text)
