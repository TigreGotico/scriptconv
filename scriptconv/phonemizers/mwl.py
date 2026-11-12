import dataclasses

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizerIdentity
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer


# lang -> orthography2ipa spec. Mirandese is dialect-aware: the central
# variety is the default, with Sendinese and the Raiano (Ifanês) border
# variety selectable per call.
DIALECTS = {
    "mwl": "mwl",                      # central Mirandese (the standard)
    "mwl-x-sendim": "mwl-x-sendim",    # Sendinese
    "mwl-x-ifanes": "mwl-x-ifanes",    # Raiano / Ifanês (border variety)
}


class MirandesePhonemizer(BasePhonemizer):
    """
    Mirandese phonemizer on the orthography2ipa specs ``mwl``,
    ``mwl-x-sendim`` and ``mwl-x-ifanes``.  Output is always IPA.

    The variety is taken from the per-call ``lang`` argument (central ``mwl`` by
    default), so one instance serves all three.  The phonemes come from
    :class:`~scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer` on the
    matching spec, so this backend needs the ``o2i`` extra.
    """

    engine_distribution = Orthography2IPAPhonemizer.engine_distribution

    _LANGS = list(DIALECTS)

    def __init__(self):
        super().__init__(Alphabet.IPA)
        self._o2i = Orthography2IPAPhonemizer()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the closest supported Mirandese variety code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def identity(self, lang: str) -> PhonemizerIdentity:
        engine = self._o2i.identity(DIALECTS[self.get_lang(lang)])
        return dataclasses.replace(super().identity(lang), distribution=engine.distribution,
                                   version=engine.version, revision=engine.revision)

    def phonemize_string(self, text: str, lang: str = "mwl") -> str:
        return self._o2i.phonemize_string(text, DIALECTS[self.get_lang(lang)])
