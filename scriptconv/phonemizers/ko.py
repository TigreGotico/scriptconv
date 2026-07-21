

from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers._thirdparty.hangul2ipa import hangul2ipa
from scriptconv.phonemizers.enums import Alphabet


class G2PKPhonemizer(BasePhonemizer):

    def __init__(self, descriptive=True, group_vowels=True, to_syl=True,
                 alphabet=Alphabet.IPA):
        assert alphabet in [Alphabet.IPA, Alphabet.HANGUL]
        from g2pk import G2p
        self.g2p = G2p()
        self.descriptive = descriptive
        self.group_vowels = group_vowels
        self.to_syl = to_syl
        super().__init__(alphabet)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the closest supported language code.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: The validated language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        # this check is here only to throw an exception if invalid language is provided
        return cls.match_lang(target_lang, ["ko"])

    def phonemize_string(self, text: str, lang: str = "ko") -> str:
        """
        """
        lang = self.get_lang(lang)
        p = self.g2p(text, descriptive=self.descriptive,
                     group_vowels=self.group_vowels,
                     to_syl=self.to_syl)
        if self.alphabet == Alphabet.IPA:
            return hangul2ipa(p)
        return p


class KoG2PPhonemizer(BasePhonemizer):
    """Korean phonemizer wrapping an external ``kog2p`` distribution.

    Upstream KoG2P (github.com/scarletcho/KoG2P) is GPL-3.0 — a license
    incompatible with vendoring in this Apache-2.0 library, so a ``kog2p``
    module providing ``runKoG2P`` must be installed separately by a user who
    accepts its terms.  :class:`G2PKPhonemizer` is the unencumbered
    alternative.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        super().__init__(alphabet)
        try:
            from kog2p import runKoG2P
        except ImportError:
            raise ImportError(
                "no kog2p module installed (KoG2P is GPL-3.0 and not "
                "vendored here). Install a distribution providing it, "
                "accepting its license, or use G2PKPhonemizer") from None
        self.g2p = runKoG2P

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ko"])

    def phonemize_string(self, text: str, lang: str) -> str:
        # contract: the installed module's runKoG2P(text) -> phoneme string
        return self.g2p(text)
