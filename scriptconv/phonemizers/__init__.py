"""Phonemizer wrappers — see :mod:`scriptconv.phonemizers.base` for the thesis.

Public surface: the :class:`BasePhonemizer` contract, the ``Alphabet``/
``Phonemizer`` enums, the lazy registry (``get_phonemizer``,
``phonemizer_for_lang``), and the per-language wrapper modules.  Backing
engines are optional extras; a missing one raises :class:`ImportError`
naming the extra to install.
"""
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.base import (
    BasePhonemizer,
    GraphemePhonemizer,
    MissingLanguageError,
    UnicodeCodepointPhonemizer,
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
    "GraphemePhonemizer",
    "MissingLanguageError",
    "UnicodeCodepointPhonemizer",
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
