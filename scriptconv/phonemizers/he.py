import re

from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer

# Hebrew writes a prefix on a number with a hyphen ("ב-5"), and phonikud reads
# that hyphen as a minus sign.
_PREFIX_HYPHEN = re.compile(r"(?<=[\u0590-\u05FF])-(?=\d)")
# phonikud reads "%" only as a token of its own, so "20%." loses the "%".
_PUNCTUATION_AFTER_PERCENT = re.compile(r"(?<=%)(?=[.,;:!?])")
# phonikud reads "[word](/ipa/)" as an annotation and drops a bracketed word.
_BRACKET = re.compile(r"[\[\]]")


class PhonikudPhonemizer(BasePhonemizer):
    owned_stages = frozenset({"normalize"})
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
        text = _PREFIX_HYPHEN.sub(" ", _BRACKET.sub(" ", text))
        return self.g2p(_PUNCTUATION_AFTER_PERCENT.sub(" ", text))
