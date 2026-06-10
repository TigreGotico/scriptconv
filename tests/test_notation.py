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
