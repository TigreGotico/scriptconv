from typing import Optional

from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer


class MantoqPhonemizer(BasePhonemizer):
    """Arabic phonemizer wrapping the external ``mantoq`` package.

    Uses an externally-installed ``mantoq`` when present, otherwise the
    quarantined vendored copy under ``_vendored/mantoq`` — distributed under
    its OWN license (the phonetisation core is CC BY-NC 4.0, non-commercial;
    see its LICENSE.md), NOT this library's Apache-2.0.  Never selected
    automatically.  Kept for compatibility with published models trained on mantoq phoneme
    sequences; the Arabic default is :class:`ArbtokPhonemizer`.  Output is
    IPA (via :func:`scriptconv.notation.mantoq_to_ipa`) or the raw mantoq
    inventory with ``alphabet=Alphabet.MANTOQ``.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        if alphabet not in (Alphabet.IPA, Alphabet.MANTOQ):
            raise ValueError("MantoqPhonemizer outputs IPA or MANTOQ")
        super().__init__(alphabet)
        try:
            # an externally-installed upstream mantoq wins
            import mantoq
        except ImportError:
            # quarantined vendored copy under its OWN license (the
            # phonetisation core is CC BY-NC 4.0 — see
            # _vendored/mantoq/LICENSE.md); using it is an explicit opt-in
            # by requesting this phonemizer
            from scriptconv.phonemizers._vendored import mantoq
        self._g2p = mantoq.g2p

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ar"])

    def phonemize_string(self, text: str, lang: str) -> str:
        _, tokens = self._g2p(text)
        if self.alphabet == Alphabet.MANTOQ:
            return " ".join(tokens)
        from scriptconv.notation import mantoq_to_ipa
        return mantoq_to_ipa(tokens)



class ArbtokPhonemizer(BasePhonemizer):
    """
    Arabic phonemizer backed by ``arbtok``, an engine built on the
    orthography2ipa lattice.  Its edge over bare orthography2ipa is
    **undiacritized** Arabic: ``arbtok`` restores the tashkeel with a bundled
    diacritizer before transcribing, so it reads the unvocalized text people
    actually type.  Output is always IPA.

    The variety is any orthography2ipa Arabic spec code (``ar``, ``arb``,
    ``ar-EG``, ``ar-SA-x-najd``, ...), taken from the per-call ``lang`` argument.

    Register: arbtok's own default is the pausal (spoken) register, which is the
    right choice for the dialects; the full iʿrāb register is only phonologically
    apt for ``ar``/``arb`` (MSA/Classical).  The default here defers to arbtok's
    register default rather than overriding it, so this convention lives in the
    engine; pass ``model`` of ``"i'rab"`` to force the full register.

    ``arbtok`` is imported lazily so importing ``scriptconv`` does not hard-require it.
    """

    def __init__(self, register: Optional[str] = None,
                 alphabet: Alphabet = Alphabet.IPA):
        if alphabet != Alphabet.IPA:
            raise ValueError("arbtok only outputs IPA")
        # register: None -> defer to arbtok's own default (pausal). The iʿrab
        # aliases force arbtok's full case-ending register, which the plugin
        # spells "full" (apt only for ar/arb); pass any other value through so a
        # caller can still say "pausal"/"full" directly.
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
        """
        Resolve *target_lang* to an arbtok/orthography2ipa Arabic spec code.

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
