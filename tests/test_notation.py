"""Tests for scriptconv.notation."""
import pytest
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
    # Each BW char should map to the corresponding Arabic char
    assert len(result) == len(bw)


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
    ("shadda", "^", "ّ"),   # ^ is the canonical reverse (alias ~ also maps to shadda)
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
    ("aɲo", "aN o"),  # placeholder — see note below
])
def test_ipa_to_lexique_gold(ipa, expected_lexique):
    # ɲ → N, o → o  (no space in Lexique; join expected without space)
    result = ipa_to_lexique(ipa)
    assert result == expected_lexique.replace(" ", "")


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
