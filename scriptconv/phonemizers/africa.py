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

``africa-g2p`` is published on PyPI and is an optional extra here:
``pip install scriptconv[africa]``. It was vendored while it was unpublished;
that copy is gone, because this project does not vendor what PyPI publishes.
The extra pins ``>=0.2.4,<0.3``: the 0.2.4 line's 400 rule tables are all
chart-sourced, while 0.3.2 carries 750 tables of which 352 say ``llm-draft``.

A pin is not a guarantee. ``ghana-g2p`` requires ``africa-g2p>=0.1.1`` with no
ceiling, so ``pip install scriptconv[ghana]`` resolves africa-g2p on its own
terms and lands on 0.3.2 whatever the ``africa`` extra says. So the ceiling is
not what keeps a draft table out of an answer: each table's own ``confidence``
field is read, and a language whose table says ``llm-draft`` is not offered
unless the caller passes ``allow_draft=True``. Measured, that removes 0 of
0.2.4's 400 languages and 352 of 0.3.2's 750.

The library's code is Apache-2.0. Its language data is derived from Omniglot
script charts (© Simon Ager) and Hartell (ed.), *Alphabets of Africa*
(UNESCO/SIL, 1993), and carries its own attribution requirements, which the
installed distribution ships.
"""
from functools import lru_cache
from typing import Dict, FrozenSet, List

from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet, _primary_subtag
from scriptconv.phonemizers.enums import Alphabet

__all__ = ["AfricaG2PPhonemizer"]

#: The value africa-g2p writes in a rule table it generated rather than read
#: off a chart. Every table carries a ``confidence`` field; measured on 0.2.4
#: the values are ``omniglot`` (313), ``high`` (85), ``hand-verified`` (1) and
#: ``medium`` (1), and none is a draft. On 0.3.2 there are 750 tables and 352
#: of them say ``llm-draft``.
DRAFT_CONFIDENCE = "llm-draft"


def _africa_g2p():
    """Import the installed ``africa_g2p`` lazily, naming the extra if absent."""
    try:
        import africa_g2p as _pkg
    except ImportError as e:
        raise ImportError(
            "africa-g2p is required for the African-language phonemizer. "
            "Install it with 'pip install africa-g2p' "
            "(or 'pip install scriptconv[africa]')."
        ) from e
    return _pkg


def _installed_version(_pkg) -> str:
    """The installed africa-g2p version, or a stand-in when it states none.

    Only used as `_draft_codes`'s cache key.
    """
    version = getattr(_pkg, "__version__", None)
    if version:
        return str(version)
    try:
        from importlib.metadata import version as _dist_version

        return str(_dist_version("africa-g2p"))
    except Exception:
        return "unknown"


@lru_cache(maxsize=None)
def _draft_codes(_pkg, version: str) -> FrozenSet[str]:
    """Every code whose rule table this install marks as a draft.

    The table is the evidence, not the version number. A pin can be bypassed -
    ``ghana-g2p`` requires ``africa-g2p>=0.1.1`` with no ceiling, so
    ``pip install scriptconv[ghana]`` resolves africa-g2p on its own terms -
    and a ceiling has to be raised by hand every release. The ``confidence``
    field is written by the project that generated the table, travels with the
    data, and needs no maintenance here.

    ``version`` is the installed distribution's version. It is not read: it is
    the cache key, so a different install in the same process is scanned again
    rather than answered from the first one's tables.
    """
    load_rules = _pkg.loader.load_rules

    drafts = set()
    for code in _pkg.available_languages():
        try:
            table = load_rules(code)
        except Exception:
            # A table that cannot be read is not a draft claim either way;
            # `_engine` will raise on it with the upstream error.
            continue
        if isinstance(table, dict) and table.get("confidence") == DRAFT_CONFIDENCE:
            drafts.add(code)
    return frozenset(drafts)


class AfricaG2PPhonemizer(BasePhonemizer):
    """
    Rule-based G2P phonemizer backed by ``africa-g2p``, covering 400+
    African languages by ISO 639-3 code.

    Supported languages are enumerated at runtime from the vendored package's
    rule-file listing (``africa_g2p.available_languages()``) rather than
    hardcoded here.

    Per-language engines are created lazily on first use and cached for the
    lifetime of the instance (one cache per alphabet, since IPA and
    native-orthography output come from differently-configured engines).
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA,
                 allow_draft: bool = False):
        """
        Args:
            alphabet: :attr:`Alphabet.IPA` or :attr:`Alphabet.AFRICA_G2P`.
            allow_draft: include the languages whose rule table africa-g2p
                marks ``llm-draft``. Off by default: a draft table is
                generated rather than read off a chart, and a caller who has
                not asked for one must not be given one. See
                :func:`_draft_codes`.
        """
        _check_alphabet(self, alphabet, [Alphabet.IPA, Alphabet.AFRICA_G2P])
        super().__init__(alphabet=alphabet)
        self._allow_draft = allow_draft
        self._cache: Dict[str, object] = {}

    def _engine(self, resolved_lang: str):
        """Return, lazily creating and caching, the pipeline for *resolved_lang*."""
        if resolved_lang not in self._cache:
            _pkg = _africa_g2p()
            output = "ipa" if self.alphabet == Alphabet.IPA else "grapheme"
            self._cache[resolved_lang] = _pkg.AfricaPipeline(lang=resolved_lang, output=output)
        return self._cache[resolved_lang]

    @classmethod
    def supported_langs(cls, allow_draft: bool = False) -> List[str]:
        """Return the ISO 639-3 codes africa_g2p ships a usable rule file for.

        A table marked ``llm-draft`` is left out unless *allow_draft* is set.
        Which install is present decides how many that is: measured on
        africa-g2p 0.2.4 it removes none of the 400 tables, and on 0.3.2 it
        removes 352 of 750.
        """
        _pkg = _africa_g2p()
        codes = _pkg.available_languages()
        if allow_draft:
            return list(codes)
        drafts = _draft_codes(_pkg, _installed_version(_pkg))
        return [code for code in codes if code not in drafts]

    @classmethod
    def get_lang(cls, target_lang: str, allow_draft: bool = False) -> str:
        """
        Resolve *target_lang* to a supported africa-g2p rule-file name.

        Two exact lookups, in order, and no fuzzing (africa-g2p keys its rule
        files by name, not by BCP-47 macrolanguage/region mapping, so
        :meth:`BasePhonemizer.match_lang`'s closest-match search does not
        apply):

        1. the whole tag, lowercased, first as written and then with ``_``
           read as ``-``. 11 of the rule
           files carry a region suffix rather than a bare ISO 639-3 code
           (``hau-nigeria``, ``hau-niger``, ``dop-benin``, ``dop-benin2``,
           ``ngb-zaire``, ``ngb-zaire2``, ``sag-congo``,
           ``sag-central_african_republic``, ``sef-cote_d_ivoire``,
           ``sef-cote_d_ivoire2``, ``snk-senegal``), and before this step none
           of them could be reached at all: the primary subtag ``hau`` is not
           a rule file, so Hausa raised.
        2. the primary subtag (``twi-GH`` -> ``twi``).

        A bare code whose only rule files carry region suffixes still raises.
        Picking one region for ``hau`` would be a claim about which variety a
        caller meant, and this wrapper does not make it.

        Raises:
            ValueError: If africa-g2p has no rule file for *target_lang*.
        """
        langs = cls.supported_langs(allow_draft=allow_draft)
        lowered = target_lang.lower()
        # Two of the names keep an underscore of their own
        # (sef-cote_d_ivoire, sag-central_african_republic), so the tag is
        # tried as written before ``_`` is read as ``-``.
        for whole in (lowered, lowered.replace("_", "-")):
            if whole in langs:
                return whole
        key = _primary_subtag(target_lang)
        if key in langs:
            return key
        if not allow_draft and key in cls.supported_langs(allow_draft=True):
            raise ValueError(
                f"africa-g2p: {target_lang!r} has only a rule table this "
                f"install marks {DRAFT_CONFIDENCE!r}, which is generated "
                f"rather than read off a chart. Pass allow_draft=True to use "
                f"it anyway, or install a release whose table for it is "
                f"chart-sourced.")
        raise ValueError(f"africa-g2p: unsupported language {target_lang!r}")

    def phonemize_string(self, text: str, lang: str) -> str:
        resolved = self.get_lang(lang, allow_draft=self._allow_draft)
        return self._engine(resolved).run(text, sep=" ")
