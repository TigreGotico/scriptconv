from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet


class PersianPhonemizer(BasePhonemizer):
    """https://github.com/de-mh/persian_phonemizer"""
    def __init__(self, alphabet=Alphabet.IPA):
        try:
            from persian_phonemizer import Phonemizer
        except ImportError as e:
            raise ImportError(
                "persian_phonemizer is required for the Persian phonemizer. "
                "Install it with 'pip install persian_phonemizer' "
                "(or 'pip install scriptconv[fa]')."
            ) from e
        assert alphabet in [Alphabet.ERAAB, Alphabet.IPA]
        output_format = "IPA" if alphabet == Alphabet.IPA else 'eraab'
        self.g2p = Phonemizer(output_format)
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
        return cls.match_lang(target_lang, ["fa"])

    def phonemize_string(self, text: str, lang: str = "fa") -> str:
        """
        """
        lang = self.get_lang(lang)
        return self.g2p.phonemize(text)
