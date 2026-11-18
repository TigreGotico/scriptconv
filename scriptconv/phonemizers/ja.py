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
        """The closest of ``ja`` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If none is close enough.
        """
        return cls.match_lang(target_lang, ["ja"])

    def phonemize_string(self, text: str, lang: str = "ja") -> str:
        """The reading of *text* in romaji or kana, after a check that *lang* is Japanese."""
        self.get_lang(lang)
        return self.g2p(text, kana=self.alphabet == Alphabet.KANA)


class CutletPhonemizer(BasePhonemizer):
    """Japanese text to romaji with cutlet.

    With *use_foreign_spelling*, a word whose UniDic lemma has a foreign
    spelling reads as that spelling: "カツ" gives "cutlet", not "katsu".
    """
    engine_distribution = "cutlet"

    def __init__(self, alphabet=Alphabet.HEPBURN, use_foreign_spelling = False):
        _check_alphabet(self, alphabet,
                        [Alphabet.HEPBURN, Alphabet.KUNREI, Alphabet.NIHON])
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
        """The closest of ``ja`` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If none is close enough.
        """
        return cls.match_lang(target_lang, ["ja"])

    def phonemize_string(self, text: str, lang: str = "ja") -> str:
        """The romaji of *text*, after a check that *lang* is Japanese."""
        self.get_lang(lang)
        return self.g2p.romaji(text)


__getattr__ = deprecated_getattr(__name__)
