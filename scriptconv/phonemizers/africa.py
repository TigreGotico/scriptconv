"""africa-g2p-backed phonemizer.

Wraps ``africa_g2p.AfricaPipeline`` to expose its rule-based grapheme-to-phoneme
engine for 400+ African languages (Hartell's *Alphabets of Africa*, UNESCO 1993)
as a ``BasePhonemizer``. One backend, hundreds of ISO 639-3 codes, no runtime
dependencies of its own.

Unlike most wrappers in this package, africa-g2p natively emits two kinds of
output for the same rule set:

* IPA (``output="ipa"``) — scriptconv's usual currency;
* native-orthography phoneme units (``output="grapheme"``) — the language's own
  writing units (e.g. ``ny``, ``kp``, ``ɔ``), which the upstream project notes
  trains TTS/ASR models better than IPA for these languages.

Both are exposed here as selectable alphabets — :attr:`Alphabet.IPA` and
:attr:`Alphabet.AFRICA_G2P` — the same shape as :class:`~scriptconv.phonemizers.zh.JiebaPhonemizer`
(pinyin vs. IPA) rather than a single fixed alphabet: africa-g2p is not a
one-notation engine like Cotovía or Vosk.

``africa_g2p`` is imported lazily so importing ``scriptconv`` never requires
it; install with ``pip install africa-g2p`` (or ``pip install
scriptconv[africa-g2p]``).
"""
from typing import Dict, List

from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet, _primary_subtag
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["AfricaG2PPhonemizer"]


class AfricaG2PPhonemizer(BasePhonemizer):
    """
    Rule-based G2P phonemizer backed by africa-g2p, covering 400+ African
    languages by ISO 639-3 code.

    Supported languages are enumerated at runtime from the installed package
    (``africa_g2p.available_languages()``, which lists africa-g2p's per-language
    JSON rule files) rather than hardcoded here, so this wrapper tracks upstream
    coverage automatically as new rule files ship.

    Per-language engines are created lazily on first use and cached for the
    lifetime of the instance (one cache per alphabet, since IPA and
    native-orthography output come from differently-configured engines).
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA):
        _check_alphabet(self, alphabet, [Alphabet.IPA, Alphabet.AFRICA_G2P])
        super().__init__(alphabet=alphabet)
        self._cache: Dict[str, object] = {}

    def _engine(self, resolved_lang: str):
        """Return, lazily creating and caching, the pipeline for *resolved_lang*."""
        if resolved_lang not in self._cache:
            try:
                from africa_g2p import AfricaPipeline
            except ImportError as e:
                raise ImportError(
                    "africa-g2p is required for the AfricaG2P phonemizer. "
                    "Install it with 'pip install africa-g2p' "
                    "(or 'pip install scriptconv[africa-g2p]')."
                ) from e
            output = "ipa" if self.alphabet == Alphabet.IPA else "grapheme"
            self._cache[resolved_lang] = AfricaPipeline(lang=resolved_lang, output=output)
        return self._cache[resolved_lang]

    @classmethod
    def supported_langs(cls) -> List[str]:
        """Return every ISO 639-3 code africa-g2p ships a rule file for."""
        try:
            from africa_g2p import available_languages
        except ImportError as e:
            raise ImportError(
                "africa-g2p is required for the AfricaG2P phonemizer. "
                "Install it with 'pip install africa-g2p' "
                "(or 'pip install scriptconv[africa-g2p]')."
            ) from e
        return available_languages()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Resolve *target_lang* to a supported africa-g2p ISO 639-3 code.

        Only the primary subtag is matched (e.g. ``tw-GH`` -> ``twi`` is *not*
        attempted — africa-g2p keys its rule files by exact ISO 639-3 code, not
        BCP-47 macrolanguage/region mapping, so this is an exact-match lookup,
        not the closest-match fuzzing :meth:`BasePhonemizer.match_lang` does).

        Raises:
            ValueError: If africa-g2p has no rule file for *target_lang*.
        """
        key = _primary_subtag(target_lang)
        if key in cls.supported_langs():
            return key
        raise ValueError(f"africa-g2p: unsupported language {target_lang!r}")

    def phonemize_string(self, text: str, lang: str) -> str:
        resolved = self.get_lang(lang)
        return self._engine(resolved).run(text, sep=" ")
