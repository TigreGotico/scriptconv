"""Phonemizer registry: backend lookup, construction, per-language defaults.

Each :class:`~scriptconv.phonemizers.enums.Phonemizer` member maps to
``(module, class name, extra)``. Classes import lazily, and a missing backing
package, scriptconv-copyleft and scriptconv-nonfree included, raises
:class:`ImportError` naming the extra to install.

A language default is eligible only when it can emit the requested alphabet:
Cotovía emits its own notation, so it is the Galician default only for that
notation. ``override=`` always wins, and espeak is the last resort.
"""
from __future__ import annotations

import importlib
from typing import Dict, Optional, Tuple

from scriptconv.phonemizers._moved import COPYLEFT, NONFREE
from scriptconv.phonemizers.base import _primary_subtag
from scriptconv.phonemizers.enums import Alphabet, Phonemizer

__all__ = ["PHONEMIZER_REGISTRY", "LANG_DEFAULTS", "get_phonemizer",
           "get_phonemizer_class", "phonemizer_for_lang"]

_P = Phonemizer
_BASE = "scriptconv.phonemizers"

# member -> (module, class, extra)
PHONEMIZER_REGISTRY: Dict[Phonemizer, Tuple[str, str, Optional[str]]] = {
    _P.UNICODE: (f"{_BASE}.base", "UnicodeCodepointPhonemizer", None),
    _P.GRAPHEMES: (f"{_BASE}.base", "GraphemePhonemizer", None),
    _P.ESPEAK: (f"{COPYLEFT}.mul", "EspeakPhonemizer", "espeak"),
    _P.ESPEAK_LT_ACCENT: (f"{COPYLEFT}.lt", "EspeakLithuanianAccentPhonemizer", "espeak"),
    _P.GRUUT: (f"{_BASE}.mul", "GruutPhonemizer", "gruut"),
    _P.GORUUT: (f"{_BASE}.mul", "GoruutPhonemizer", "goruut"),
    _P.EPITRAN: (f"{_BASE}.mul", "EpitranPhonemizer", "epitran"),
    _P.TRANSPHONE: (f"{COPYLEFT}.mul", "TransphonePhonemizer", "transphone"),
    _P.PHONETISAURUS: (f"{_BASE}.mul", "PhonetisaurusPhonemizer", "phonetisaurus"),
    _P.BYT5: (f"{_BASE}.mul", "ByT5Phonemizer", "byt5"),
    _P.CHARSIU: (f"{_BASE}.mul", "CharsiuPhonemizer", "byt5"),
    _P.MISAKI: (f"{COPYLEFT}.mul", "MisakiPhonemizer", "misaki"),
    _P.MISAKI_EN: (f"{COPYLEFT}.mul", "MisakiEnPhonemizer", "misaki"),
    _P.MISAKI_JA: (f"{COPYLEFT}.mul", "MisakiJaPhonemizer", "misaki"),
    _P.MISAKI_ZH: (f"{COPYLEFT}.mul", "MisakiZhPhonemizer", "misaki"),
    _P.MISAKI_KO: (f"{COPYLEFT}.mul", "MisakiKoPhonemizer", "misaki"),
    _P.MISAKI_VI: (f"{COPYLEFT}.mul", "MisakiViPhonemizer", "misaki"),
    _P.DEEPPHONEMIZER: (f"{_BASE}.en", "DeepPhonemizer", "en-phonemizers"),
    _P.OPENPHONEMIZER: (f"{_BASE}.en", "OpenPhonemizer", "en-phonemizers"),
    _P.G2PEN: (f"{_BASE}.en", "G2PEnPhonemizer", "en-phonemizers"),
    _P.DIZIONE: (f"{_BASE}.dizione", "DizionePhonemizer", "en-phonemizers"),
    _P.LEOKANI: (f"{_BASE}.leokani", "LeokaniPhonemizer", "en-phonemizers"),
    _P.NEMO_IPA: (f"{_BASE}.nemo_ipa", "NemoIpaPhonemizer", "en-phonemizers"),
    _P.KOLOKWA: (f"{_BASE}.lir", "KolokwaPhonemizer", "lir"),
    _P.TUGAPHONE: (f"{_BASE}.pt", "TugaphonePhonemizer", "pt-phonemizers"),
    _P.BARRANQUENHO: (f"{_BASE}.pt", "BarranquenhoPhonemizer", "o2i"),
    _P.MIRANDESE: (f"{_BASE}.mwl", "MirandesePhonemizer", "o2i"),
    _P.COTOVIA: (f"{COPYLEFT}.gl", "CotoviaPhonemizer", "gl"),
    _P.AHOTTS: (f"{COPYLEFT}.eu", "AhoTTSPhonemizer", "eu"),
    _P.EUSKAPHONE: (f"{_BASE}.eu", "EuskaphonePhonemizer", "eu"),
    _P.PHONIKUD: (f"{_BASE}.he", "PhonikudPhonemizer", "he"),
    _P.HEBREW_IPA: (f"{COPYLEFT}.he", "HebrewIPAPhonemizer", "he"),
    _P.TLTK: (f"{COPYLEFT}.th", "TLTKPhonemizer", "th"),
    _P.G2PFA: (f"{COPYLEFT}.fa", "PersianPhonemizer", "fa"),
    _P.VIPHONEME: (f"{NONFREE}.vi", "VIPhonemePhonemizer", "vi"),
    _P.ORTHOGRAPHY2IPA: (f"{_BASE}.o2ipa", "Orthography2IPAPhonemizer", "o2i"),
    _P.AFRICA_G2P: (f"{NONFREE}.africa", "AfricaG2PPhonemizer", "africa"),
    _P.MATOUB_KAB: (f"{_BASE}.ber", "MatoubKabylePhonemizer", None),
    _P.GHANA_G2P: (f"{NONFREE}.ghana", "GhanaG2PPhonemizer", "ghana"),
    _P.OPENJTALK: (f"{_BASE}.ja", "OpenJTaklPhonemizer", "ja-phonemizers"),
    _P.CUTLET: (f"{_BASE}.ja", "CutletPhonemizer", "ja-phonemizers"),
    _P.PYKAKASI: (f"{COPYLEFT}.ja", "PyKakasiPhonemizer", "ja-phonemizers"),
    _P.OPENJTALK_PROSODY: (f"{COPYLEFT}.ja_prosody", "OpenJTalkProsodyPhonemizer", "ja-phonemizers"),
    _P.G2PK: (f"{COPYLEFT}.ko", "G2PKPhonemizer", "ko"),
    _P.KOG2PK: (f"{COPYLEFT}.ko", "KoG2PPhonemizer", "ko"),
    _P.JIEBA: (f"{_BASE}.zh", "JiebaPhonemizer", "zh-phonemizers"),
    _P.F5TTS_CHAR: (f"{_BASE}.f5tts", "F5TTSCharPhonemizer", None),
    _P.F5TTS_PINYIN: (f"{_BASE}.f5tts", "F5TTSPinyinPhonemizer", "zh-phonemizers"),
    _P.G2PC: (f"{_BASE}.zh", "G2pCPhonemizer", "zh-phonemizers"),
    _P.G2PM: (f"{_BASE}.zh", "G2pMPhonemizer", "zh-phonemizers"),
    _P.G2PW: (f"{_BASE}.g2pw", "G2PWPhonemizer", "zh-phonemizers"),
    _P.PYPINYIN: (f"{_BASE}.zh", "PypinyinPhonemizer", "zh-phonemizers"),
    _P.XPINYIN: (f"{_BASE}.zh", "XpinyinPhonemizer", "zh-phonemizers"),
    _P.MANTOQ: (f"{NONFREE}.ar", "MantoqPhonemizer", "ar-phonemizers"),
    _P.HALABI: (f"{NONFREE}.ar", "HalabiPhonemizer", "ar-phonemizers"),
    _P.IQRA: (f"{NONFREE}.ar", "IqraPhonemizer", "ar-phonemizers"),
    _P.ARBTOK: (f"{_BASE}.ar", "ArbtokPhonemizer", "ar-phonemizers"),
    _P.SHAMI: (f"{_BASE}.shami", "ShamiPhonemizer", "shami"),
    _P.VOSK: (f"{_BASE}.ru", "VoskPhonemizer", "phonemizers"),
}


def get_phonemizer_class(phonemizer: Phonemizer):
    """The class of a registry member, imported on first use.

    Raises:
        ImportError: If the backing package is missing; the message names the extra to install.
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
    """An instance of the *phonemizer* backend.

    *model* goes to the constructor's ``model``, ``engine`` or ``register``
    parameter, and *alphabet* to its ``alphabet`` parameter, when it has one.
    A non-empty *model* raises ValueError when the constructor has none of
    those parameters. Other *kwargs* go to the constructor, except
    ``normalizer=`` and ``keep_punctuation=``, which are set on the instance.
    """
    phonemizer = Phonemizer(phonemizer)
    cls = get_phonemizer_class(phonemizer)
    normalizer = kwargs.pop("normalizer", None)
    keep_punctuation = kwargs.pop("keep_punctuation", None)
    if phonemizer in (_P.BYT5, _P.CHARSIU, _P.DEEPPHONEMIZER):
        inst = cls(model, **kwargs)
    else:
        import inspect
        params = inspect.signature(cls.__init__).parameters
        if "alphabet" in params:
            kwargs.setdefault("alphabet", alphabet)
        if model is not None:
            for name in ("model", "engine", "register"):
                if name in params:
                    kwargs.setdefault(name, model)
                    break
            else:
                # Voice configs use an empty string for "no model".
                if model:
                    raise ValueError(
                        f"phonemizer {phonemizer.value!r} cannot take model={model!r}: "
                        f"{cls.__name__} has no model, engine or register parameter")
        inst = cls(**kwargs)
    if normalizer is not None:
        inst.normalizer = normalizer
    if keep_punctuation is not None:
        inst.keep_punctuation = keep_punctuation
    return inst


# The alphabets a language default can emit; a backend not listed emits IPA.
_EMITS: Dict[Phonemizer, Tuple[Alphabet, ...]] = {
    _P.ARBTOK: (Alphabet.IPA,),
    _P.EUSKAPHONE: (Alphabet.IPA,),
    _P.MIRANDESE: (Alphabet.IPA,),
    _P.TUGAPHONE: (Alphabet.IPA,),
    _P.PHONIKUD: (Alphabet.IPA,),
    _P.COTOVIA: (Alphabet.COTOVIA,),
    _P.VOSK: (Alphabet.VOSK,),
    _P.ESPEAK: (Alphabet.IPA,),
}

# language -> candidate backends in order; the first that emits the requested alphabet wins
LANG_DEFAULTS: Dict[str, Tuple[Phonemizer, ...]] = {
    "ar": (_P.ARBTOK,),
    "eu": (_P.EUSKAPHONE,),
    "mwl": (_P.MIRANDESE,),
    "pt": (_P.TUGAPHONE,),
    "he": (_P.PHONIKUD,),
    "lir": (_P.KOLOKWA,),
    "gl": (_P.COTOVIA, _P.ORTHOGRAPHY2IPA, _P.ESPEAK),
    "ru": (_P.VOSK, _P.ORTHOGRAPHY2IPA, _P.ESPEAK),
}

# Languages whose entry is exhaustive: Arabic never falls through to orthography2ipa or espeak.
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
    """The default phonemizer for *lang*.

    The first of: *override*; the first :data:`LANG_DEFAULTS` candidate that
    emits *alphabet*; orthography2ipa when it supports *lang* and *alphabet*
    is IPA; espeak. Arabic never leaves its :data:`LANG_DEFAULTS` entry.

    Raises:
        ValueError: If no candidate of an exhaustive entry emits *alphabet*.
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
    """``phonemizer_for_lang(...).phonemize_string(text, lang)``.

    Each call builds a new backend; keep one from :func:`phonemizer_for_lang` to phonemize repeatedly.
    """
    return phonemizer_for_lang(lang, alphabet, override, model,
                               **kwargs).phonemize_string(text, lang)


def register(graph) -> None:
    """Add the ``text -> ipa`` and ``text-diacritized -> ipa`` edges to *graph*.

    The edges phonemize with the default backend for the ``lang=`` context
    key, or the ``override=`` one, and take ``phonemizer_model=``. The
    :data:`scriptconv.graph.DEFAULT_GRAPH` holds no phonemizer edge.

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
        return phonemizer_for_lang(lang, Alphabet.IPA, override,
                                   phonemizer_model).phonemize_string(text, lang)

    graph.register(Edge("text", "ipa", _text_to_ipa, lossless=False))
    graph.register(Edge("text-diacritized", "ipa", _text_to_ipa, lossless=False))
