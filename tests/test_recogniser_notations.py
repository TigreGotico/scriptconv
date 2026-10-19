"""Allosaurus and espeak-ng phone-recogniser units to IPA.

``recogniser_units_fixture.json`` holds every output unit of the Allosaurus
``uni2005`` model and of ``facebook/wav2vec2-xlsr-53-espeak-cv-ft`` with its IPA,
or ``null`` for a unit with no IPA reading.
"""
import json
from pathlib import Path

import pytest

from scriptconv.notation import (
    NOTATION_INFO,
    Notation,
    UnknownSymbolError,
    allosaurus_to_ipa,
    can_convert,
    convert,
    espeak_ipa_to_ipa,
)

FIXTURE = json.loads((Path(__file__).parent / "recogniser_units_fixture.json").read_text())
CONVERTERS = {"allosaurus": allosaurus_to_ipa, "espeak-ipa": espeak_ipa_to_ipa}


def _strict(notation, unit):
    try:
        return CONVERTERS[notation]([unit], errors="strict")
    except UnknownSymbolError:
        return None


@pytest.mark.parametrize("notation", sorted(FIXTURE))
def test_every_unit_matches_the_golden_map(notation):
    wrong = {u: (_strict(notation, u), ipa) for u, ipa in FIXTURE[notation].items() if _strict(notation, u) != ipa}
    assert not wrong, wrong


def test_the_inventories_are_complete():
    assert len(FIXTURE["allosaurus"]) == 229
    assert len(FIXTURE["espeak-ipa"]) == 392


@pytest.mark.parametrize("unit, ipa", [
    ("tʃ", "t͡ʃ"), ("dʒ", "d͡ʒ"), ("ts", "t͡s"), ("tsʰ", "t͡sʰ"), ("tʂʰ", "t͡ʂʰ"),
    ("kx", "k͡x"), ("pf", "p͡f"), ("g", "ɡ"), ("gʲj", "ɡʲj"), ("ә", "ə"),
    ("t͡ʃ", "t͡ʃ"), ("uə", "uə"), ("nj", "nj"), ("ɫ", "ɫ"), ("ʃ", "ʃ"), ("ɨ", "ɨ"),
])
def test_allosaurus_units(unit, ipa):
    assert allosaurus_to_ipa([unit]) == ipa


@pytest.mark.parametrize("unit, ipa", [
    ("S", "ʃ"), ("N", "ŋ"), ("X", "χ"), ("dZ", "d͡ʒ"), ("tS", "t͡ʃ"), ("t[", "t̪"),
    ("u:", "uː"), ("s.", "ʂ"), ("ts.", "t͡ʂ"), ("ts.h", "t͡ʂʰ"), ("th", "tʰ"),
    ("tsh", "t͡sʰ"), ("tʃʲ", "t͡ʃʲ"), ("ɐ̃ʊ̃", "ɐ̃ʊ̃"), ("ɨ", "ɨ"), ("ɜ", "ɜ"), ("ɜː", "ɜː"),
])
def test_espeak_units(unit, ipa):
    assert espeak_ipa_to_ipa([unit]) == ipa


@pytest.mark.parametrize("unit", ["i5", "iɜ", "ərɜ", "??", "u\"", "s^", "a.", "i.", "1", "<pad>"])
def test_espeak_units_without_ipa_follow_the_policy(unit):
    with pytest.raises(UnknownSymbolError):
        espeak_ipa_to_ipa([unit], errors="strict")
    assert espeak_ipa_to_ipa([unit], errors="ignore") == ""
    assert espeak_ipa_to_ipa([unit]) == unit


@pytest.mark.parametrize("unit", ["I", "ː"])
def test_allosaurus_units_without_ipa_follow_the_policy(unit):
    with pytest.raises(UnknownSymbolError):
        allosaurus_to_ipa([unit], errors="strict")
    assert allosaurus_to_ipa([unit], errors="ignore") == ""


def test_a_string_is_whitespace_separated_units():
    assert allosaurus_to_ipa("tʃ a g ә") == "t͡ʃaɡə"
    assert espeak_ipa_to_ipa("dZ S u: t[") == "d͡ʒʃuːt̪"


def test_the_unit_boundary_decides_the_affricate():
    assert allosaurus_to_ipa(["t", "ʃ"]) == "tʃ"
    assert allosaurus_to_ipa(["tʃ"]) == "t͡ʃ"


@pytest.mark.parametrize("notation", [Notation.ALLOSAURUS, Notation.ESPEAK_IPA])
def test_registered_one_directional(notation):
    info = NOTATION_INFO[notation]
    assert info.token_separated and not info.lossless_from_ipa and info.reference
    assert can_convert(notation, "ipa")
    assert not can_convert("ipa", notation)


def test_convert_facade():
    assert convert("tʃ a", "allosaurus", "ipa") == "t͡ʃa"
    assert convert("dZ i5", "espeak-ipa", "ipa", errors="ignore") == "d͡ʒ"
    assert convert("S", "espeak-ipa", "x-sampa") == "S"
