from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer


# lang -> orthography2ipa spec.
DIALECTS = {
    "mwl": "mwl",                      # central Mirandese (the standard)
    "mwl-x-sendim": "mwl-x-sendim",    # Sendinese
    "mwl-x-ifanes": "mwl-x-ifanes",    # Raiano / Ifanês (border variety)
}


class MirandesePhonemizer(BasePhonemizer):
    """Mirandese to IPA on the orthography2ipa specs ``mwl``, ``mwl-x-sendim`` and ``mwl-x-ifanes``.

    The per-call ``lang`` picks the variety, central ``mwl`` by default. The
    phonemes come from
    :class:`~scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer`, so this
    backend needs the ``o2i`` extra.
    """

    engine_distribution = Orthography2IPAPhonemizer.engine_distribution
    revision_distributions = Orthography2IPAPhonemizer.revision_distributions

    _LANGS = list(DIALECTS)

    def __init__(self):
        super().__init__(Alphabet.IPA)
        self._o2i = Orthography2IPAPhonemizer()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest supported Mirandese variety code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def phonemize_string(self, text: str, lang: str = "mwl") -> str:
        return self._o2i.phonemize_string(text, DIALECTS[self.get_lang(lang)])
