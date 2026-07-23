"""Pure-python tests for scriptconv.diacritics strip/overlay helpers.

No optional backend is required — strip_diacritics/_overlay_marks/_supports_strip
never load a phonemizer model.
"""
import pytest

from scriptconv.diacritics import (
    strip_diacritics,
    _overlay_marks,
    _supports_strip,
    _STRESS_MARKS,
    _ARABIC_MARKS,
    _HEBREW_MARKS,
)
from scriptconv.phonemizers.base import STRESS_LANGS


def test_strip_removes_combining_acute_preserves_cyrillic():
    assert strip_diacritics("мой родно́й край", "ru") == "мой родной край"


def test_strip_preserves_precomposed_cyrillic_letters():
    # й (U+0439) and ё (U+0451) are precomposed, not combining marks — they
    # must survive stripping even alongside a combining acute.
    text = "ёж, война́, май"  # combining acute (U+0301) after "а" in "война́"
    stripped = strip_diacritics(text, "ru")
    assert "ё" in stripped
    assert "й" in stripped
    assert stripped == "ёж, война, май"


def test_strip_arabic_removes_tashkeel_preserves_consonants():
    assert strip_diacritics("مُحَمَّد", "ar") == "محمد"


def test_strip_arabic_preserves_hamza_carrier():
    stripped = strip_diacritics("أَحْمَد", "ar")
    assert stripped.startswith("أ")


def test_strip_hebrew_removes_niqqud_preserves_consonants():
    # שָׁלוֹם with niqqud -> bare consonants שלום
    stripped = strip_diacritics("שָׁלוֹם", "he")
    assert stripped == "שלום"


@pytest.mark.parametrize("text,lang", [
    ("café", "pt"),
    ("café", "en"),
    ("café", "es"),
    ("café", "arg"),
    ("café", "her"),
    ("café", "arn"),
])
def test_strip_raises_for_native_orthography_langs(text, lang):
    with pytest.raises(ValueError):
        strip_diacritics(text, lang)


@pytest.mark.parametrize("lang", [
    "ru", "uk", "be", "ar", "ar-SA", "he", "he-IL", "bg", "ka",
])
def test_supports_strip_true(lang):
    assert _supports_strip(lang) is True


@pytest.mark.parametrize("lang", [
    "pt", "pt-PT", "en", "arg", "her", "arn",
])
def test_supports_strip_false(lang):
    assert _supports_strip(lang) is False


def test_overlay_marks_stress_lang():
    lang = next(iter(STRESS_LANGS))
    assert _overlay_marks(lang) == _STRESS_MARKS


def test_overlay_marks_arabic():
    assert _overlay_marks("ar") == _ARABIC_MARKS


def test_overlay_marks_hebrew():
    assert _overlay_marks("he") == _HEBREW_MARKS


def test_overlay_marks_none_for_native_orthography():
    assert _overlay_marks("pt") is None
    assert _overlay_marks("en") is None
