from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.base import BasePhonemizer, UnsupportedLanguageError
from scriptconv.phonemizers.enums import Alphabet


class EuskaphonePhonemizer(BasePhonemizer):
    """Basque to IPA through ``euskaphone``, for eight lects: Batua and the historical dialects.

    The per-call ``lang``, a BCP-47 code (``eu``, ``eu-x-zuberera``, ...), picks
    the lect, so one instance serves every dialect. euskaphone reads numbers, dates and
    abbreviations through ``text2spoken``, so this backend owns the
    ``normalize`` stage. ``AhoTTSPhonemizer`` in scriptconv-copyleft is a
    different engine, a port of the AhoTTS front-end.
    """

    owned_stages = frozenset({"normalize"})
    engine_distribution = "euskaphone"
    revision_distributions = ("orthography2ipa", "text2spoken")

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        if alphabet != Alphabet.IPA:
            raise ValueError("euskaphone only outputs IPA")
        self._pho = None
        super().__init__(alphabet)

    @property
    def pho(self):
        """The ``EuskaPhonemizer``, built on first use."""
        if self._pho is None:
            try:
                from euskaphone import EuskaPhonemizer
            except ImportError as e:
                raise ImportError(
                    "euskaphone is required for the euskaphone Basque phonemizer. "
                    "Install it with 'pip install euskaphone' "
                    "(or 'pip install scriptconv[eu]')."
                ) from e
            self._pho = EuskaPhonemizer()
        return self._pho

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """*target_lang* as a euskaphone Basque lect code.

        Raises:
            ValueError: If euskaphone has no lect for *target_lang*.
        """
        try:
            from euskaphone import resolve_lect
            from euskaphone.registry import is_supported
        except ImportError as e:
            raise ImportError(
                "euskaphone is required for the euskaphone Basque phonemizer. "
                "Install it with 'pip install euskaphone' (or 'pip install scriptconv[eu]')."
            ) from e
        # resolve_lect gives Batua for an unknown tag.
        if not is_supported(target_lang):
            raise UnsupportedLanguageError(f"euskaphone: unsupported language {target_lang!r}")
        return resolve_lect(target_lang)

    def phonemize_string(self, text: str, lang: str = "eu") -> str:
        return self.pho.phonemize_sentence(text, dialect=self.get_lang(lang))


__getattr__ = deprecated_getattr(__name__)
