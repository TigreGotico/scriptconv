"""Phonemizer wrappers — see :mod:`scriptconv.phonemizers.base` for the thesis.

Public surface: the :class:`BasePhonemizer` contract, the ``Alphabet``/
``Phonemizer`` enums, the lazy registry (``get_phonemizer``,
``phonemizer_for_lang``), and the per-language wrapper modules.  Backing
engines are optional extras; a missing one raises :class:`ImportError`
naming the extra to install.  The wrappers under a copyleft or a
non-commercial licence are in the scriptconv-copyleft and scriptconv-nonfree
packages (see :mod:`scriptconv.phonemizers._moved`); the registry imports
them from there.
"""
from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.base import (
    BasePhonemizer,
    FrontendError,
    GraphemePhonemizer,
    MissingLanguageError,
    ModelUnavailableError,
    PhonemizerIdentity,
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

__getattr__ = deprecated_getattr(__name__)
