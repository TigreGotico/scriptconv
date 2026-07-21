

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
    """KoG2P-backed Korean phonemizer — NOT distributable with scriptconv.

    Upstream KoG2P (github.com/scarletcho/KoG2P) is GPL-3.0, incompatible
    with this library's Apache-2.0 distribution, so the implementation is not
    vendored here.  Use :class:`G2PKPhonemizer` or the hangul2ipa-backed
    pipeline instead, or a GPL-compatible package that ships KoG2P itself.
    """

    def __init__(self, *args, **kwargs):
        raise ImportError(
            "KoG2P is GPL-3.0 and not vendored in scriptconv — use "
            "G2PKPhonemizer, or install a GPL-licensed distribution that "
            "provides it")

    def phonemize_string(self, text: str, lang: str) -> str:
        raise NotImplementedError
