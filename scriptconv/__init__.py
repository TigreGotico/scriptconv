"""scriptconv — shared script-conversion core for phoonnx, stressonnx,
and orthography2ipa.

Modules
-------
scripts:
    Writing-system identification and metadata.  ISO-15924 script codes,
    character-range detection, ``lang_to_script``, ``normalize_script_tag``.
notation:
    Phoneme-notation transcoding.  IPA ↔ ARPABET, IPA ↔ X-SAMPA,
    IPA ↔ Lexique, Buckwalter ↔ Arabic script.
    ``Notation`` enum + ``convert`` facade.
translit:
    Grapheme-to-IPA transliteration for table-driven scripts.
    Currently: Hangul → IPA.

Zero runtime dependencies (stdlib only).
"""

from scriptconv.scripts import (
    Script,
    SCRIPT_REGISTRY,
    char_script,
    detect_script,
    lang_to_script,
    normalize_script_tag,
)
from scriptconv.notation import (
    Notation,
    convert,
    arpa_to_ipa,
    ipa_to_arpa,
    xsampa_to_ipa,
    ipa_to_xsampa,
    buckwalter_to_arabic,
    arabic_to_buckwalter,
    lexique_to_ipa,
    ipa_to_lexique,
)
from scriptconv.translit import hangul_to_ipa

__all__ = [
    # scripts
    "Script",
    "SCRIPT_REGISTRY",
    "char_script",
    "detect_script",
    "lang_to_script",
    "normalize_script_tag",
    # notation
    "Notation",
    "convert",
    "arpa_to_ipa",
    "ipa_to_arpa",
    "xsampa_to_ipa",
    "ipa_to_xsampa",
    "buckwalter_to_arabic",
    "arabic_to_buckwalter",
    "lexique_to_ipa",
    "ipa_to_lexique",
    # translit
    "hangul_to_ipa",
]
