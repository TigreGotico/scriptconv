"""africa-g2p-backed phonemizer.

Wraps the vendored ``africa_g2p`` copy's ``AfricaPipeline`` to expose its
rule-based grapheme-to-phoneme engine for 400+ African languages (Hartell's
*Alphabets of Africa*, UNESCO 1993) as a ``BasePhonemizer``. One backend,
hundreds of ISO 639-3 codes.

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

``africa-g2p`` is not published to PyPI, and scriptconv does not take
``git+`` dependencies, so — unlike every other wrapper in this package — it
is vendored rather than an optional extra: see
``scriptconv.phonemizers._vendored.africa_g2p`` and its ``LICENSE.md`` /
``DATA_LICENSE.md`` (code is Apache-2.0; the language data carries its own
attribution requirements). It is always available, no extra to install.
"""
from typing import Dict, List

from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet, _primary_subtag
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["AfricaG2PPhonemizer"]


def _vendored_africa_g2p():
    """Return the vendored ``africa_g2p`` module, importing it lazily.

    There is no external ``africa_g2p`` distribution to prefer (the package
    is not on PyPI) — this always resolves to the quarantined vendored copy.
    An :class:`ImportError` here means the scriptconv install itself is
    broken (the vendored tree ships with every install), not that an
    optional extra is missing.
    """
    try:
        from scriptconv.phonemizers._vendored import africa_g2p as _pkg
    except ImportError as e:
        raise ImportError(
            "scriptconv's vendored africa_g2p copy is missing or broken — "
            "this is a bundled backend, not an optional extra, so this "
            "indicates a corrupted scriptconv installation."
        ) from e
    return _pkg


class AfricaG2PPhonemizer(BasePhonemizer):
    """
    Rule-based G2P phonemizer backed by the vendored africa-g2p copy,
    covering 400+ African languages by ISO 639-3 code.

    Supported languages are enumerated at runtime from the vendored package's
    rule-file listing (``africa_g2p.available_languages()``) rather than
    hardcoded here.

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
            _pkg = _vendored_africa_g2p()
            output = "ipa" if self.alphabet == Alphabet.IPA else "grapheme"
            self._cache[resolved_lang] = _pkg.AfricaPipeline(lang=resolved_lang, output=output)
        return self._cache[resolved_lang]

    @classmethod
    def supported_langs(cls) -> List[str]:
        """Return every ISO 639-3 code the vendored africa_g2p ships a rule file for."""
        return _vendored_africa_g2p().available_languages()

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
