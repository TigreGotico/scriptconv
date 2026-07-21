"""Tests for scriptconv.notation."""
import pytest
from scriptconv.notation import (
    Notation,
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
    _ARPA_TO_IPA,
)


# ---------------------------------------------------------------------------
# ARPABET → IPA  (spot gold checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("arpa, expected_ipa", [
    ("HH AH0 L OW1", "həloʊ"),
    ("P IY1 T", "pit"),
    ("B AY1", "baɪ"),
    ("SH OW1", "ʃoʊ"),
    ("JH AH1 S T", "dʒʌst"),
    ("TH AE1 NG K S", "θæŋks"),
    ("NG", "ŋ"),
    ("AH0", "ə"),
    ("AH1", "ʌ"),
    ("EY1", "eɪ"),
    ("OY1", "ɔɪ"),
    ("AW1", "aʊ"),
    ("ER0", "ɜr"),
])
def test_arpa_to_ipa_gold(arpa, expected_ipa):
    assert arpa_to_ipa(arpa) == expected_ipa


def test_arpa_to_ipa_unknown_passthrough():
    result = arpa_to_ipa("UNKNOWN")
    assert "UNKNOWN" in result


def test_arpa_g_is_canonical_script_g():
    # ARPA "G" must emit script ɡ (U+0261), the canonical IPA used by the
    # X-SAMPA and Lexique tables — not ASCII "g" (U+0067).
    out = arpa_to_ipa("G")
    assert out == "ɡ"
    assert ord(out) == 0x0261


@pytest.mark.parametrize("ipa_g", ["ɡ", "g"])  # script U+0261 and ASCII U+0067
def test_ipa_g_both_spellings_to_arpa(ipa_g):
    assert ipa_to_arpa(ipa_g) == "G"


def test_cross_converter_g_xsampa_to_arpa():
    # Regression: voiced velar stop must survive X-SAMPA → ARPA via IPA hub.
    from scriptconv import convert
    assert convert("g", "x-sampa", "arpa") == "G"


@pytest.mark.parametrize("ipa, expected", [
    ("iː", "IY"),    # length mark (U+02D0, Lm) is not a standalone phoneme
    ("ɑ̃", "AA"),     # combining tilde (U+0303, Mn) qualifies the vowel
    ("ˈhʌ", "HH AH"),  # primary-stress modifier letter dropped, not "?"
])
def test_ipa_to_arpa_drops_diacritics_not_phonemes(ipa, expected):
    assert ipa_to_arpa(ipa) == expected


def test_ipa_to_arpa_still_flags_real_unknown_phoneme():
    # A genuine out-of-inventory phoneme (ɸ, Ll) must still surface as unknown.
    assert ipa_to_arpa("ɸ") == "?"


def test_buckwalter_shadda_round_trips_to_canonical_tilde():
    from scriptconv import arabic_to_buckwalter, buckwalter_to_arabic
    # Standard Buckwalter shadda "~" must survive a round-trip (not become "^").
    assert arabic_to_buckwalter(buckwalter_to_arabic("Al~a")) == "Al~a"


# ---------------------------------------------------------------------------
# IPA → ARPABET  (spot gold checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected_arpa", [
    ("p", "P"),
    ("b", "B"),
    ("t", "T"),
    ("d", "D"),
    ("k", "K"),
    ("ŋ", "NG"),
    ("ʃ", "SH"),
    ("ʒ", "ZH"),
    ("θ", "TH"),
    ("ð", "DH"),
    ("ʔ", "Q"),
    ("ə", "AX"),  # AX maps to ə; AH0 also maps to ə but AX is inserted first
])
def test_ipa_to_arpa_gold(ipa, expected_arpa):
    result = ipa_to_arpa(ipa)
    assert result == expected_arpa


# ---------------------------------------------------------------------------
# Round-trip ARPA → IPA → ARPA
# ---------------------------------------------------------------------------

_ROUND_TRIP_ARPA = [
    "P", "B", "T", "D", "K",
    "M", "N", "NG", "F", "V",
    "TH", "DH", "S", "Z", "SH", "ZH", "HH",
    "CH", "JH", "W", "Y", "R", "L", "Q",
]


@pytest.mark.parametrize("arpa", _ROUND_TRIP_ARPA)
def test_arpa_ipa_arpa_round_trip(arpa):
    ipa = arpa_to_ipa(arpa)
    back = ipa_to_arpa(ipa)
    assert back == arpa, f"Round-trip failed: {arpa} → {ipa} → {back}"


# ---------------------------------------------------------------------------
# X-SAMPA → IPA  (spot gold checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("xs, expected_ipa", [
    ("S", "ʃ"),
    ("Z", "ʒ"),
    ("@", "ə"),
    ("E", "ɛ"),
    ("I", "ɪ"),
    ("A", "ɑ"),
    ("O", "ɔ"),
    ("N", "ŋ"),
    ("tS", "tʃ"),
    ("dZ", "dʒ"),
    ('"', "ˈ"),
    (":", "ː"),
])
def test_xsampa_to_ipa_gold(xs, expected_ipa):
    assert xsampa_to_ipa(xs) == expected_ipa


# ---------------------------------------------------------------------------
# IPA → X-SAMPA  (spot gold checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected_xs", [
    ("ʃ", "S"),
    ("ʒ", "Z"),
    ("ə", "@"),
    ("ŋ", "N"),
    ("ɪ", "I"),
    ("ɔ", "O"),
    ("ɑ", "A"),
    ("ɛ", "E"),
    ("ˈ", '"'),
    ("ː", ":"),
])
def test_ipa_to_xsampa_gold(ipa, expected_xs):
    assert ipa_to_xsampa(ipa) == expected_xs


# ---------------------------------------------------------------------------
# X-SAMPA round-trip  (IPA → X-SAMPA → IPA)
# ---------------------------------------------------------------------------

_ROUND_TRIP_IPA = [
    "p", "b", "t", "d", "k", "m", "n", "f", "v", "s", "z",
    "ʃ", "ʒ", "θ", "ð", "ŋ", "ɪ", "ʊ", "ɔ", "ɑ", "ɛ", "ə",
]


@pytest.mark.parametrize("ipa", _ROUND_TRIP_IPA)
def test_ipa_xsampa_ipa_round_trip(ipa):
    xs = ipa_to_xsampa(ipa)
    back = xsampa_to_ipa(xs)
    assert back == ipa, f"Round-trip failed: {ipa!r} → {xs!r} → {back!r}"


# ---------------------------------------------------------------------------
# Buckwalter ↔ Arabic script  (spot gold checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bw, arabic", [
    ("A", "ا"),
    ("b", "ب"),
    ("m", "م"),
    ("r", "ر"),
    ("H", "ح"),
    ("l", "ل"),
    ("w", "و"),
    ("n", "ن"),
    ("h", "ه"),
    ("y", "ي"),
    ("k", "ك"),
    ("t", "ت"),
])
def test_buckwalter_to_arabic_gold(bw, arabic):
    assert buckwalter_to_arabic(bw) == arabic


@pytest.mark.parametrize("bw, arabic", [
    ("mrHbA", "مرحبا"),   # Ar: مرحبا but H→ح, b→ب, A→ا
])
def test_buckwalter_word(bw, arabic):
    result = buckwalter_to_arabic(bw)
    assert result == arabic


# ---------------------------------------------------------------------------
# Buckwalter round-trip
# ---------------------------------------------------------------------------

_ROUND_TRIP_BW = list("AbtjHxdrzsfqklmnhwy")


@pytest.mark.parametrize("bw_char", _ROUND_TRIP_BW)
def test_buckwalter_arabic_buckwalter_round_trip(bw_char):
    arabic = buckwalter_to_arabic(bw_char)
    back = arabic_to_buckwalter(arabic)
    assert back == bw_char, f"Round-trip failed: {bw_char!r} → {arabic!r} → {back!r}"


# ---------------------------------------------------------------------------
# convert() facade
# ---------------------------------------------------------------------------

def test_convert_arpa_to_ipa():
    assert convert("HH AH0 L OW1", "arpa", "ipa") == "həloʊ"


def test_convert_ipa_to_arpa():
    result = convert("ŋ", "ipa", "arpa")
    assert result == "NG"


def test_convert_xsampa_to_ipa():
    assert convert("S", "x-sampa", "ipa") == "ʃ"


def test_convert_ipa_to_xsampa():
    assert convert("ʃ", "ipa", "x-sampa") == "S"


def test_convert_buckwalter_to_arabic():
    assert convert("A", "buckwalter", "arabic") == "ا"


def test_convert_arabic_to_buckwalter():
    assert convert("ا", "arabic", "buckwalter") == "A"


def test_convert_arpa_to_xsampa_via_ipa():
    result = convert("NG", "arpa", "x-sampa")
    assert result == "N"


def test_convert_identity():
    assert convert("hello", "ipa", "ipa") == "hello"


def test_convert_notation_enum():
    assert convert("S", Notation.XSAMPA, Notation.IPA) == "ʃ"


def test_convert_unsupported_raises():
    with pytest.raises(ValueError):
        convert("ا", "arabic", "ipa")


# ---------------------------------------------------------------------------
# ARPABET edge cases — stress round-trips and unknown-symbol flagging
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("arpa, expected_ipa", [
    ("AH0", "ə"),       # AH0 special-case → schwa
    ("AH1", "ʌ"),       # stressed AH → ʌ
    ("AH2", "ʌ"),       # secondary stress AH
    ("EL", "ɫ̩"),       # syllabic l
    ("EM", "m̩"),        # syllabic m
    ("EN", "n̩"),        # syllabic n
    ("AX", "ə"),        # AX = schwa (CMU variant)
    ("AXR", "ər"),      # r-coloured schwa
])
def test_arpa_to_ipa_edge_cases(arpa, expected_ipa):
    assert arpa_to_ipa(arpa) == expected_ipa


def test_ipa_to_arpa_flags_unknown():
    """Symbols outside the ARPABET table are replaced by '?'."""
    result = ipa_to_arpa("ɸ")
    assert result == "?"


def test_ipa_to_arpa_drop_unknown():
    """unknown='' silently drops symbols outside the table."""
    result = ipa_to_arpa("ɸ", unknown="")
    assert result == ""


def test_arpa_stress_round_trip():
    """Stress-stripped ARPA → IPA → ARPA round-trip for vowels with digits."""
    for base in ("AH", "IY", "UW", "EH", "IH", "UH", "AE", "AO", "AA",
                 "EY", "AY", "OW", "AW", "OY", "ER"):
        for digit in ("0", "1", "2"):
            token = base + digit
            if token == "AH0":
                continue  # schwa maps to AX in reverse; known asymmetry
            ipa = arpa_to_ipa(token)
            back = ipa_to_arpa(ipa)
            # back may be the base form (no digit) — that is the expected lossy behaviour
            assert base in back, f"Round-trip lost base: {token} → {ipa} → {back}"


# ---------------------------------------------------------------------------
# X-SAMPA edge cases — multi-char longest-first matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("xs, expected_ipa", [
    ("tS", "tʃ"),        # affricate: must not split as t + S
    ("dZ", "dʒ"),        # affricate: must not split as d + Z
    ("r\\", "ɹ"),        # r-backslash before plain r
    ("ts`", "ʈ͡ʂ"),      # retro affricate: longest first
    ("@\\", "ɘ"),        # @-backslash before @
    ("@`", "ɚ"),         # @-backtick before @
    ("}", "ʉ"),          # close-mid central rounded
    ("{", "æ"),          # near-open front unrounded
    ("N\\", "ɴ"),        # uvular nasal before N=ŋ
    ("G\\", "ɢ"),        # voiced uvular stop before G=ɣ
])
def test_xsampa_longest_first(xs, expected_ipa):
    assert xsampa_to_ipa(xs) == expected_ipa


@pytest.mark.parametrize("ipa, expected_xs", [
    ("tʃ", "tS"),
    ("dʒ", "dZ"),
    ("ɹ", "r\\"),
    ("æ", "{"),
    ("ʉ", "}"),
    ("ŋ", "N"),
])
def test_ipa_to_xsampa_edge(ipa, expected_xs):
    assert ipa_to_xsampa(ipa) == expected_xs


# ---------------------------------------------------------------------------
# Buckwalter round-trip — extended Arabic sample
# ---------------------------------------------------------------------------

_BW_ARABIC_EXTENDED = [
    # word, BW, Arabic Unicode
    ("marhaba", "mrHbA", "مرحبا"),
    ("taa marbuta", "p", "ة"),
    ("hamza on alef", ">", "أ"),
    ("hamza below alef", "<", "إ"),
    ("hamza on waw", "&", "ؤ"),
    ("hamza on ya", "}", "ئ"),
    ("alef madda", "|", "آ"),
    ("shadda", "~", "ّ"),   # "~" is the canonical (and only) Buckwalter shadda
    ("fatha", "a", "َ"),
    ("damma", "u", "ُ"),
    ("kasra", "i", "ِ"),
    ("sukun", "o", "ْ"),
    ("tanwin fath", "F", "ً"),
    ("tanwin damm", "N", "ٌ"),
    ("tanwin kasr", "K", "ٍ"),
]


@pytest.mark.parametrize("label,bw,arabic", _BW_ARABIC_EXTENDED)
def test_buckwalter_extended_to_arabic(label, bw, arabic):
    assert buckwalter_to_arabic(bw) == arabic, f"Failed for {label}"


@pytest.mark.parametrize("label,bw,arabic", _BW_ARABIC_EXTENDED)
def test_buckwalter_extended_round_trip(label, bw, arabic):
    assert arabic_to_buckwalter(arabic) == bw, f"Round-trip failed for {label}"


# ---------------------------------------------------------------------------
# Lexique → IPA  (gold pairs from the official Lexique table)
# ---------------------------------------------------------------------------
#
# Gold pairs verified against Manuel de Lexique 3 v3.11, Tableau 2 (p. 12)
# and cross-checked with Lexique383 database entries.
# Source: New & Pallier, CC BY-SA 4.0.

@pytest.mark.parametrize("lexique, expected_ipa", [
    # bonjour — b§ZuR
    ("b§ZuR", "bɔ̃ʒuʁ"),
    # vin — v5
    ("v5", "vɛ̃"),
    # brun — bR1
    ("bR1", "bʁœ̃"),
    # deux — d2
    ("d2", "dø"),
    # peur — p9R
    ("p9R", "pœʁ"),
    # huit — 8it
    ("8it", "ɥit"),
    # agneau — aNo  (N=ɲ palatal nasal, verified from Table 2)
    ("aNo", "aɲo"),
    # camping — kaGiG  (G=ŋ velar nasal from English loan; a=lowercase in Lexique)
    ("kaGiG", "kaŋiŋ"),
    # chat — Sa
    ("Sa", "ʃa"),
    # gilet — Zile
    ("Zile", "ʒile"),
    # dans — d@s
    ("d@s", "dɑ̃s"),
    # long — l§
    ("l§", "lɔ̃"),
    # schwa élidable (abordera) — abdORa with °
    ("abd°Ra", "abdəʁa"),
])
def test_lexique_to_ipa_gold(lexique, expected_ipa):
    assert lexique_to_ipa(lexique) == expected_ipa


# ---------------------------------------------------------------------------
# IPA → Lexique  (spot checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected_lexique", [
    ("bɔ̃ʒuʁ", "b§ZuR"),
    ("vɛ̃", "v5"),
    ("dø", "d2"),
    ("pœʁ", "p9R"),
    ("ɥit", "8it"),
    ("aɲo",    "aNo"),    # ɲ→N, a→a, o→o
])
def test_ipa_to_lexique_gold(ipa, expected_lexique):
    result = ipa_to_lexique(ipa)
    assert result == expected_lexique


# ---------------------------------------------------------------------------
# Lexique round-trip
# ---------------------------------------------------------------------------

_LEXIQUE_ROUND_TRIP = [
    "b§ZuR",   # bonjour
    "v5",      # vin
    "d2",      # deux
    "p9R",     # peur
    "Sa",      # chat
    "ZuR",     # jour
    "aNo",     # agneau
    "8it",     # huit
    "l§",      # long
    "d@s",     # dans
]


@pytest.mark.parametrize("lexique", _LEXIQUE_ROUND_TRIP)
def test_lexique_ipa_lexique_round_trip(lexique):
    ipa = lexique_to_ipa(lexique)
    back = ipa_to_lexique(ipa)
    assert back == lexique, f"Round-trip failed: {lexique!r} → {ipa!r} → {back!r}"


# ---------------------------------------------------------------------------
# Lexique convert() facade
# ---------------------------------------------------------------------------

def test_convert_lexique_to_ipa():
    assert convert("b§ZuR", "lexique", "ipa") == "bɔ̃ʒuʁ"


def test_convert_ipa_to_lexique():
    assert convert("bɔ̃ʒuʁ", "ipa", "lexique") == "b§ZuR"


def test_convert_lexique_enum():
    assert convert("v5", Notation.LEXIQUE, Notation.IPA) == "vɛ̃"


def test_convert_lexique_to_xsampa_via_ipa():
    result = convert("Sa", "lexique", "x-sampa")
    assert result == "Sa"  # ʃ→S, a→a


# ---------------------------------------------------------------------------
# B1 regression — Buckwalter docstring example mrHbA
# ---------------------------------------------------------------------------

def test_buckwalter_docstring_example():
    """B1: buckwalter_to_arabic('mrHbA') must produce 'مرحبا'."""
    assert buckwalter_to_arabic("mrHbA") == "مرحبا"


# ---------------------------------------------------------------------------
# B3 regression — X-SAMPA ɻ canonical reverse
# ---------------------------------------------------------------------------

def test_xsampa_61b_reverse_canonical():
    """B3: ipa_to_xsampa('ɻ') must return a form that round-trips."""
    xs = ipa_to_xsampa("ɻ")
    back = xsampa_to_ipa(xs)
    assert back == "ɻ", f"ɻ round-trip failed: ɻ → {xs!r} → {back!r}"


def test_xsampa_r_backtick_and_r_backslash():
    r"""r` -> ɽ (retroflex flap), r\` -> ɻ (retroflex approximant), r\\ -> ɹ (alveolar approximant)."""
    assert xsampa_to_ipa("r`") == "ɽ"
    assert xsampa_to_ipa("r\\`") == "ɻ"
    assert xsampa_to_ipa("r\\") == "ɹ"


# ---------------------------------------------------------------------------
# New X-SAMPA symbols — retroflex, palatal, uvular, alveolo-palatal
# ---------------------------------------------------------------------------

def test_xsampa_new_symbols():
    """Regression: newly added X-SAMPA symbols map correctly."""
    # Retroflex plosives
    assert xsampa_to_ipa("t`") == "ʈ"
    assert xsampa_to_ipa("d`") == "ɖ"
    # Palatal plosive
    assert xsampa_to_ipa("J\\`") == "ɟ"
    # Uvular plosive
    assert xsampa_to_ipa("q") == "q"
    # Alveolo-palatal fricatives
    assert xsampa_to_ipa("s\\`") == "ɕ"
    assert xsampa_to_ipa("z\\`") == "ʑ"
    # Lateral flap
    assert xsampa_to_ipa("l\\`") == "ɺ"


def test_xsampa_new_symbols_roundtrip():
    """Round-trip all new X-SAMPA symbols through IPA."""
    symbols = ["ʈ", "ɖ", "ɟ", "q", "ɕ", "ʑ", "ɺ"]
    for ipa in symbols:
        xs = ipa_to_xsampa(ipa)
        back = xsampa_to_ipa(xs)
        assert back == ipa, f"Round-trip failed for {ipa}: -> {xs!r} -> {back!r}"


# ---------------------------------------------------------------------------
# B4 regression — ipa_to_arpa works correctly (regex caching)
# ---------------------------------------------------------------------------

def test_ipa_to_arpa_simple():
    """B4: Basic ipa_to_arpa should work regardless of regex caching."""
    assert ipa_to_arpa("p") == "P"
    assert ipa_to_arpa("k") == "K"


def test_ipa_to_arpa_multi_char():
    """B4: Multi-char IPA symbols match correctly."""
    assert ipa_to_arpa("tʃ") == "CH"
    assert ipa_to_arpa("dʒ") == "JH"


# ---------------------------------------------------------------------------
# M4 regression — Notation repr
# ---------------------------------------------------------------------------

def test_notation_repr():
    """M4: Notation members have clean repr."""
    assert repr(Notation.IPA) == "Notation.IPA"
    assert repr(Notation.ARPA) == "Notation.ARPA"
    assert repr(Notation.XSAMPA) == "Notation.XSAMPA"


# ---------------------------------------------------------------------------
# B7 regression — __init__.py translit docstring (jamo, not IPA)
# ---------------------------------------------------------------------------

def test_translit_docstring_says_jamo():
    """B7: The translit module docstring should mention 'jamo', not 'IPA'."""
    from scriptconv import translit
    assert "jamo" in translit.__doc__.lower()


# ---------------------------------------------------------------------------
# B5 regression — lam-alef ligatures in Buckwalter
# ---------------------------------------------------------------------------

def test_buckwalter_lam_alef_ligature():
    """B5: Pre-composed lam-alef ligatures (single codepoints) convert correctly."""
    # Pre-composed ligatures (U+FEFB etc.)
    assert arabic_to_buckwalter("\uFEFB") == "lA"   # لا ligature
    assert arabic_to_buckwalter("\uFEF9") == "l<"   # لإ ligature
    assert arabic_to_buckwalter("\uFEF7") == "l>"   # لأ ligature
    assert arabic_to_buckwalter("\uFEF8") == "l|"   # لآ ligature
    # Decomposed forms (lam + alef as separate chars) also work
    assert arabic_to_buckwalter("لا") == "lA"
    assert arabic_to_buckwalter("لأ") == "l>"


def test_buckwalter_lam_alef_roundtrip():
    """B5: lam-alef ligatures survive Buckwalter→Arabic→Buckwalter."""
    assert arabic_to_buckwalter(buckwalter_to_arabic("lA")) == "lA"


# ---------------------------------------------------------------------------
# MO1 regression — can_convert predicate
# ---------------------------------------------------------------------------

def test_can_convert_direct():
    assert can_convert("arpa", "ipa") is True
    assert can_convert("ipa", "arpa") is True
    assert can_convert("x-sampa", "ipa") is True
    assert can_convert("buckwalter", "arabic") is True


def test_can_convert_indirect():
    assert can_convert("arpa", "x-sampa") is True
    assert can_convert("lexique", "arpa") is True


def test_can_convert_unsupported():
    assert can_convert("buckwalter", "ipa") is False
    assert can_convert("arabic", "ipa") is False


def test_can_convert_identity_false():
    # Identity is not a "conversion path" — use convert() for that
    assert can_convert("ipa", "ipa") is False


# ---------------------------------------------------------------------------
# convert_batch
# ---------------------------------------------------------------------------

def test_convert_batch_basic():
    lines = ["HH AH0 L OW1", "", "AY1"]
    result = list(convert_batch(lines, "arpa", "ipa"))
    assert result == ["həloʊ", "", "aɪ"]


def test_convert_batch_blank_lines_preserved():
    lines = ["", "", "HH"]
    result = list(convert_batch(lines, "arpa", "ipa"))
    assert result == ["", "", "h"]


# ---------------------------------------------------------------------------
# Empty string edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", [
    arpa_to_ipa, ipa_to_arpa, xsampa_to_ipa, ipa_to_xsampa,
    buckwalter_to_arabic, arabic_to_buckwalter,
    lexique_to_ipa, ipa_to_lexique,
])
def test_empty_string_passthrough(fn):
    assert fn("") == ""


# ---------------------------------------------------------------------------
# can_convert with Notation enum arguments
# ---------------------------------------------------------------------------

def test_can_convert_enum_direct():
    assert can_convert(Notation.ARPA, Notation.IPA) is True
    assert can_convert(Notation.IPA, Notation.XSAMPA) is True
    assert can_convert(Notation.BUCKWALTER, Notation.ARABIC) is True
    assert can_convert(Notation.LEXIQUE, Notation.IPA) is True


def test_can_convert_enum_indirect():
    assert can_convert(Notation.ARPA, Notation.XSAMPA) is True
    assert can_convert(Notation.XSAMPA, Notation.LEXIQUE) is True


def test_can_convert_enum_unsupported():
    assert can_convert(Notation.BUCKWALTER, Notation.IPA) is False


# ---------------------------------------------------------------------------
# convert() with invalid notation name
# ---------------------------------------------------------------------------

def test_convert_invalid_notation_name():
    with pytest.raises(ValueError):
        convert("x", "foobar", "ipa")


# ---------------------------------------------------------------------------
# ipa_to_arpa — multi-character IPA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected", [
    ("həloʊ", "HH AX L OW"),
    ("tʃɛ", "CH ?"),       # ɛ not in IPA→ARPA → flagged
    ("dʒʌst", "JH AH S T"),
    ("θæŋks", "TH AE NG K S"),
    ("ʃoʊ", "SH OW"),
])
def test_ipa_to_arpa_multi(ipa, expected):
    # ɛ is not in the IPA→ARPA table, so it gets flagged as ?
    assert ipa_to_arpa(ipa) == expected


# ---------------------------------------------------------------------------
# ipa_to_arpa — r-colored vowels and syllabics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected", [
    ("ɜr", "ER"),
    ("ər", "AXR"),
    ("ɾ", "DX"),
    ("ɫ̩", "EL"),
    ("m̩", "EM"),
    ("n̩", "EN"),
])
def test_ipa_to_arpa_r_colored_syllabic(ipa, expected):
    assert ipa_to_arpa(ipa) == expected


# ---------------------------------------------------------------------------
# arpa_to_ipa — diphthongs and special tokens
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("arpa, expected", [
    ("EY1", "eɪ"),
    ("AY1", "aɪ"),
    ("OW1", "oʊ"),
    ("AW1", "aʊ"),
    ("OY1", "ɔɪ"),
    ("ENG", "ŋ̍"),
    ("DX", "ɾ"),
    ("NX", "ɾ̃"),
])
def test_arpa_to_ipa_diphthongs_special(arpa, expected):
    assert arpa_to_ipa(arpa) == expected


# ---------------------------------------------------------------------------
# X-SAMPA — unknown character passthrough
# ---------------------------------------------------------------------------

def test_xsampa_passthrough():
    # Truly unknown characters pass through
    assert xsampa_to_ipa("!#$") == "!#$"
    assert xsampa_to_ipa("xyz") == "xyz"


def test_ipa_to_xsampa_passthrough():
    assert ipa_to_xsampa("!@#") == "!@#"
    assert ipa_to_xsampa("xyz") == "xyz"


# ---------------------------------------------------------------------------
# X-SAMPA — alias and suprasegmental symbols
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("xs, expected", [
    ("&", "æ"),      # alias for {
    ("f\\", "ɸ"),    # alias for p\
    ("%", "ˌ"),      # secondary stress
    ("-.", "."),     # syllable boundary
    ("-", "-"),      # hyphen (pass-through)
])
def test_xsampa_aliases_suprasegmentals(xs, expected):
    assert xsampa_to_ipa(xs) == expected


# ---------------------------------------------------------------------------
# X-SAMPA — backslash-combo symbols n\` and X\`
# ---------------------------------------------------------------------------

def test_xsampa_n_backtick():
    assert xsampa_to_ipa("n\\`") == "ɳ"
    assert ipa_to_xsampa("ɳ") == "n\\`"


def test_xsampa_X_backtick():
    assert xsampa_to_ipa("X\\`") == "ħ"
    assert ipa_to_xsampa("ħ") == "X\\`"


# ---------------------------------------------------------------------------
# X-SAMPA — vowel symbols coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("xs, expected", [
    ("1", "ɨ"),
    ("2", "ø"),
    ("4", "ɾ"),
    ("5", "ɫ"),
    ("6", "ɐ"),
    ("7", "ɤ"),
    ("8", "ɵ"),
    ("9", "œ"),
    ("A", "ɑ"),
    ("Q", "ɒ"),
    ("M", "ɯ"),
    ("U", "ʊ"),
    ("W", "ʍ"),
    ("Y", "ʏ"),
    ("I\\", "ᵻ"),
    ("U\\", "ᵿ"),
    ("M\\", "ɰ"),
    ("3\\", "ɞ"),
    ("B\\", "ʙ"),
    ("H\\", "ʜ"),
    ("?\\", "ʕ"),
    ("h\\", "ɦ"),
    ("K\\", "ɮ"),
    ("L\\", "ʎ"),
    ("R\\", "ʀ"),
])
def test_xsampa_vowels_coverage(xs, expected):
    assert xsampa_to_ipa(xs) == expected


# ---------------------------------------------------------------------------
# Buckwalter — tatweel, shadda alias, unknown passthrough
# ---------------------------------------------------------------------------

def test_buckwalter_tatweel():
    assert buckwalter_to_arabic("_") == "ـ"


def test_buckwalter_shadda_alias():
    # "~" is the only shadda spelling; "^" is NOT Buckwalter (mantoq uses it
    # for θ) and passes through as an unknown.
    # yields the canonical "~".
    assert buckwalter_to_arabic("~") == "ّ"
    assert buckwalter_to_arabic("^") == "^"
    assert arabic_to_buckwalter("ّ") == "~"


def test_buckwalter_unknown_passthrough():
    # Digits are not in the BW table, so they pass through
    assert buckwalter_to_arabic("123") == "123"


# ---------------------------------------------------------------------------
# convert_batch — generator protocol and line stripping
# ---------------------------------------------------------------------------

def test_convert_batch_is_generator():
    result = convert_batch(["HH"], "arpa", "ipa")
    import types
    assert isinstance(result, types.GeneratorType)


def test_convert_batch_lazy_next():
    lines = ["HH", "AH0"]
    gen = convert_batch(lines, "arpa", "ipa")
    assert next(gen) == "h"
    assert next(gen) == "ə"


def test_convert_batch_strips_newlines():
    lines = ["HH\n", "AH0\r\n", "OW1\r"]
    result = list(convert_batch(lines, "arpa", "ipa"))
    assert result == ["h", "ə", "oʊ"]


def test_convert_batch_with_enum():
    lines = ["S", "Z"]
    result = list(convert_batch(lines, Notation.XSAMPA, Notation.IPA))
    assert result == ["ʃ", "ʒ"]


# ---------------------------------------------------------------------------
# IPA → X-SAMPA round-trip — multi-character IPA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa", [
    "tʃ",
    "dʒ",
    "eɪ",
    "aɪ",
    "oʊ",
    "aʊ",
    "ɔɪ",
    "ɜr",
    "ər",
])
def test_ipa_xsampa_roundtrip_multi(ipa):
    xs = ipa_to_xsampa(ipa)
    back = xsampa_to_ipa(xs)
    assert back == ipa, f"Round-trip failed: {ipa!r} -> {xs!r} -> {back!r}"


# ---------------------------------------------------------------------------
# ARPA round-trip — diphthongs, r-colored, affricates
# ---------------------------------------------------------------------------

_ROUND_TRIP_ARPA_EXTENDED = [
    "EY", "AY", "OW", "AW", "OY",
    "CH", "JH", "ER",
]


@pytest.mark.parametrize("arpa", _ROUND_TRIP_ARPA_EXTENDED)
def test_arpa_roundtrip_extended(arpa):
    ipa = arpa_to_ipa(arpa)
    back = ipa_to_arpa(ipa)
    assert back == arpa, f"Round-trip failed: {arpa!r} -> {ipa!r} -> {back!r}"


# ---------------------------------------------------------------------------
# Lexique — isolated vowel gold checks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected", [
    ("ø", "2"),
    ("œ", "9"),
    ("ɑ̃", "@"),
    ("ɔ̃", "§"),
    ("ɛ̃", "5"),
    ("œ̃", "1"),
])
def test_ipa_to_lexique_vowels(ipa, expected):
    assert ipa_to_lexique(ipa) == expected


# ---------------------------------------------------------------------------
# ipa_to_arpa — unknown chars flagged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ipa, expected", [
    ("ɸɸ", "? ?"),
    ("pɸt", "P ? T"),
    ("həˈloʊ", "HH AX L OW"),  # ˈ is a suprasegmental modifier, dropped not flagged
])
def test_ipa_to_arpa_unknown_chars(ipa, expected):
    assert ipa_to_arpa(ipa) == expected


# ---------------------------------------------------------------------------
# Notation enum — basic properties
# ---------------------------------------------------------------------------

def test_notation_enum_values():
    assert Notation.IPA.value == "ipa"
    assert Notation.ARPA.value == "arpa"
    assert Notation.XSAMPA.value == "x-sampa"
    assert Notation.BUCKWALTER.value == "buckwalter"
    assert Notation.ARABIC.value == "arabic"
    assert Notation.LEXIQUE.value == "lexique"


def test_notation_enum_count():
    assert len(Notation) == 10


def test_notation_str():
    assert str(Notation.IPA) == "Notation.IPA"


# ---------------------------------------------------------------------------
# Kirshenbaum (ASCII-IPA) ↔ IPA
# ---------------------------------------------------------------------------

from scriptconv.notation import (  # noqa: E402
    kirshenbaum_to_ipa, ipa_to_kirshenbaum, NotationInfo, NOTATION_INFO,
)


@pytest.mark.parametrize("k, ipa", [
    ("S", "ʃ"), ("Z", "ʒ"), ("N", "ŋ"), ("T", "θ"), ("D", "ð"),
    ("A", "ɑ"), ("g", "ɡ"), ("tS", "tʃ"), ("@", "ə"),
])
def test_kirshenbaum_to_ipa(k, ipa):
    assert kirshenbaum_to_ipa(k) == ipa


@pytest.mark.parametrize("ipa, k", [
    ("ʃ", "S"), ("ŋ", "N"), ("θ", "T"), ("ɑ", "A"), ("ə", "@"),
])
def test_ipa_to_kirshenbaum(ipa, k):
    assert ipa_to_kirshenbaum(ipa) == k


def test_kirshenbaum_passthrough_and_empty():
    assert kirshenbaum_to_ipa("") == ""
    assert ipa_to_kirshenbaum("") == ""


def test_convert_routes_through_kirshenbaum():
    # arpa → ipa → kirshenbaum
    assert convert("HH AH0 L OW1", "arpa", "kirshenbaum") == "h@loU"
    # kirshenbaum → ipa → x-sampa
    assert convert("S", "kirshenbaum", "x-sampa") == "S"


def test_can_convert_kirshenbaum():
    assert can_convert("kirshenbaum", "ipa")
    assert can_convert("ipa", "kirshenbaum")
    assert can_convert("kirshenbaum", "arpa")


# ---------------------------------------------------------------------------
# NotationInfo fidelity metadata
# ---------------------------------------------------------------------------

def test_notation_info_shape():
    info = NOTATION_INFO[Notation.ARPA]
    assert isinstance(info, NotationInfo)
    assert info.lossless_from_ipa is False   # restricted English inventory
    assert info.token_separated is True      # space-separated ARPABET tokens
    assert info.reference                     # non-empty citation


def test_every_notation_info_has_a_citation():
    assert all(i.reference for i in NOTATION_INFO.values())


def test_lossless_to_ipa_flag_backed_by_round_trip():
    # A lossless_to_ipa=True claim must actually round-trip a representative
    # symbol set through IPA and back.
    samples = {
        Notation.KIRSHENBAUM: "SNTDpbtdkg",
        Notation.BUCKWALTER: "AbtmrHlwnhyk",
    }
    to_ipa = {Notation.KIRSHENBAUM: kirshenbaum_to_ipa,
              Notation.BUCKWALTER: buckwalter_to_arabic}
    from_ipa = {Notation.KIRSHENBAUM: ipa_to_kirshenbaum,
                Notation.BUCKWALTER: arabic_to_buckwalter}
    for notation, info in NOTATION_INFO.items():
        if info.lossless_to_ipa and notation in samples:
            for ch in samples[notation]:
                assert from_ipa[notation](to_ipa[notation](ch)) == ch, notation


# ---------------------------------------------------------------------------
# looks_like_ipa — heuristic notation detection
# ---------------------------------------------------------------------------

from scriptconv.notation import looks_like_ipa  # noqa: E402


@pytest.mark.parametrize("text", [
    "pʰɑtʃ",       # IPA Extensions + modifier
    "ˈhɛloʊ",      # stress mark + IPA Extensions
    "ɑ",           # single IPA Extensions char
    "næ̃",          # combining nasalisation
    "kat̪",         # combining dental diacritic
])
def test_looks_like_ipa_true(text):
    assert looks_like_ipa(text) is True


@pytest.mark.parametrize("text", [
    "",            # empty
    "hello",       # plain Latin — ambiguous, no distinctive marker
    "att",         # overlaps Latin
    "café",        # accented Latin is not IPA-distinctive
    "θaβ",         # bare Greek letters carry no IPA signal
    "مرحبا",       # Arabic
])
def test_looks_like_ipa_false(text):
    assert looks_like_ipa(text) is False


# ---------------------------------------------------------------------------
# Cotovía ↔ IPA
# ---------------------------------------------------------------------------

from scriptconv.notation import cotovia_to_ipa, ipa_to_cotovia  # noqa: E402


@pytest.mark.parametrize("cv, ipa", [
    ("tS", "tʃ"),
    ("rr", "r"),     # trill
    ("r", "ɾ"),      # tap
    ("L", "ʎ"), ("Z", "ʎ"), ("jj", "ʎ"),  # all three collapse to ʎ
    ("B", "β"), ("D", "ð"), ("G", "ɣ"), ("J", "ɲ"), ("N", "ŋ"),
    ("S", "ʃ"), ("T", "θ"), ("E", "ɛ"), ("O", "ɔ"), ("x", "x"), ("X", "x"),
    ("karro", "karo"),
])
def test_cotovia_to_ipa(cv, ipa):
    assert cotovia_to_ipa(cv) == ipa


@pytest.mark.parametrize("ipa, cv", [
    ("tʃ", "tS"),
    ("r", "rr"),     # trill
    ("ɾ", "r"),      # tap
    ("ʎ", "L"),      # canonical Cotovía palatal lateral
    ("x", "x"),
    ("β", "B"), ("ɲ", "J"), ("ɛ", "E"), ("ɔ", "O"),
])
def test_ipa_to_cotovia(ipa, cv):
    assert ipa_to_cotovia(ipa) == cv


def test_cotovia_tap_trill_round_trip():
    # The tap/trill distinction must survive a round-trip.
    assert ipa_to_cotovia(cotovia_to_ipa("karro")) == "karro"  # trill
    assert ipa_to_cotovia(cotovia_to_ipa("kara")) == "kara"    # tap


def test_convert_routes_through_cotovia():
    assert convert("tS", "cotovia", "x-sampa") == "tS"
    assert convert("CH IY1", "arpa", "cotovia") == "tSi"


def test_cotovia_pause_marker_not_a_phoneme():
    # "#" (silence marker) is excluded from the table and passes through
    # unchanged, rather than being emitted as a "pau" token.
    assert cotovia_to_ipa("#") == "#"
    # p/a/u are ordinary phonemes, converted independently.
    assert cotovia_to_ipa("pau") == "pau"


# ---------------------------------------------------------------------------
# RFE (Revista de Filología Española) ↔ IPA
# ---------------------------------------------------------------------------

from scriptconv.notation import rfe_to_ipa, ipa_to_rfe  # noqa: E402


@pytest.mark.parametrize("rfe, ipa", [
    ("š", "ʃ"), ("ž", "ʒ"), ("ĉ", "tʃ"), ("y", "ʝ"), ("ŷ", "ɟʝ"),
    ("ñ", "ɲ"), ("n̮", "ɲ"), ("l̮", "ʎ"),
    ("ƀ", "β"), ("đ", "ð"), ("ǥ", "ɣ"), ("θ", "θ"), ("ł", "ɫ"),
    ("r", "ɾ"), ("r̄", "r"),
    ("g", "ɡ"),
    ("kaša", "kaʃa"),
])
def test_rfe_to_ipa(rfe, ipa):
    assert rfe_to_ipa(rfe) == ipa


@pytest.mark.parametrize("ipa, rfe", [
    ("ʃ", "š"), ("ʒ", "ž"), ("tʃ", "ĉ"), ("ʝ", "y"),
    ("ɲ", "ñ"),      # canonical, not the n̮ variant
    ("ʎ", "l̮"),
    ("β", "ƀ"), ("ð", "đ"), ("ɣ", "ǥ"),
    ("ɾ", "r"), ("r", "r̄"),
])
def test_ipa_to_rfe(ipa, rfe):
    assert ipa_to_rfe(ipa) == rfe


def test_rfe_tap_trill_round_trip():
    assert ipa_to_rfe(rfe_to_ipa("far̄a")) == "far̄a"   # trill
    assert ipa_to_rfe(rfe_to_ipa("kara")) == "kara"     # tap


def test_convert_routes_through_rfe():
    assert convert("š", "rfe", "x-sampa") == "S"
    assert convert("ʃ", "ipa", "rfe") == "š"


# ---------------------------------------------------------------------------
# Mantoq → IPA (Halabi Arabic-Phonetiser inventory; one-directional)
# ---------------------------------------------------------------------------

from scriptconv.notation import mantoq_to_ipa, UnknownSymbolError  # noqa: E402

def test_mantoq_basic_word():
    assert mantoq_to_ipa("salaam") == "salaːm"


def test_mantoq_theta_is_caret_not_shadda():
    # mantoq's "^" is θ — the same character is NOT a Buckwalter shadda here
    assert mantoq_to_ipa("^") == "θ"


def test_mantoq_gemination_marker():
    assert mantoq_to_ipa("b_dbl_a") == "bːa"
    assert mantoq_to_ipa("aa_dbl_") == "aːː"


def test_mantoq_word_separator_and_glottal():
    assert mantoq_to_ipa("m_+_<a") == "m ʔa"


def test_mantoq_emphatics_and_superlong():
    assert mantoq_to_ipa("SaaaaD") == "sˤaːːdˤ"


def test_mantoq_via_convert_facade():
    assert convert("salaam", "mantoq", "ipa") == "salaːm"
    assert can_convert("mantoq", "ipa") is True
    assert can_convert("ipa", "mantoq") is False


def test_mantoq_chains_to_xsampa_via_graph():
    # mantoq -> ipa -> x-sampa multi-hop through the conversion graph
    out = convert("salaam", "mantoq", "x-sampa")
    assert "a:" in out


def test_mantoq_errors_strict():
    import pytest as _pytest
    with _pytest.raises(UnknownSymbolError):
        mantoq_to_ipa("Q", errors="strict")


def test_buckwalter_wasla_and_dagger_alef():
    from scriptconv.notation import arabic_to_buckwalter, buckwalter_to_arabic
    assert buckwalter_to_arabic("{") == "ٱ"
    assert buckwalter_to_arabic("`") == "ٰ"
    assert arabic_to_buckwalter("رحمٰن") == "rHm`n"
    assert arabic_to_buckwalter("ٱ") == "{"
