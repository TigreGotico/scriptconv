"""Phonemizer wrappers: the :class:`BasePhonemizer` contract, the enums and the lazy registry.

Backing engines are optional extras; a missing one raises :class:`ImportError`
naming the extra to install. The wrappers under a copyleft or a non-commercial
licence are in scriptconv-copyleft and scriptconv-nonfree.
"""
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.base import (
    BasePhonemizer,
    FrontendError,
    GraphemePhonemizer,
    MissingLanguageError,
    ModelUnavailableError,
    PhonemizerIdentity,
    Segment,
    StageError,
    UnicodeCodepointPhonemizer,
    UnreadTextError,
    UnsupportedLanguageError,
    TextChunks,
    RawPhonemizedChunks,
    PhonemizedChunks,
)
from scriptconv.phonemizers.registry import (
    PHONEMIZER_REGISTRY,
    LANG_DEFAULTS,
    get_phonemizer,
    get_phonemizer_class,
    phonemizer_for_lang,
    phonemize,
    register,
)

__all__ = [
    "Alphabet",
    "Phonemizer",
    "BasePhonemizer",
    "FrontendError",
    "GraphemePhonemizer",
    "MissingLanguageError",
    "ModelUnavailableError",
    "PhonemizerIdentity",
    "Segment",
    "StageError",
    "UnicodeCodepointPhonemizer",
    "UnreadTextError",
    "UnsupportedLanguageError",
    "TextChunks",
    "RawPhonemizedChunks",
    "PhonemizedChunks",
    "PHONEMIZER_REGISTRY",
    "LANG_DEFAULTS",
    "get_phonemizer",
    "get_phonemizer_class",
    "phonemizer_for_lang",
    "phonemize",
    "register",
]
