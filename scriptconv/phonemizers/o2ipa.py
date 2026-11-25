"""The orthography2ipa phonemizer: one backend for every orthography2ipa spec, always IPA.

For undiacritized Arabic use ``ArbtokPhonemizer``, and for the Basque dialects
``EuskaphonePhonemizer``; both build on the same engine.

With ``packaged_lexicons=True`` (the default) the engine of each language holds
the packaged lexicon (``o2i-lexicons``) for that language, when a package
serves it: the exceptions, and the patches when the package ships them. No
other orthography2ipa engine in the process sees that lexicon. With
``packaged_lexicons=False`` the engine runs on the rules alone.
"""
import logging
from typing import Dict, List, Optional

from scriptconv.phonemizers.base import (
    BasePhonemizer,
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
    revision_distributions = ("o2i-lexicons",)

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
