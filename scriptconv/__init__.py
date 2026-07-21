"""scriptconv — a zero-dependency core for written-script operations.

Script identification and metadata, phoneme-notation transcoding, and
orthographic decomposition — no phonemization.

Modules
-------
scripts:
    Writing-system identification and metadata.  ISO-15924 script codes,
    character-range detection, ``lang_to_script``, ``normalize_script_tag``,
    ``script_distribution``, ``script_runs``, ``base_direction``,
    ``script_to_langs``.
notation:
    Phoneme-notation transcoding.  IPA ↔ ARPABET, IPA ↔ X-SAMPA,
    IPA ↔ Lexique, IPA ↔ Kirshenbaum, Buckwalter ↔ Arabic script.
    ``Notation`` enum, ``convert`` facade, ``NOTATION_INFO`` fidelity registry.
translit:
    Script-level decomposition and transliteration (Hangul → jamo,
    Hiragana ↔ Katakana).
readings:
    Dictionary-backed respelling (Japanese kanji → kana via the ``ja``
    extra; Chinese hanzi → pinyin/bopomofo via the ``zh`` extra).
cangjie:
    Hanzi → Cangjie5 input codes (shape decomposition, vendored table).
graph:
    Conversion-graph engine: representations (notations and orthographies)
    as nodes, registered transforms as edges, lossless-preferring routing.
    External packages extend graph instances explicitly.
conventions:
    Orthographic conventions — script-scoped decorations orthogonal to
    identity (tashkeel, niqqud, wakachigaki, pinyin tone spelling…).
    Scripts are nodes; conventions are parameters, never nodes.

Zero required runtime dependencies (stdlib only); the readings module
needs the optional ``ja``/``zh`` extras.
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
    cotovia_to_ipa,
    ipa_to_cotovia,
    rfe_to_ipa,
    ipa_to_rfe,
    looks_like_ipa,
)
from scriptconv.translit import (
    decompose_hangul,
    hira_to_kana,
    kana_to_hira,
)
from scriptconv.readings import (
    ReadingToken,
    tokens,
    to_hiragana,
    to_katakana,
    to_pinyin,
    to_bopomofo,
)
from scriptconv.conventions import (
    Convention,
    Transition,
    CONVENTION_REGISTRY,
    conventions_for,
    restyle,
    strip,
    apply,
    detect as detect_convention,
)
from scriptconv.graph import (
    Representation,
    Edge,
    ConversionGraph,
    DEFAULT_GRAPH,
    REPRESENTATIONS,
)
from scriptconv.cangjie import (
    cangjie_code,
    to_cangjie,
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
    "cotovia_to_ipa",
    "ipa_to_cotovia",
    "rfe_to_ipa",
    "ipa_to_rfe",
    "looks_like_ipa",
    # translit
    "decompose_hangul",
    "hira_to_kana",
    "kana_to_hira",
    # readings (dictionary-backed, needs scriptconv[ja])
    "ReadingToken",
    "tokens",
    "to_hiragana",
    "to_katakana",
    # conventions (orthographic decorations, orthogonal to script identity)
    "Convention",
    "Transition",
    "CONVENTION_REGISTRY",
    "conventions_for",
    "restyle",
    "strip",
    "apply",
    "detect_convention",
    # graph (conversion routing engine over representations)
    "Representation",
    "Edge",
    "ConversionGraph",
    "DEFAULT_GRAPH",
    "REPRESENTATIONS",
    # cangjie (vendored Cangjie5 table)
    "cangjie_code",
    "to_cangjie",
    "to_pinyin",
    "to_bopomofo",
]
