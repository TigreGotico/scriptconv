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
    # normalizer/phonikud_model are plain BasePhonemizer attributes; set them
    # after construction so wrapper __init__ signatures stay untouched
    normalizer = kwargs.pop("normalizer", None)
    phonikud_model = kwargs.pop("phonikud_model", None)
    if phonemizer in (_P.BYT5, _P.CHARSIU, _P.DEEPPHONEMIZER):
        inst = cls(model, **kwargs)
    else:
        import inspect
        params = inspect.signature(cls.__init__).parameters
        if "alphabet" in params:
            kwargs.setdefault("alphabet", alphabet)
        inst = cls(**kwargs)
    if normalizer is not None:
        inst.normalizer = normalizer
    if phonikud_model is not None:
        inst.phonikud_model = phonikud_model
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
    # Arabic IPA always goes through arbtok (hard org rule)
    "ar": (_P.ARBTOK,),
    "eu": (_P.EUSKAPHONE,),
    "mwl": (_P.MIRANDESE,),
    "pt": (_P.TUGAPHONE,),
    "he": (_P.PHONIKUD,),
    "gl": (_P.COTOVIA, _P.ESPEAK),
}


def phonemizer_for_lang(lang: str, alphabet: Alphabet = Alphabet.IPA,
                        override: Optional[Phonemizer] = None,
                        model: Optional[str] = None, **kwargs):
    """Construct the default phonemizer for *lang* (or the override).

    Candidates from :data:`LANG_DEFAULTS` are filtered by the alphabet they
    can emit; espeak is the universal fallback.
    """
    if override is not None:
        return get_phonemizer(override, alphabet, model, **kwargs)
    key = lang.replace("_", "-").split("-")[0].lower()
    for candidate in LANG_DEFAULTS.get(key, ()):
        if alphabet in _EMITS.get(candidate, (Alphabet.IPA,)):
            return get_phonemizer(candidate, alphabet, model, **kwargs)
    return get_phonemizer(_P.ESPEAK, alphabet, model, **kwargs)
