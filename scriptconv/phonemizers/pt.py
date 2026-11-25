import logging

from linguatag import standardize_lang

from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer

LOG = logging.getLogger(__name__)


class TugaphonePhonemizer(BasePhonemizer):
    owned_stages = frozenset({"normalize", "diacritize"})
    engine_distribution = "tugaphone"

    contact = "none"
    """The embedded-language policy that this backend passes to tugaphone."""

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
        """The lect of *target_lang*: a tugaphone lect as tugaphone spells it, else the closest country lect.

        A lect that tugaphone lists, as ``pt-PT-x-porto``, passes through, so it
        keeps its own output. Any other tag goes through :meth:`match_lang`,
        because ``tugaphone.resolve_lect`` reads an unknown tag as ``pt-PT``.

        Raises:
            ValueError: If the language code is unsupported.
        """
        import tugaphone
        dialects = {standardize_lang(d): d for d in tugaphone.list_dialects()}
        if target_lang and (tag := standardize_lang(target_lang)) in dialects:
            return dialects[tag]
        return cls.match_lang(target_lang, ["pt-PT", "pt-BR", "pt-AO", "pt-MZ", "pt-TL"])

    def phonemize_string(self, text: str, lang: str) -> str:
        lang = self.get_lang(lang)
        return self.tuga.phonemize_sentence(text, lang, contact=self.contact)

    def _engine_revision(self, lang: str) -> str:
        """``tugaphone.revision(lang)``: tugaphone names the distributions that give its phonemes."""
        import tugaphone
        return tugaphone.revision(lang)


class BarranquenhoPhonemizer(BasePhonemizer):
    """Barranquenho, the Portuguese and Spanish contact variety of Barrancos, to IPA.

    The phonemes come from
    :class:`~scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer` on the
    spec ``ext-PT-x-barranco``, which reads the whole text, so cross-word
    sandhi applies. This backend needs the ``o2i`` extra.
    """

    engine_distribution = Orthography2IPAPhonemizer.engine_distribution
    revision_distributions = Orthography2IPAPhonemizer.revision_distributions

    _LANGS = ["ext-PT-x-barrancos"]
    _SPEC = "ext-PT-x-barranco"

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        super().__init__(alphabet)
        self._o2i = Orthography2IPAPhonemizer()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The Barranquenho language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        return cls.match_lang(target_lang, cls._LANGS)

    def phonemize_string(self, text: str, lang: str = "ext-PT-x-barrancos") -> str:
        self.get_lang(lang)
        return self._o2i.phonemize_string(text, self._SPEC)
