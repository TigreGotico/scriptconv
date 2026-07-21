"""Downstream compat: the script tags scriptconv returns are a wire format.

stressonnx (accentor.py) maps its supported languages to a private script
taxonomy that mirrors phoonnx's Alphabet enum.  These fixtures pin, key by
key, that scriptconv resolves every one of those language codes to the
expected ISO-15924 tag — so stressonnx's migration to scriptconv is a pure
deletion, and future edits here cannot silently break it.
"""
import pytest

from scriptconv import lang_to_script

# stressonnx LANG_SCRIPT, verbatim keys -> the ISO-15924 tag its Script
# enum value corresponds to (cyrillic->Cyrl, latin->Latn, armenian->Armn,
# georgian->Geor).
STRESSONNX_LANGS = {
    "ru": "Cyrl", "ukr": "Cyrl", "bel": "Cyrl", "bel_simple": "Cyrl",
    "kaz": "Cyrl", "tat": "Cyrl", "bak": "Cyrl", "chv": "Cyrl",
    "sah": "Cyrl", "kir": "Cyrl", "kjh": "Cyrl", "tgk": "Cyrl",
    "udm": "Cyrl", "xal": "Cyrl", "kbd": "Cyrl", "erz": "Cyrl",
    "mdf": "Cyrl", "uzb_cyr": "Cyrl", "aze_cyr": "Cyrl",
    "aze_lat": "Latn", "uzb_lat": "Latn",
    "hye": "Armn",
    "kat": "Geor",
}


@pytest.mark.parametrize("lang,expected", sorted(STRESSONNX_LANGS.items()))
def test_stressonnx_language_resolves(lang, expected):
    assert lang_to_script(lang) == expected


def test_iso639_bibliographic_variants():
    assert lang_to_script("ger") == lang_to_script("deu") == "Latn"
    assert lang_to_script("gre") == lang_to_script("ell") == "Grek"
    assert lang_to_script("arm") == lang_to_script("hye") == "Armn"


def test_explicit_script_subtag_still_authoritative():
    assert lang_to_script("uzb-Latn") == "Latn"
    assert lang_to_script("sr_lat") == "Latn"
    assert lang_to_script("sr") == "Cyrl"


def test_unknown_language_stays_none():
    assert lang_to_script("zzz") is None
    assert lang_to_script("qqq_cyr") == "Cyrl"  # variant subtag wins even unknown-lang
