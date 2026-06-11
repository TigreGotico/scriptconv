"""Tests for scriptconv.scripts."""
import pytest
from scriptconv.scripts import (
    Script,
    SCRIPT_REGISTRY,
    char_script,
    detect_script,
    lang_to_script,
    normalize_script_tag,
)


# ---------------------------------------------------------------------------
# Script registry
# ---------------------------------------------------------------------------

def test_registry_contains_required_scripts():
    required = {"Latn", "Cyrl", "Arab", "Hebr", "Deva", "Hang", "Hira",
                "Kana", "Hani", "Grek", "Armn", "Geor", "Ethi", "Khmr",
                "Telu", "Cans", "Tfng"}
    for code in required:
        assert code in SCRIPT_REGISTRY, f"Missing script: {code}"


def test_script_is_frozen_dataclass():
    s = SCRIPT_REGISTRY["Latn"]
    assert isinstance(s, Script)
    with pytest.raises((AttributeError, TypeError)):
        s.iso15924 = "Fake"  # type: ignore[misc]


def test_script_fields():
    arab = SCRIPT_REGISTRY["Arab"]
    assert arab.iso15924 == "Arab"
    assert arab.direction == "rtl"
    assert len(arab.char_ranges) > 0


# ---------------------------------------------------------------------------
# char_script
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch, expected", [
    ("A", "Latn"),
    ("з", "Cyrl"),
    ("ع", "Arab"),
    ("ה", "Hebr"),
    ("अ", "Deva"),
    ("가", "Hang"),
    ("あ", "Hira"),
    ("ア", "Kana"),
    ("中", "Hani"),
    ("α", "Grek"),
    ("Ա", "Armn"),
    ("ა", "Geor"),
    ("ሀ", "Ethi"),
    ("ក", "Khmr"),
    ("అ", "Telu"),
    (" ", None),
    ("1", None),
])
def test_char_script(ch, expected):
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# detect_script
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Hello world", "Latn"),
    ("Привет мир", "Cyrl"),
    ("مرحبا", "Arab"),
    ("안녕하세요", "Hang"),
    ("中文测试", "Hani"),
    ("ελληνικά", "Grek"),
    ("", None),
    ("123 !!!", None),
])
def test_detect_script(text, expected):
    assert detect_script(text) == expected


def test_detect_script_dominant():
    # Mixed but mostly Cyrillic
    text = "Привет A world"
    result = detect_script(text)
    assert result == "Cyrl"


# ---------------------------------------------------------------------------
# lang_to_script
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang, expected", [
    ("ru", "Cyrl"),
    ("uk", "Cyrl"),
    ("hy", "Armn"),
    ("ka", "Geor"),
    ("ar", "Arab"),
    ("he", "Hebr"),
    ("hi", "Deva"),
    ("ko", "Hang"),
    ("ja", "Hira"),
    ("zh", "Hani"),
    ("el", "Grek"),
    ("en", "Latn"),
    ("pt", "Latn"),
    ("pt-BR", "Latn"),
    ("ru-RU", "Cyrl"),
    ("th", "Thai"),
    ("bn", "Beng"),
])
def test_lang_to_script(lang, expected):
    assert lang_to_script(lang) == expected


def test_lang_to_script_unknown():
    assert lang_to_script("xyz") is None


@pytest.mark.parametrize("lang, expected", [
    # Non-Latin orthography2ipa languages
    ("am", "Ethi"),   # Amharic → Ethiopic
    ("ti", "Ethi"),   # Tigrinya → Ethiopic
    ("mn", "Cyrl"),   # Mongolian → Cyrillic
    ("bo", "Tibt"),   # Tibetan → Tibetan
    ("km", "Khmr"),   # Khmer → Khmer
    ("lo", "Laoo"),   # Lao → Lao
    ("my", "Mymr"),   # Myanmar/Burmese → Myanmar
    ("th", "Thai"),   # Thai → Thai
    # Latin-script orthography2ipa languages
    ("vi", "Latn"),   # Vietnamese
    ("ha", "Latn"),   # Hausa
    ("ig", "Latn"),   # Igbo
    ("yo", "Latn"),   # Yoruba
    ("zu", "Latn"),   # Zulu
    ("xh", "Latn"),   # Xhosa
    ("rw", "Latn"),   # Kinyarwanda
    ("tk", "Latn"),   # Turkmen
    ("eo", "Latn"),   # Esperanto
    # Cyrillic-script languages
    ("kk", "Cyrl"),   # Kazakh
    ("ky", "Cyrl"),   # Kyrgyz
    ("tt", "Cyrl"),   # Tatar
    ("ba", "Cyrl"),   # Bashkir
    ("cv", "Cyrl"),   # Chuvash
    ("ce", "Cyrl"),   # Chechen
    # Hebrew
    ("he", "Hebr"),
])
def test_lang_to_script_extended(lang, expected):
    assert lang_to_script(lang) == expected


# ---------------------------------------------------------------------------
# detect_script — mixed/empty behaviour
# ---------------------------------------------------------------------------

def test_detect_script_empty():
    assert detect_script("") is None


def test_detect_script_numbers_only():
    assert detect_script("123 456") is None


def test_detect_script_punctuation_only():
    assert detect_script("!!! ???") is None


def test_detect_script_mixed_returns_dominant():
    # Mostly Arabic with one Latin word
    text = "مرحبا hello مرحبا"
    result = detect_script(text)
    assert result == "Arab"


def test_detect_script_lao():
    assert detect_script("ສະບາຍດີ") == "Laoo"


def test_detect_script_tibetan():
    assert detect_script("བོད་སྐད།") == "Tibt"


# ---------------------------------------------------------------------------
# Script registry — extended scripts present
# ---------------------------------------------------------------------------

def test_registry_laoo_present():
    assert "Laoo" in SCRIPT_REGISTRY


def test_registry_tibt_present():
    assert "Tibt" in SCRIPT_REGISTRY


def test_registry_mymr_present():
    assert "Mymr" in SCRIPT_REGISTRY


def test_registry_thai_present():
    assert "Thai" in SCRIPT_REGISTRY


# ---------------------------------------------------------------------------
# normalize_script_tag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label, expected", [
    ("latin", "Latn"),
    ("Latin", "Latn"),
    ("LATIN", "Latn"),      # lowercased → "latin" → found in label map
    ("cyrillic", "Cyrl"),
    ("arabic", "Arab"),
    ("syllabics", "Cans"),
    ("tifinagh", "Tfng"),
    ("devanagari", "Deva"),
    ("ethiopic", "Ethi"),
    ("khmer", "Khmr"),
    ("telugu", "Telu"),
    ("hangul", "Hang"),
    ("korean", "Hang"),
    ("greek", "Grek"),
    ("armenian", "Armn"),
    ("georgian", "Geor"),
    ("han", "Hani"),
    ("chinese", "Hani"),
    ("Latn", "Latn"),       # ISO code passed directly
    ("latn", "Latn"),       # lowercase ISO code
    ("Cyrl", "Cyrl"),
    ("arab", "Arab"),
    ("lao", "Laoo"),
    ("tibetan", "Tibt"),
    ("myanmar", "Mymr"),
    ("burmese", "Mymr"),
    ("thai", "Thai"),
    ("unknown_xyz", None),
])
def test_normalize_script_tag(label, expected):
    assert normalize_script_tag(label) == expected
