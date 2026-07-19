"""scriptconv — shared script-conversion core for phoonnx, stressonnx,
and orthography2ipa.

Modules
-------
scripts:
    Writing-system identification and metadata.  ISO-15924 script codes,
    character-range detection, ``lang_to_script``, ``normalize_script_tag``,
    ``script_distribution``, ``base_direction``, ``script_to_langs``.
notation:
    Phoneme-notation transcoding.  IPA ↔ ARPABET, IPA ↔ X-SAMPA,
    IPA ↔ Lexique, Buckwalter ↔ Arabic script.
    ``Notation`` enum + ``convert`` facade.
translit:
    Script-level decomposition utilities (Hangul jamo).
    Currently: Hangul → jamo.

Zero runtime dependencies (stdlib only).
"""

from scriptconv.scripts import (
    Script,
    SCRIPT_REGISTRY,
    char_script,
    detect_script,
    script_distribution,
    script_runs,
    base_direction,
    lang_to_script,
    script_to_langs,
    normalize_script_tag,
)
from scriptconv.notation import (
    Notation,
    NotationInfo,
    NOTATION_INFO,
    convert,
    can_convert,
    convert_batch,
    arpa_to_ipa,
    ipa_to_arpa,
    xsampa_to_ipa,
    ipa_to_xsampa,
    buckwalter_to_arabic,
    arabic_to_buckwalter,
    lexique_to_ipa,
    ipa_to_lexique,
    kirshenbaum_to_ipa,
    ipa_to_kirshenbaum,
)
from scriptconv.translit import (
    decompose_hangul,
    hira_to_kana,
    kana_to_hira,
)

__all__ = [
    # scripts
    "Script",
    "SCRIPT_REGISTRY",
    "char_script",
    "detect_script",
    "script_distribution",
    "script_runs",
    "base_direction",
    "lang_to_script",
    "script_to_langs",
    "normalize_script_tag",
    # notation
    "Notation",
    "NotationInfo",
    "NOTATION_INFO",
    "convert",
    "can_convert",
    "convert_batch",
    "arpa_to_ipa",
    "ipa_to_arpa",
    "xsampa_to_ipa",
    "ipa_to_xsampa",
    "buckwalter_to_arabic",
    "arabic_to_buckwalter",
    "lexique_to_ipa",
    "ipa_to_lexique",
    "kirshenbaum_to_ipa",
    "ipa_to_kirshenbaum",
    # translit
    "decompose_hangul",
    "hira_to_kana",
    "kana_to_hira",
]
