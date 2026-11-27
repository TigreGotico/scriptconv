from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer


class PhonikudPhonemizer(BasePhonemizer):
    engine_distribution = "phonikud"

    def __init__(self):
        try:
            from phonikud import phonemize
        except ImportError as e:
            raise ImportError(
                "phonikud is required for the Hebrew phonemizer. "
                "Install it with 'pip install phonikud' "
                "(or 'pip install scriptconv[he]')."
            ) from e
        self.g2p = phonemize
        super().__init__(Alphabet.IPA)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """``he`` when *target_lang* matches Hebrew.

        Raises:
            ValueError: If the language code is unsupported.
        """
        return cls.match_lang(target_lang, ["he"])

    def phonemize_string(self, text: str, lang: str = "he") -> str:
        self.get_lang(lang)
        return self.g2p(text)
