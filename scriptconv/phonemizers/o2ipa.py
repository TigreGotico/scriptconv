"""The orthography2ipa phonemizer: one backend for every orthography2ipa spec, always IPA.

For undiacritized Arabic use ``ArbtokPhonemizer``, and for the Basque dialects
``EuskaphonePhonemizer``; both build on the same engine.

With ``packaged_lexicons=True`` (the default) the engine of each language holds
the packaged lexicon (``o2i-lexicons``) for that language, when a package
serves it: the exceptions, and the patches when the package ships them. No
other orthography2ipa engine in the process sees that lexicon. With
``packaged_lexicons=False`` the engine runs on the rules alone.
"""
import dataclasses
import hashlib
import logging
from typing import Dict, FrozenSet, List, Optional

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    PhonemizerIdentity,
    UnsupportedLanguageError,
)
from scriptconv.phonemizers.enums import Alphabet

LOG = logging.getLogger(__name__)

# Spec codes whose G2P engine builds. ``orthography2ipa.resolve`` echoes an
# unknown tag, so get_lang builds the engine once per code to prove the spec.
_KNOWN_SPECS: set[str] = set()


class Orthography2IPAPhonemizer(BasePhonemizer):
    """Any language that ``orthography2ipa.resolve`` maps to a spec, to IPA.

    The BCP-47 closest match lives in orthography2ipa, so this wrapper does not
    repeat it. The engine of each language is built on first use and kept.
    """

    engine_distribution = "orthography2ipa"

    def __init__(self, packaged_lexicons: bool = True):
        super().__init__(alphabet=Alphabet.IPA)
        self.packaged_lexicons = packaged_lexicons
        self._cache: Dict[str, object] = {}

    def _lexicon_patches(self, resolved_lang: str) -> Optional[bool]:
        """The ``patches`` flag of the packaged lexicon that the engine of
        *resolved_lang* holds, or ``None`` when the engine holds no lexicon."""
        import orthography2ipa
        if (not self.packaged_lexicons
                or resolved_lang not in orthography2ipa.packaged_lexicon_sources()):
            return None
        return resolved_lang in orthography2ipa.packaged_lexicon_sources(patches=True)

    def _engine(self, resolved_lang: str):
        """The G2P engine of *resolved_lang*, built on first use."""
        if resolved_lang not in self._cache:
            import orthography2ipa
            patches = self._lexicon_patches(resolved_lang)
            lexicon = ({} if patches is None
                       else orthography2ipa.packaged_lexicon(resolved_lang, patches=patches))
            self._cache[resolved_lang] = orthography2ipa.G2P(
                resolved_lang, pipeline=orthography2ipa.Pipeline(lexicon=lexicon))
        return self._cache[resolved_lang]

    def _revision_arguments(self) -> Dict[str, object]:
        return {"packaged_lexicons": self.packaged_lexicons}

    def _spec_revision(self, resolved_lang: str) -> Optional[str]:
        """The orthography2ipa revision of *resolved_lang*, or ``None`` and a
        warning when orthography2ipa cannot read its engine source.

        When the engine holds a packaged lexicon, it is the sha256 of the spec
        revision and the lexicon revision, so a lexicon change also changes it.
        """
        import orthography2ipa
        from orthography2ipa.exceptions import EngineSourceUnavailable
        try:
            revision = orthography2ipa.spec_revision(resolved_lang)
        except EngineSourceUnavailable as exc:
            LOG.warning("orthography2ipa cannot read its engine source, so the "
                        "identity of %r holds the orthography2ipa version: %s", resolved_lang, exc)
            return None
        patches = self._lexicon_patches(resolved_lang)
        if patches is not None:
            lexicon = orthography2ipa.lexicon_revision(resolved_lang, patches=patches)
            combined = f"{revision}\n{lexicon}".encode()
            revision = "sha256:" + hashlib.sha256(combined).hexdigest()
        return revision

    def _covered_distributions(self, lang: str) -> FrozenSet[str]:
        """orthography2ipa, and o2i-lexicons when the engine of *lang* holds a packaged lexicon."""
        if self._lexicon_patches(self.get_lang(lang)) is None:
            return frozenset({"orthography2ipa"})
        return frozenset({"orthography2ipa", "o2i-lexicons"})

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the code revision of this
        backend that holds the orthography2ipa revision of the resolved lect.

        :meth:`_spec_revision` gives the orthography2ipa revision. The code
        revision of :func:`~scriptconv.phonemizers._revision.code_revision`
        adds the scriptconv code on the path of this backend, and leaves out
        the files of orthography2ipa and of a packaged lexicon. So an
        orthography2ipa release that keeps the spec revision keeps the
        revision. When orthography2ipa cannot read its engine source,
        ``revision`` is that of :meth:`BasePhonemizer.identity`, which holds
        the orthography2ipa version.
        """
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        engine = self._spec_revision(identity.lang)
        if engine is None:
            return identity
        return dataclasses.replace(
            identity, revision=code_revision(self, identity.lang, {"orthography2ipa": engine}))

    @classmethod
    def supported_langs(cls) -> List[str]:
        """Every language code orthography2ipa ships a spec for."""
        import orthography2ipa
        return orthography2ipa.available_codes()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """*target_lang* as the orthography2ipa spec code that ``orthography2ipa.resolve`` gives.

        ``orthography2ipa.resolve`` does the BCP-47 closest match.

        Raises:
            ValueError: If orthography2ipa has no spec for *target_lang*.
        """
        try:
            import orthography2ipa
        except ImportError as e:
            raise ImportError(
                "orthography2ipa is required for the Orthography2IPA phonemizer. "
                "Install it with 'pip install orthography2ipa' "
                "(or 'pip install scriptconv[o2i]')."
            ) from e
        resolved = orthography2ipa.resolve(target_lang)
        if resolved not in _KNOWN_SPECS:
            try:
                orthography2ipa.G2P(resolved)
            except Exception as exc:
                raise UnsupportedLanguageError(
                    f"orthography2ipa: unsupported language {target_lang!r}"
                ) from exc
            _KNOWN_SPECS.add(resolved)
        return resolved

    def phonemize_string(self, text: str, lang: str) -> str:
        resolved = self.get_lang(lang)
        return self._engine(resolved).transcribe(text)
