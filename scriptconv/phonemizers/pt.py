import dataclasses
import functools
import logging
from typing import Dict, FrozenSet, Optional, Tuple

from scriptconv.phonemizers.base import BasePhonemizer, PhonemizerIdentity, _check_alphabet
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer

LOG = logging.getLogger(__name__)


class TugaphonePhonemizer(BasePhonemizer):
    owned_stages = frozenset({"diacritize"})
    engine_distribution = "tugaphone"

    contact = "none"
    """The embedded-language policy that this backend passes to tugaphone.
    ``tugaphone.revision`` covers ``"none"`` only, so any other value gives
    no ``revision``."""

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

    def _identity_settings(self) -> Dict[str, object]:
        return {"contact": self.contact}

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        """The distributions that ``tugaphone.revision`` covers for the lect of *lang*."""
        engine = _tugaphone_revision(self.get_lang(lang))
        return frozenset() if engine is None else engine[1]

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the code revision of this
        backend that holds ``tugaphone.revision`` of the resolved lect.

        ``tugaphone.revision`` covers tugaphone and each distribution that its
        output path loads, for ``contact="none"``. The code revision of
        :func:`~scriptconv.phonemizers._revision.code_revision` adds the
        scriptconv code on the path of this backend, and the distributions
        that tugaphone does not cover. So a tugaphone release that keeps its
        revision keeps this revision. ``revision`` is ``None`` when
        :attr:`contact` is not ``"none"``, and, with one warning, when
        tugaphone gives no revision.
        """
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        if self.contact != "none":
            return identity
        engine = _tugaphone_revision(identity.lang)
        if engine is None:
            return identity
        return dataclasses.replace(
            identity, revision=code_revision(self, identity.lang, {"tugaphone": engine[0]}))

    def phonemize_string(self, text: str, lang: str) -> str:
        lang = self.get_lang(lang)
        return self.tuga.phonemize_sentence(text, lang, contact=self.contact)


@functools.lru_cache(maxsize=None)
def _tugaphone_revision(lect: str) -> Optional[Tuple[str, FrozenSet[str]]]:
    """``tugaphone.revision`` of *lect* and the distributions it covers, or
    ``None`` and one warning in this process when tugaphone gives no revision."""
    import tugaphone
    from tugaphone.content_revision import distributions
    try:
        return tugaphone.revision(lect), frozenset(distributions(tugaphone.resolve_lect(lect)))
    except tugaphone.RevisionError as exc:
        LOG.warning("tugaphone gives no revision for %r, so the identity has none: %s: %s",
                    lect, type(exc).__name__, exc)
        return None


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

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        return self._o2i._covered_distributions(self._SPEC)

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the code revision of this
        backend that holds the orthography2ipa revision of ``ext-PT-x-barranco``,
        as :meth:`Orthography2IPAPhonemizer.identity
        <scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer.identity>` gives it."""
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        engine = self._o2i._spec_revision(self._SPEC)
        if engine is None:
            return identity
        return dataclasses.replace(
            identity, revision=code_revision(self, identity.lang, {"orthography2ipa": engine}))

    def phonemize_string(self, text: str, lang: str = "ext-PT-x-barrancos") -> str:
        self.get_lang(lang)
        return self._o2i.phonemize_string(text, self._SPEC)
