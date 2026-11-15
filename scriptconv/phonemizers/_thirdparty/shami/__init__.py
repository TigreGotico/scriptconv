"""Vendored Shami (Levantine Arabic / English code-switching) text front-end.

Ported from hams_tts.text (Apache-2.0) so Levantine G2P is available as a library, e.g. to drive ShamiVITS ONNX models
without requiring the hams-tts package at runtime.
"""

from .frontend import TextFrontend, Utterance, get_default_frontend
from .phoneme_inventory import (
    Inventory,
    Lang,
    SYMBOL_TO_ID,
    ID_TO_SYMBOL,
    VOCAB_SIZE,
    SYMBOL_TO_ID_90,
    ID_TO_SYMBOL_90,
    VOCAB_SIZE_90,
    encode,
    decode,
    get_inventory,
    tokenize_ipa,
)

__all__ = [
    "TextFrontend",
    "Utterance",
    "get_default_frontend",
    "get_inventory",
    "Inventory",
    "Lang",
    "SYMBOL_TO_ID",
    "ID_TO_SYMBOL",
    "VOCAB_SIZE",
    "SYMBOL_TO_ID_90",
    "ID_TO_SYMBOL_90",
    "VOCAB_SIZE_90",
    "encode",
    "decode",
    "tokenize_ipa",
]
