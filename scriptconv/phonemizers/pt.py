import dataclasses

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizerIdentity, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer


class TugaphonePhonemizer(BasePhonemizer):
    owned_stages = frozenset({"diacritize"})
    engine_distribution = "tugaphone"

    def __init__(self):
        try:
            from tugaphone import TugaPhonemizer
        except ImportError as e:
            raise ImportError(
                "tugaphone is required for the Tugaphone phonemizer. "
                "Install it with 'pip install tugaphone' "
                "(or 'pip install scriptconv[pt-phonemizers]')."
            ) from e
        self.tuga = TugaPhonemizer()
        super().__init__(Alphabet.IPA)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the closest supported language code.

        A full sub-regional lect tag tugaphone itself knows about (e.g.
        ``pt-PT-x-lisbon``, ``pt-PT-x-porto``) is passed through unchanged,
        so its output stays distinct from the generic country lect. A loose
        tag (``pt``, ``pt-PT``) falls back to :meth:`match_lang` against the
        country-level lects, since ``tugaphone.resolve_lect`` silently
        defaults an unrecognized tag to ``pt-PT`` rather than raising.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: The validated language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        import tugaphone
        dialects = {d.lower(): d for d in tugaphone.list_dialects()}
        if target_lang and target_lang.replace("_", "-").lower() in dialects:
            return dialects[target_lang.replace("_", "-").lower()]
        # this check is here only to throw an exception if invalid language is provided
        return cls.match_lang(target_lang, ["pt-PT", "pt-BR", "pt-AO", "pt-MZ", "pt-TL"])

    def phonemize_string(self, text: str, lang: str) -> str:
        lang = self.get_lang(lang)
        return self.tuga.phonemize_sentence(text, lang)



class BarranquenhoPhonemizer(BasePhonemizer):
    """
    Barranquenho phonemizer on the orthography2ipa spec ``ext-PT-x-barranco``,
    for the Portuguese/Spanish contact variety spoken in Barrancos.  Output is
    always IPA.

    The phonemes come from
    :class:`~scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer` on that
    spec, which transcribes the whole text, so cross-word sandhi applies.  This
    backend needs the ``o2i`` extra.
    """

    engine_distribution = Orthography2IPAPhonemizer.engine_distribution

    _LANGS = ["ext-PT-x-barrancos"]
    _SPEC = "ext-PT-x-barranco"

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        super().__init__(alphabet)
        self._o2i = Orthography2IPAPhonemizer()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the Barranquenho language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def identity(self, lang: str) -> PhonemizerIdentity:
        engine = self._o2i.identity(self._SPEC)
        return dataclasses.replace(super().identity(lang), distribution=engine.distribution,
                                   version=engine.version, revision=engine.revision)

    def phonemize_string(self, text: str, lang: str = "ext-PT-x-barrancos") -> str:
        self.get_lang(lang)
        return self._o2i.phonemize_string(text, self._SPEC)
