

from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers._thirdparty.hangul2ipa import hangul2ipa
from scriptconv.phonemizers.enums import Alphabet


class G2PKPhonemizer(BasePhonemizer):

    def __init__(self, descriptive=True, group_vowels=True, to_syl=True,
                 alphabet=Alphabet.IPA):
        assert alphabet in [Alphabet.IPA, Alphabet.HANGUL]
        try:
            from g2pk import G2p
        except ImportError as e:
            raise ImportError(
                "g2pk is required for the G2PK phonemizer. "
                "Install it with 'pip install g2pk' "
                "(or 'pip install scriptconv[ko]')."
            ) from e
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

    Uses an externally-installed ``kog2p`` when present, otherwise the
    quarantined vendored copy under ``_vendored/kog2p`` — GPL-3.0 under its
    own license, NOT this library's Apache-2.0.  Never selected
    automatically; :class:`G2PKPhonemizer` is the unencumbered default.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        super().__init__(alphabet)
        try:
            # an externally-installed kog2p distribution wins
            from kog2p import runKoG2P
        except ImportError:
            # quarantined vendored copy, GPL-3.0 under its own license
            # (see _vendored/kog2p/LICENSE.md); explicit opt-in by
            # requesting this phonemizer
            from scriptconv.phonemizers._vendored.kog2p import runKoG2P
        self.g2p = runKoG2P

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ko"])

    def phonemize_string(self, text: str, lang: str) -> str:
        # contract: the installed module's runKoG2P(text) -> phoneme string
        return self.g2p(text)
