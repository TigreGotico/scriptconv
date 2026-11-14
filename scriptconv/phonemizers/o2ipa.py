"""orthography2ipa-backed phonemizer.

Wraps ``orthography2ipa.G2P`` to expose the shared grapheme->IPA lattice as a
``BasePhonemizer``.  A single instance covers the whole orthography2ipa family
(hundreds of language specs: the Arabic lects, Basque, Galician, Mirandese,
Portuguese, the East-Slavic set, ...): one backend, many languages, always IPA.

Per-language quality varies -- the lattice is strongest for regular
orthographies.  For undiacritized Arabic use ``ArbtokPhonemizer`` (which adds a
diacritizer on top of this same lattice); for dialect-aware Basque use
``EuskaphonePhonemizer``.

``orthography2ipa`` is imported lazily so importing ``scriptconv`` never requires
it; install with ``pip install orthography2ipa`` (or ``pip install scriptconv[o2i]``).

With ``packaged_lexicons=True`` (the default) the engine of each language
holds the installed packaged lexicon (``o2i-lexicons``) for that language, when
a package serves it: the exceptions, and the patches when the package ships
them. The lexicon belongs to that engine, so no other orthography2ipa engine in
the process sees it. With ``packaged_lexicons=False`` the engine holds an empty
lexicon and runs on the rules alone.
"""
import dataclasses
import hashlib
import logging
from typing import Dict, List, Optional

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    PhonemizerIdentity,
    UnsupportedLanguageError,
)
from scriptconv.phonemizers.enums import Alphabet

LOG = logging.getLogger(__name__)


class Orthography2IPAPhonemizer(BasePhonemizer):
    """
    Data-driven multilingual IPA phonemizer backed by orthography2ipa.

    Accepts any language code that ``orthography2ipa.resolve`` can map to a
    supported spec (BCP-47 closest-match logic lives in orthography2ipa itself,
    so it is not reinvented here).  The per-language G2P engine is created
    lazily on first use and cached for the lifetime of the instance.
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
        """Return, lazily creating and caching, the G2P engine for *resolved_lang*."""
        if resolved_lang not in self._cache:
            import orthography2ipa
            patches = self._lexicon_patches(resolved_lang)
            lexicon = ({} if patches is None
                       else orthography2ipa.packaged_lexicon(resolved_lang, patches=patches))
            self._cache[resolved_lang] = orthography2ipa.G2P(
                resolved_lang, pipeline=orthography2ipa.Pipeline(lexicon=lexicon))
        return self._cache[resolved_lang]

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` set to the orthography2ipa
        spec revision of the resolved lect.

        When the engine holds a packaged lexicon, ``revision`` is the sha256 of
        the spec revision and the lexicon revision, so a lexicon change also
        changes it. When orthography2ipa cannot read its engine source,
        ``revision`` is ``None``.
        """
        import orthography2ipa
        from orthography2ipa.exceptions import EngineSourceUnavailable
        identity = super().identity(lang)
        try:
            revision = orthography2ipa.spec_revision(identity.lang)
        except EngineSourceUnavailable as exc:
            LOG.warning("orthography2ipa cannot read its engine source, so the "
                        "identity of %r has no revision: %s", identity.lang, exc)
            return identity
        patches = self._lexicon_patches(identity.lang)
        if patches is not None:
            lexicon = orthography2ipa.lexicon_revision(identity.lang, patches=patches)
            combined = f"{revision}\n{lexicon}".encode()
            revision = "sha256:" + hashlib.sha256(combined).hexdigest()
        return dataclasses.replace(identity, revision=revision)

    @classmethod
    def supported_langs(cls) -> List[str]:
        """Return every language code orthography2ipa ships a spec for."""
        import orthography2ipa
        return orthography2ipa.available_codes()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Resolve *target_lang* to the canonical orthography2ipa spec code.

        Delegates BCP-47 resolution to ``orthography2ipa.resolve``.

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
        # ``resolve`` echoes an unknown tag back rather than raising, so probe
        # the resolved code by constructing its G2P engine (raises if no spec).
        resolved = orthography2ipa.resolve(target_lang)
        try:
            orthography2ipa.G2P(resolved)
        except Exception as exc:
            raise UnsupportedLanguageError(
                f"orthography2ipa: unsupported language {target_lang!r}"
            ) from exc
        return resolved

    def phonemize_string(self, text: str, lang: str) -> str:
        resolved = self.get_lang(lang)
        return self._engine(resolved).transcribe(text)
