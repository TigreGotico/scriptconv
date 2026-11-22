import dataclasses
from typing import FrozenSet

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizerIdentity
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

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        return self._o2i._covered_distributions(DIALECTS[self.get_lang(lang)])

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the code revision of this
        backend that holds the orthography2ipa revision of the variety's spec,
        as :meth:`Orthography2IPAPhonemizer.identity
        <scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer.identity>` gives it."""
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        engine = self._o2i._spec_revision(DIALECTS[identity.lang])
        if engine is None:
            return identity
        return dataclasses.replace(
            identity, revision=code_revision(self, identity.lang, {"orthography2ipa": engine}))

    def phonemize_string(self, text: str, lang: str = "mwl") -> str:
        return self._o2i.phonemize_string(text, DIALECTS[self.get_lang(lang)])
