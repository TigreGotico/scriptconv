"""ghana-g2p-backed phonemizer.

Wraps ``ghana-g2p`` (GhanaNLP, https://github.com/GhanaNLP/ghana-g2p,
Apache-2.0), a grapheme-to-phoneme library for 42 Ghanaian languages. It is
built on africa-g2p's rule tables and adds three things for Ghanaian text:
Unicode codepoint normalisation (for example ``ʊ`` U+028A written for ``ʋ``
U+028B), a patch table of missing or corrected letters, and donor rule sets
for languages africa-g2p has no table for. Every result records whether its
rules are the language's own, an equivalent code, or a related donor.

Like :class:`~scriptconv.phonemizers.africa.AfricaG2PPhonemizer`, it emits
IPA (:attr:`Alphabet.IPA`) or native-orthography phoneme units
(:attr:`Alphabet.AFRICA_G2P`).

``ghana-g2p`` depends on the PyPI ``africa-g2p`` package and loads THAT
installed copy, not scriptconv's vendored ``africa_g2p``. The two can be
different versions, so this backend and ``AfricaG2PPhonemizer`` can give
different output for the same language.

Optional extra: ``pip install scriptconv[ghana]``.
"""
from typing import Dict, List

from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet, _primary_subtag
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["GhanaG2PPhonemizer"]


def _ghana_g2p():
    """Import ``ghana_g2p`` lazily, naming the extra when it is missing."""
    try:
        import ghana_g2p
    except ImportError as e:
        raise ImportError(
            "ghana-g2p is required for the Ghanaian phonemizer. Install it "
            "with 'pip install ghana-g2p' (or 'pip install scriptconv[ghana]')."
        ) from e
    return ghana_g2p


class GhanaG2PPhonemizer(BasePhonemizer):
    """
    Rule-based G2P for 42 Ghanaian languages, backed by ``ghana-g2p``.

    Languages are ghana-g2p's own ISO 639-3 codes (``twi``, ``ewe``, ``dag``,
    ``gaa``, ``hau``, ...), read at runtime from ``ghana_g2p.languages()``.
    One engine per language is created on first use and cached.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        _check_alphabet(self, alphabet, [Alphabet.IPA, Alphabet.AFRICA_G2P])
        super().__init__(alphabet=alphabet)
        self._cache: Dict[str, object] = {}

    def _engine(self, resolved_lang: str):
        """Return, lazily creating and caching, the engine for *resolved_lang*."""
        if resolved_lang not in self._cache:
            self._cache[resolved_lang] = _ghana_g2p().GhanaG2P(resolved_lang)
        return self._cache[resolved_lang]

    @classmethod
    def supported_langs(cls) -> List[str]:
        """Return every ISO 639-3 code ghana-g2p lists."""
        return [entry["code"] for entry in _ghana_g2p().languages()]

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Resolve *target_lang* to a ghana-g2p ISO 639-3 code.

        Only the primary subtag is matched, exactly (``twi-GH`` -> ``twi``).
        ISO 639-1 tags are not mapped (``ee`` is not ``ewe``).

        Raises:
            ValueError: If ghana-g2p has no such language.
        """
        key = _primary_subtag(target_lang)
        if key in cls.supported_langs():
            return key
        raise ValueError(f"ghana-g2p: unsupported language {target_lang!r}")

    def phonemize_string(self, text: str, lang: str) -> str:
        engine = self._engine(self.get_lang(lang))
        if self.alphabet == Alphabet.IPA:
            return engine.ipa(text, sep=" ")
        return engine.grapheme(text, sep=" ")
