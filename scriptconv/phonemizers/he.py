from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer


class PhonikudPhonemizer(BasePhonemizer):

    def __init__(self):
        from phonikud import phonemize
        self.g2p = phonemize
        super().__init__(Alphabet.IPA)

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
        return cls.match_lang(target_lang, ["he"])

    def phonemize_string(self, text: str, lang: str = "he") -> str:
        """
        """
        lang = self.get_lang(lang)
        return self.g2p(text)
