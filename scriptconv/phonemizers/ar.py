from typing import Optional

from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet


class ArbtokPhonemizer(BasePhonemizer):
    """Arabic to IPA through ``arbtok``, which restores the tashkeel before it transcribes.

    So it reads undiacritized Arabic, which bare orthography2ipa does not. The
    per-call ``lang`` is any orthography2ipa Arabic spec code (``ar``, ``arb``,
    ``ar-EG``, ``ar-SA-x-najd``, ...).

    ``register=None`` keeps arbtok's default, the pausal register, which suits
    the dialects. ``"i'rab"`` (or ``"irab"``, ``"iʿrab"``, ``"full"``) forces the
    full case-ending register, apt only for ``ar`` and ``arb``.
    """

    owned_stages = frozenset({"diacritize"})
    engine_distribution = "arbtok"

    def __init__(self, register: Optional[str] = None,
                 alphabet: Alphabet = Alphabet.IPA):
        if alphabet != Alphabet.IPA:
            raise ValueError("arbtok only outputs IPA")
        # arbtok spells the iʿrab register "full"; any other value passes through.
        self.register = None
        if register:
            self.register = ("full" if register.lower() in ("irab", "i'rab", "iʿrab", "full")
                             else register)
        self._cache = {}
        super().__init__(alphabet)

    def _engine(self, lang: str):
        """Return, lazily creating and caching, the arbtok engine for *lang*."""
        key = (lang, self.register)
        if key not in self._cache:
            try:
                from arbtok.plugin import ArbtokG2PPlugin
            except ImportError as e:
                raise ImportError(
                    "arbtok is required for the arbtok Arabic phonemizer. "
                    "Install it with 'pip install arbtok' "
                    "(or 'pip install scriptconv[ar-phonemizers]')."
                ) from e
            kwargs = dict(lang=lang, diacritize=True)
            if self.register is not None:
                kwargs["register"] = self.register
            self._cache[key] = ArbtokG2PPlugin(**kwargs)
        return self._cache[key]

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """*target_lang* as an arbtok (orthography2ipa) Arabic spec code.

        Raises:
            ValueError: If arbtok has no Arabic variety for *target_lang*.
        """
        try:
            from arbtok import spec_for_lang
        except ImportError as e:
            raise ImportError(
                "arbtok is required for the arbtok Arabic phonemizer. "
                "Install it with 'pip install arbtok' (or 'pip install scriptconv[ar-phonemizers]')."
            ) from e
        return spec_for_lang(target_lang)

    def phonemize_string(self, text: str, lang: str = "ar") -> str:
        return self._engine(self.get_lang(lang)).transcribe(text)


__getattr__ = deprecated_getattr(__name__)
