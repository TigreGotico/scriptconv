from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.openjtalk_engine import ENGINE_DISTRIBUTION, require_pyopenjtalk_plus


class OpenJTaklPhonemizer(BasePhonemizer):
    """Japanese readings from OpenJTalk, in Hepburn romaji or kana.

    The engine is pyopenjtalk-plus with onnxruntime. The backend refuses an
    install where another distribution owns the ``pyopenjtalk`` module, or
    where onnxruntime does not import, because those give other readings
    (:mod:`scriptconv.phonemizers.openjtalk_engine`).
    """
    engine_distribution = ENGINE_DISTRIBUTION

    def __init__(self, alphabet=Alphabet.HEPBURN):
        _check_alphabet(self, alphabet, [Alphabet.HEPBURN, Alphabet.KANA])
        pyopenjtalk = require_pyopenjtalk_plus("The OpenJTalk phonemizer", "scriptconv[ja-phonemizers]")
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
    engine_distribution = "cutlet"

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


__getattr__ = deprecated_getattr(__name__)
