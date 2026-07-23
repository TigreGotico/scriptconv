"""Phonemizer registry: backend lookup, construction, per-language defaults.

The registry is data: each :class:`~scriptconv.phonemizers.enums.Phonemizer`
member maps to ``(module, class name, extra)``.  Classes import lazily — a
missing backing package raises :class:`ImportError` naming the extra to
install, never a silent gap (a meta-test iterates every member).

Language defaults are org-informed and **filtered by the requested output
alphabet**: a default is only eligible when the wrapper can emit that
alphabet (Cotovía emits its own notation, not IPA, so it is the Galician
default only when Cotovía notation is requested).  ``override=`` always
wins.  The fallback for any language is espeak — the espeak-ng subprocess
(or the pure-Python espyak port when the binary is absent).
"""
from __future__ import annotations

import importlib
from typing import Dict, Optional, Tuple

from scriptconv.phonemizers.base import _primary_subtag
from scriptconv.phonemizers.enums import Alphabet, Phonemizer

__all__ = ["PHONEMIZER_REGISTRY", "LANG_DEFAULTS", "get_phonemizer",
           "get_phonemizer_class", "phonemizer_for_lang"]

_P = Phonemizer
_BASE = "scriptconv.phonemizers"

# member -> (module, class, extra) — the single source of truth
PHONEMIZER_REGISTRY: Dict[Phonemizer, Tuple[str, str, Optional[str]]] = {
    _P.UNICODE: (f"{_BASE}.base", "UnicodeCodepointPhonemizer", None),
    _P.GRAPHEMES: (f"{_BASE}.base", "GraphemePhonemizer", None),
    _P.ESPEAK: (f"{_BASE}.mul", "EspeakPhonemizer", "espeak"),
    _P.GRUUT: (f"{_BASE}.mul", "GruutPhonemizer", "gruut"),
    _P.GORUUT: (f"{_BASE}.mul", "GoruutPhonemizer", "goruut"),
    _P.EPITRAN: (f"{_BASE}.mul", "EpitranPhonemizer", "epitran"),
    _P.TRANSPHONE: (f"{_BASE}.mul", "TransphonePhonemizer", "transphone"),
    _P.BYT5: (f"{_BASE}.mul", "ByT5Phonemizer", "byt5"),
    _P.CHARSIU: (f"{_BASE}.mul", "CharsiuPhonemizer", "byt5"),
    _P.MISAKI: (f"{_BASE}.mul", "MisakiPhonemizer", "misaki"),
    _P.MISAKI_EN: (f"{_BASE}.mul", "MisakiEnPhonemizer", "misaki"),
    _P.MISAKI_JA: (f"{_BASE}.mul", "MisakiJaPhonemizer", "misaki"),
    _P.MISAKI_ZH: (f"{_BASE}.mul", "MisakiZhPhonemizer", "misaki"),
    _P.MISAKI_KO: (f"{_BASE}.mul", "MisakiKoPhonemizer", "misaki"),
    _P.MISAKI_VI: (f"{_BASE}.mul", "MisakiViPhonemizer", "misaki"),
    _P.DEEPPHONEMIZER: (f"{_BASE}.en", "DeepPhonemizer", "en-phonemizers"),
    _P.OPENPHONEMIZER: (f"{_BASE}.en", "OpenPhonemizer", "en-phonemizers"),
    _P.G2PEN: (f"{_BASE}.en", "G2PEnPhonemizer", "en-phonemizers"),
    _P.TUGAPHONE: (f"{_BASE}.pt", "TugaphonePhonemizer", "pt-phonemizers"),
    _P.BARRANQUENHO: (f"{_BASE}.pt", "BarranquenhoPhonemizer", "pt-phonemizers"),
    _P.MIRANDESE: (f"{_BASE}.mwl", "MirandesePhonemizer", "mwl"),
    _P.COTOVIA: (f"{_BASE}.gl", "CotoviaPhonemizer", "gl"),
    _P.AHOTTS: (f"{_BASE}.eu", "AhoTTSPhonemizer", "eu"),
    _P.EUSKAPHONE: (f"{_BASE}.eu", "EuskaphonePhonemizer", "eu"),
    _P.PHONIKUD: (f"{_BASE}.he", "PhonikudPhonemizer", "he"),
    _P.G2PFA: (f"{_BASE}.fa", "PersianPhonemizer", "fa"),
    _P.VIPHONEME: (f"{_BASE}.vi", "VIPhonemePhonemizer", "vi"),
    _P.ORTHOGRAPHY2IPA: (f"{_BASE}.o2ipa", "Orthography2IPAPhonemizer", "o2i"),
    # ported in the CJK/AR stage; registered here so no member is silently
    # unmapped — resolution raises ImportError naming the pending extra
    _P.OPENJTALK: (f"{_BASE}.ja", "OpenJTaklPhonemizer", "ja-phonemizers"),
    _P.CUTLET: (f"{_BASE}.ja", "CutletPhonemizer", "ja-phonemizers"),
    _P.PYKAKASI: (f"{_BASE}.ja", "PyKakasiPhonemizer", "ja-phonemizers"),
    _P.G2PK: (f"{_BASE}.ko", "G2PKPhonemizer", "ko"),
    _P.KOG2PK: (f"{_BASE}.ko", "KoG2PPhonemizer", "ko"),
    _P.JIEBA: (f"{_BASE}.zh", "JiebaPhonemizer", "zh-phonemizers"),
    _P.G2PC: (f"{_BASE}.zh", "G2pCPhonemizer", "zh-phonemizers"),
    _P.G2PM: (f"{_BASE}.zh", "G2pMPhonemizer", "zh-phonemizers"),
    _P.PYPINYIN: (f"{_BASE}.zh", "PypinyinPhonemizer", "zh-phonemizers"),
    _P.XPINYIN: (f"{_BASE}.zh", "XpinyinPhonemizer", "zh-phonemizers"),
    _P.MANTOQ: (f"{_BASE}.ar", "MantoqPhonemizer", "ar-phonemizers"),
    _P.ARBTOK: (f"{_BASE}.ar", "ArbtokPhonemizer", "ar-phonemizers"),
    _P.SHAMI: (f"{_BASE}.shami", "ShamiPhonemizer", "shami"),
}


def get_phonemizer_class(phonemizer: Phonemizer):
    """Resolve a registry member to its class, importing lazily.

    Raises :class:`ImportError` naming the extra to install when the backing
    package is missing.
    """
    module, cls_name, extra = PHONEMIZER_REGISTRY[Phonemizer(phonemizer)]
    try:
        return getattr(importlib.import_module(module), cls_name)
    except ImportError as e:
        hint = f"`pip install scriptconv[{extra}]`" if extra else str(e)
        raise ImportError(
            f"phonemizer {Phonemizer(phonemizer).value!r} needs a missing "
            f"backing package — install with {hint}") from e


def get_phonemizer(phonemizer: Phonemizer,
                   alphabet: Alphabet = Alphabet.IPA,
                   model: Optional[str] = None,
                   **kwargs):
    """Construct a phonemizer instance for the requested backend.

    ``model`` is forwarded to model-backed phonemizers (ByT5/Charsiu/
    DeepPhonemizer); ``alphabet`` to those with a selectable output alphabet.
    Extra ``kwargs`` (e.g. ``normalizer=``) pass to the constructor.
    """
    phonemizer = Phonemizer(phonemizer)
    cls = get_phonemizer_class(phonemizer)
    # normalizer is a plain BasePhonemizer attribute; set it after
    # construction so wrapper __init__ signatures stay untouched
    normalizer = kwargs.pop("normalizer", None)
    if phonemizer in (_P.BYT5, _P.CHARSIU, _P.DEEPPHONEMIZER):
        inst = cls(model, **kwargs)
    else:
        import inspect
        params = inspect.signature(cls.__init__).parameters
        if "alphabet" in params:
            kwargs.setdefault("alphabet", alphabet)
        if model is not None:
            # backends name their variant/model selector differently
            # (AhoTTS: engine=, arbtok: register=, ...) — forward to whichever
            # parameter the constructor declares
            for name in ("model", "engine", "register"):
                if name in params:
                    kwargs.setdefault(name, model)
                    break
        inst = cls(**kwargs)
    if normalizer is not None:
        inst.normalizer = normalizer
    return inst


# language -> ordered candidate backends; first whose emittable alphabets
# include the requested one wins.  The alphabets each candidate can emit:
_EMITS: Dict[Phonemizer, Tuple[Alphabet, ...]] = {
    _P.ARBTOK: (Alphabet.IPA,),
    _P.EUSKAPHONE: (Alphabet.IPA,),
    _P.MIRANDESE: (Alphabet.IPA,),
    _P.TUGAPHONE: (Alphabet.IPA,),
    _P.PHONIKUD: (Alphabet.IPA,),
    _P.COTOVIA: (Alphabet.COTOVIA,),
    _P.ESPEAK: (Alphabet.IPA,),
}

LANG_DEFAULTS: Dict[str, Tuple[Phonemizer, ...]] = {
    # Arabic IPA always goes through arbtok (hard org rule — never falls
    # through to orthography2ipa or espeak)
    "ar": (_P.ARBTOK,),
    "eu": (_P.EUSKAPHONE,),
    "mwl": (_P.MIRANDESE,),
    "pt": (_P.TUGAPHONE,),
    "he": (_P.PHONIKUD,),
    "gl": (_P.COTOVIA, _P.ORTHOGRAPHY2IPA, _P.ESPEAK),
}

# Languages whose explicit entry is exhaustive: no generic fallback beyond it.
_NO_GENERIC_FALLBACK = {"ar"}


def _o2i_supports(lang: str) -> bool:
    """True when orthography2ipa is installed and has a spec for *lang*."""
    try:
        from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
        Orthography2IPAPhonemizer.get_lang(lang)
        return True
    except (ImportError, ValueError):
        return False


def phonemizer_for_lang(lang: str, alphabet: Alphabet = Alphabet.IPA,
                        override: Optional[Phonemizer] = None,
                        model: Optional[str] = None, **kwargs):
    """Construct the default phonemizer for *lang* (or the override).

    Resolution order — in-house engines first:

    1. ``override=`` when given;
    2. the language's explicit :data:`LANG_DEFAULTS` chain, filtered by the
       alphabet each candidate can emit;
    3. :data:`~Phonemizer.ORTHOGRAPHY2IPA` when orthography2ipa supports the
       language (the usual default);
    4. espeak as the last resort.

    Languages in the no-fallback set (Arabic) never leave their explicit
    chain — a missing arbtok raises rather than silently degrading.
    """
    if override is not None:
        return get_phonemizer(override, alphabet, model, **kwargs)
    key = _primary_subtag(lang)
    explicit = LANG_DEFAULTS.get(key, ())
    for candidate in explicit:
        if alphabet in _EMITS.get(candidate, (Alphabet.IPA,)):
            return get_phonemizer(candidate, alphabet, model, **kwargs)
    if key in _NO_GENERIC_FALLBACK:
        raise ValueError(
            f"no eligible phonemizer for {lang!r} with alphabet "
            f"{alphabet.value!r}: the explicit chain "
            f"{[c.value for c in explicit]} is exhaustive for this language")
    if alphabet == Alphabet.IPA and _o2i_supports(lang):
        return get_phonemizer(_P.ORTHOGRAPHY2IPA, alphabet, model, **kwargs)
    return get_phonemizer(_P.ESPEAK, alphabet, model, **kwargs)


def phonemize(text: str, lang: str, alphabet: Alphabet = Alphabet.IPA,
              override: Optional[Phonemizer] = None,
              model: Optional[str] = None, **kwargs) -> str:
    """One-call facade: phonemize *text* with the language's default backend.

    Equivalent to ``phonemizer_for_lang(...).phonemize_string(text, lang)``.
    Construct the phonemizer yourself when phonemizing repeatedly — backends
    cache models/dictionaries per instance.
    """
    return phonemizer_for_lang(lang, alphabet, override, model,
                               **kwargs).phonemize_string(text, lang)


def register(graph) -> None:
    """Opt-in graph integration: add the phonemization edge to *graph*.

    Adds the ``"text"`` representation — meaningful only with ``lang=``
    routing context, and present only in graphs that opted in (the
    :data:`scriptconv.graph.DEFAULT_GRAPH` stays orthography-only by
    design) — and one dispatching ``text -> ipa`` edge that resolves the
    per-language default (honouring an ``override=`` context key). It also
    accepts already-diacritized input via a ``"text-diacritized" -> "ipa"``
    edge (the same phonemization; pair with :func:`scriptconv.diacritics.register`).

    Usage::

        from scriptconv.graph import DEFAULT_GRAPH
        from scriptconv import phonemizers
        g = DEFAULT_GRAPH.extend(phonemizers.register)
        g.convert("bom dia", "text", "ipa", lang="pt")
    """
    from scriptconv.graph import Edge

    def _text_to_ipa(text: str, lang: str = "und",
                     override: Optional[Phonemizer] = None,
                     phonemizer_model: Optional[str] = None, **_):
        # phonemizer_model is the model knob for this (phonemizer) edge —
        # forwarded to model-backed phonemizers (ByT5/Charsiu/…); parallel to
        # diacritizer_model on the text -> text-diacritized edge.
        return phonemizer_for_lang(lang, Alphabet.IPA, override,
                                   phonemizer_model).phonemize_string(text, lang)

    graph.register(Edge("text", "ipa", _text_to_ipa, lossless=False))
    graph.register(Edge("text-diacritized", "ipa", _text_to_ipa, lossless=False))
