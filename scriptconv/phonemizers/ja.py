from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet

class OpenJTaklPhonemizer(BasePhonemizer):

    def __init__(self, alphabet=Alphabet.HEPBURN):
        _check_alphabet(self, alphabet, [Alphabet.HEPBURN, Alphabet.KANA])
        import pyopenjtalk
        self.g2p = pyopenjtalk.g2p
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
        return cls.match_lang(target_lang, ["ja"])

    def phonemize_string(self, text: str, lang: str = "ja") -> str:
        """
        """
        lang = self.get_lang(lang)
        return self.g2p(text, kana=self.alphabet == Alphabet.KANA)


class CutletPhonemizer(BasePhonemizer):

    def __init__(self, alphabet=Alphabet.HEPBURN, use_foreign_spelling = False):
        _check_alphabet(self, alphabet,
                        [Alphabet.HEPBURN, Alphabet.KUNREI, Alphabet.NIHON])
        # If `use_foreign_spelling` is true, output will use the foreign spelling
        #         provided in a UniDic lemma when available. For example, "カツ" will
        #         become "cutlet" instead of "katsu".
        try:
            import cutlet
        except ImportError as e:
            raise ImportError(
                "cutlet is required for the Cutlet phonemizer. "
                "Install it with 'pip install cutlet' "
                "(or 'pip install scriptconv[ja-phonemizers]')."
            ) from e
        self.g2p = cutlet.Cutlet(alphabet)
        self.g2p.use_foreign_spelling = use_foreign_spelling
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
        return cls.match_lang(target_lang, ["ja"])

    def phonemize_string(self, text: str, lang: str = "ja") -> str:
        """
        """
        lang = self.get_lang(lang)
        return self.g2p.romaji(text)

class PyKakasiPhonemizer(BasePhonemizer):

    def __init__(self, alphabet=Alphabet.HEPBURN):
        _check_alphabet(self, alphabet,
                        [Alphabet.HEPBURN, Alphabet.KANA, Alphabet.HIRA])
        # kana, hira, hepburn
        try:
            import pykakasi
        except ImportError as e:
            raise ImportError(
                "pykakasi is required for the PyKakasi phonemizer. "
                "Install it with 'pip install pykakasi' "
                "(or 'pip install scriptconv[ja-phonemizers]')."
            ) from e
        self.g2p = pykakasi.kakasi()
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
        return cls.match_lang(target_lang, ["ja"])

    def phonemize_string(self, text: str, lang: str = "ja") -> str:
        """
        """
        lang = self.get_lang(lang)
        return " ".join([
            a[self.alphabet] for a in
            self.g2p.convert(text)
        ])
