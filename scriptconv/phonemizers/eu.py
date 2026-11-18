from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.base import BasePhonemizer, UnsupportedLanguageError
from scriptconv.phonemizers.enums import Alphabet


class EuskaphonePhonemizer(BasePhonemizer):
    """
    Dialect-aware Basque phonemizer backed by ``euskaphone``, a TTS frontend
    built on the shared orthography2ipa lattice.  Output is always IPA.

    This is distinct from ``AhoTTSPhonemizer`` in scriptconv-copyleft: AhoTTS is a port of the
    AhoTTS front-end, whereas euskaphone drives the orthography2ipa candidate
    lattice and resolves eight Basque lects (Batua and the historical dialects)
    from their spec data, adding vigesimal number verbalization and Spanish/
    French code-switch handling.

    The lect is taken from the per-call ``lang`` argument -- a BCP-47 code
    (``eu``, ``eu-x-zuberera``, ...) which euskaphone resolves internally, so a
    single instance serves every dialect.  ``euskaphone`` is imported lazily so
    importing ``scriptconv`` does not hard-require it.

    euskaphone reads numbers, dates and abbreviations through ``text2spoken``
    on every call, so this backend owns the ``normalize`` stage.
    """

    owned_stages = frozenset({"normalize"})
    engine_distribution = "euskaphone"

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        if alphabet != Alphabet.IPA:
            raise ValueError("euskaphone only outputs IPA")
        self._pho = None
        super().__init__(alphabet)

    @property
    def pho(self):
        """Lazily import, construct and cache the ``EuskaPhonemizer``."""
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
        """
        Resolve *target_lang* to a euskaphone Basque lect code.

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
        # resolve_lect silently falls back to Batua for an unknown tag, so gate
        # on is_supported first.
        if not is_supported(target_lang):
            raise UnsupportedLanguageError(f"euskaphone: unsupported language {target_lang!r}")
        return resolve_lect(target_lang)

    def phonemize_string(self, text: str, lang: str = "eu") -> str:
        return self.pho.phonemize_sentence(text, dialect=self.get_lang(lang))


__getattr__ = deprecated_getattr(__name__)
