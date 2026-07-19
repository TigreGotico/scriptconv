"""Tests for scriptconv.scripts."""
import pytest
from scriptconv.scripts import (
    Script,
    SCRIPT_REGISTRY,
    char_script,
    detect_script,
    script_distribution,
    base_direction,
    lang_to_script,
    script_to_langs,
    normalize_script_tag,
)


# ---------------------------------------------------------------------------
# Script registry
# ---------------------------------------------------------------------------

def test_registry_contains_required_scripts():
    required = {
        "Latn", "Cyrl", "Arab", "Hebr", "Deva", "Hang", "Hira",
        "Kana", "Hani", "Grek", "Armn", "Geor", "Ethi", "Khmr",
        "Telu", "Cans", "Tfng", "Thai", "Beng", "Guru", "Gujr",
        "Taml", "Sinh", "Mymr", "Tibt", "Laoo", "Ogam", "Runr",
        "Phnx", "Cprt", "Glag", "Knda", "Mlym", "Orya",
    }
    assert set(SCRIPT_REGISTRY.keys()) == required


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
    text = "Привет мир A"
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


# ---------------------------------------------------------------------------
# G3 regression — new normalize_script_tag labels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label, expected", [
    ("japanese", "Hira"),
    ("jamo", "Hang"),
    ("hangul jamo", "Hang"),
    ("devanagari extended", "Deva"),
    ("ipa", "Latn"),
    ("cjk", "Hani"),
    ("chinese characters", "Hani"),
    ("han characters", "Hani"),
    ("hangeul", "Hang"),
    ("bangla", "Beng"),
    ("punjabi", "Guru"),
])
def test_normalize_script_tag_new_labels(label, expected):
    assert normalize_script_tag(label) == expected


# ---------------------------------------------------------------------------
# G3 regression — taiViet typo fix (must be lowercase key)
# ---------------------------------------------------------------------------

def test_normalize_script_tag_taiviet():
    # taiViet label was removed (script not in SCRIPT_REGISTRY);
    # verify it no longer resolves.
    assert normalize_script_tag("taiViet") is None
    assert normalize_script_tag("taiviet") is None


# ---------------------------------------------------------------------------
# B5+B6 regression — IPA Extensions & Latin Extended Additional classified as Latn
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch, expected", [
    ("ɑ", "Latn"),   # IPA Extensions (U+0251)
    ("ɒ", "Latn"),   # IPA Extensions (U+0252)
    ("ɛ", "Latn"),   # IPA Extensions (U+025B)
    ("ɔ", "Latn"),   # IPA Extensions (U+0254)
    ("ʃ", "Latn"),   # IPA Extensions (U+0283)
    ("ʒ", "Latn"),   # IPA Extensions (U+0292)
    ("ŋ", "Latn"),   # Latin Extended (U+014B, in 0x00C0-0x024F range)
    ("Ḃ", "Latn"),   # Latin Extended Additional (U+1E02)
    ("Ḋ", "Latn"),   # Latin Extended Additional (U+1E08)
])
def test_char_script_ipa_and_latin_ext(ch, expected):
    """B5/B6: IPA Extensions and Latin Extended Additional → Latn."""
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# G1 regression — script_distribution
# ---------------------------------------------------------------------------

def test_script_distribution_basic():
    dist = script_distribution("Hello Привет мир")
    assert dist["Latn"] == 5
    assert dist["Cyrl"] == 9


def test_script_distribution_empty():
    assert script_distribution("") == {}


def test_script_distribution_sorted_descending():
    dist = script_distribution("Hello Привет мир")
    values = list(dist.values())
    assert values == sorted(values, reverse=True)
    assert len(dist) == 2


def test_script_distribution_mixed_cjk():
    dist = script_distribution("日本語ひらがなカタカナ")
    assert dist["Hani"] == 3
    assert dist["Hira"] == 4
    assert dist["Kana"] == 4


# ---------------------------------------------------------------------------
# G2 regression — base_direction
# ---------------------------------------------------------------------------

def test_base_direction_ltr():
    assert base_direction("Hello world") == "ltr"


def test_base_direction_rtl():
    assert base_direction("مرحبا بالعالم") == "rtl"


def test_base_direction_mixed():
    assert base_direction("Hello مرحبا") == "mixed"


def test_base_direction_empty():
    assert base_direction("") == "mixed"


def test_base_direction_numbers_only():
    assert base_direction("12345") == "mixed"


# ---------------------------------------------------------------------------
# G4 regression — script_to_langs
# ---------------------------------------------------------------------------

def test_script_to_langs_cyrl():
    langs = script_to_langs("Cyrl")
    assert "ru" in langs
    assert "uk" in langs
    assert "bg" in langs


def test_script_to_langs_latn():
    langs = script_to_langs("Latn")
    assert "en" in langs
    assert "fr" in langs
    assert "de" in langs


# ---------------------------------------------------------------------------
# M2 regression — char_script performance (interval-based lookup)
# ---------------------------------------------------------------------------

def test_char_script_all_registered_scripts():
    """Every script in the registry has at least one character that resolves."""
    for code, script in SCRIPT_REGISTRY.items():
        cp = script.char_ranges[0][0]
        ch = chr(cp)
        assert char_script(ch) == code, f"char_script({ch!r}) should be {code}"


# ---------------------------------------------------------------------------
# B5+B6 regression — detect_script classifies IPA text as Latn
# ---------------------------------------------------------------------------

def test_detect_script_ipa_classified_as_latn():
    assert detect_script("ɑɛɔ") == "Latn"


# ---------------------------------------------------------------------------
# B2 regression — script_to_langs returns sorted list
# ---------------------------------------------------------------------------

def test_script_to_langs_sorted():
    result = script_to_langs("Cyrl")
    assert result == sorted(result)
    assert len(result) > 5


def test_script_to_langs_unknown_empty():
    assert script_to_langs("Zzzz") == []


# ---------------------------------------------------------------------------
# MO4 regression — detect_script tie-breaking is deterministic
# ---------------------------------------------------------------------------

def test_detect_script_tiebreaking_deterministic():
    # Actual tie: 2 Latn (A, B) + 2 Cyrl (П, Г) → lexicographic tiebreak
    # "Latn" > "Cyrl" alphabetically → Latn wins
    text = "ABПГ"
    assert detect_script(text) == "Latn"


def test_detect_script_majority_wins():
    text = "Привет мир"  # 10 Cyrl, 0 Latn
    assert detect_script(text) == "Cyrl"


# ---------------------------------------------------------------------------
# char_script edge cases
# ---------------------------------------------------------------------------

def test_char_script_multi_char_returns_none():
    assert char_script("ab") is None
    assert char_script("") is None


def test_char_script_ogham_space_returns_none():
    """U+1680 OGHAM SPACE MARK is a space char, not a letter."""
    assert char_script("\u1680") is None


def test_char_script_bom_returns_none():
    """U+FEFF BOM should not be classified as Arabic."""
    assert char_script("\uFEFF") is None


def test_char_script_hangul_jamo_extended_a():
    """U+A960–U+A97C are Hangul Jamo Extended-A."""
    assert char_script("\uA960") == "Hang"
    assert char_script("\uA97C") == "Hang"


# ---------------------------------------------------------------------------
# New scripts and extended ranges
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch,expected", [
    ("\u0B01", "Orya"),   # Oriya/Odia range start
    ("\u0B7F", "Orya"),   # Oriya/Odia range end
    ("\u0C80", "Knda"),   # Kannada range start
    ("\u0CFF", "Knda"),   # Kannada range end
    ("\u0D00", "Mlym"),   # Malayalam range start
    ("\u0D7F", "Mlym"),   # Malayalam range end
])
def test_new_indic_scripts(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\u0980", "Beng"),   # Bengali (sanity — not in new range)
    ("\uA8E0", "Deva"),   # Devanagari Extended start
    ("\uA8FF", "Deva"),   # Devanagari Extended end
])
def test_deva_extended(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\u1C90", "Geor"),   # Georgian Extended start
    ("\u1CBF", "Geor"),   # Georgian Extended end
])
def test_georgian_extended(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\u2D80", "Ethi"),   # Ethiopic Extended start
    ("\u2DDF", "Ethi"),   # Ethiopic Extended end
    ("\uAB00", "Ethi"),   # Ethiopic Extended-A start
    ("\uAB2F", "Ethi"),   # Ethiopic Extended-A end
])
def test_ethiopic_extended(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\uAA60", "Mymr"),   # Myanmar Extended-A start
    ("\uAA7F", "Mymr"),   # Myanmar Extended-A end
    ("\uA9E0", "Mymr"),   # Myanmar Extended-B start
    ("\uA9FF", "Mymr"),   # Myanmar Extended-B end
])
def test_myanmar_extended(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\uA720", "Latn"),   # Latin Extended-D start
    ("\uA7FF", "Latn"),   # Latin Extended-D end
    ("\uAB30", "Latn"),   # Latin Extended-E start
    ("\uAB6F", "Latn"),   # Latin Extended-E end
])
def test_latin_extended_d_e(ch, expected):
    assert char_script(ch) == expected


@pytest.mark.parametrize("ch,expected", [
    ("\uFA00", "Hani"),       # CJK Compatibility Ideographs
    ("\uFAFF", "Hani"),       # CJK Compatibility Ideographs end
    ("\U0002B740", "Hani"),   # CJK Extension D start
    ("\U0002B81F", "Hani"),   # CJK Extension D end
    ("\U00030000", "Hani"),   # CJK Extension G start
    ("\U0003134F", "Hani"),   # CJK Extension G end
])
def test_han_cjk_extensions(ch, expected):
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# Registry size
# ---------------------------------------------------------------------------

def test_registry_has_34_scripts():
    assert len(SCRIPT_REGISTRY) == 34


# ---------------------------------------------------------------------------
# New lang mappings — Kannada, Malayalam, Odia, Central Kurdish
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang, expected", [
    ("kn", "Knda"),
    ("ml", "Mlym"),
    ("or", "Orya"),
    ("ckb", "Arab"),
])
def test_lang_to_script_new_scripts(lang, expected):
    assert lang_to_script(lang) == expected


def test_lang_to_script_underscore_separator():
    assert lang_to_script("pt_BR") == "Latn"
    assert lang_to_script("ru_RU") == "Cyrl"


@pytest.mark.parametrize("tag, expected", [
    ("sr-Latn", "Latn"),   # Serbian written in Latin, not its default Cyrillic
    ("uz-Cyrl", "Cyrl"),   # Uzbek written in Cyrillic, not its default Latin
    ("az-Arab", "Arab"),   # Azerbaijani in Arabic script
    ("ku-Latn", "Latn"),
    ("sr_Latn", "Latn"),   # underscore separator
])
def test_lang_to_script_honours_explicit_script_subtag(tag, expected):
    assert lang_to_script(tag) == expected


def test_lang_to_script_ignores_region_and_variant_subtags():
    # Non-script subtags must not be mistaken for a script.
    assert lang_to_script("pt-BR") == "Latn"
    assert lang_to_script("en-US") == "Latn"


# ---------------------------------------------------------------------------
# normalize_script_tag — new labels and edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label, expected", [
    ("kannada", "Knda"),
    ("malayalam", "Mlym"),
    ("odia", "Orya"),
    ("oriya", "Orya"),
    ("persian", "Arab"),
    ("farsi", "Arab"),
])
def test_normalize_new_labels(label, expected):
    assert normalize_script_tag(label) == expected


def test_normalize_whitespace():
    assert normalize_script_tag("  Latin  ") == "Latn"


def test_normalize_empty():
    assert normalize_script_tag("") is None


# ---------------------------------------------------------------------------
# char_script — boundary values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch, expected", [
    (chr(0x0040), None),   # just before A-Z
    (chr(0x005B), None),   # just after A-Z
    (chr(0x00BF), None),   # before Latin Extended
    (chr(0x0250), "Latn"),  # IPA Extensions start
    (chr(0x02AF), "Latn"),  # IPA Extensions end
    (chr(0x02B0), None),   # after IPA Extensions
    (chr(0x0300), None),   # combining grave accent
    (chr(0x036F), None),   # combining latin small letter l
])
def test_char_script_boundaries(ch, expected):
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# char_script — new script ranges
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch, expected", [
    ("\u0870", "Arab"),   # Arabic Extended-B start
    ("\u089F", "Arab"),   # Arabic Extended-B end
    ("\u1C80", "Cyrl"),   # Cyrillic Extended-C start
    ("\u1C8F", "Cyrl"),   # Cyrillic Extended-C end
    ("\u2DE0", "Cyrl"),   # Cyrillic Extended-A start
    ("\u2DFF", "Cyrl"),   # Cyrillic Extended-A end
    ("\uA640", "Cyrl"),   # Cyrillic Extended-B start
    ("\uA69F", "Cyrl"),   # Cyrillic Extended-B end
    ("\u2C60", "Latn"),   # Latin Extended-C start
    ("\u2C7F", "Latn"),   # Latin Extended-C end
    ("\U00010780", "Latn"),  # Latin Extended-F start
    ("\U000107BF", "Latn"),  # Latin Extended-F end
    ("\U0001DF00", "Latn"),  # Latin Extended-G start
    ("\U0001DFFF", "Latn"),  # Latin Extended-G end
    ("\u31F0", "Kana"),   # Katakana Phonetic Extensions start
    ("\u31FF", "Kana"),   # Katakana Phonetic Extensions end
    ("\u19E0", "Khmr"),   # Khmer Symbols start
    ("\u19FF", "Khmr"),   # Khmer Symbols end
    ("\U000116D0", "Mymr"),  # Myanmar Extended-C start
    ("\U000116FF", "Mymr"),  # Myanmar Extended-C end
    ("\U0001E7E0", "Ethi"),  # Ethiopic Extended-B start
    ("\U0001E7FF", "Ethi"),  # Ethiopic Extended-B end
    ("\U00011FC0", "Taml"),  # Tamil Supplement start
    ("\U00011FFF", "Taml"),  # Tamil Supplement end
    ("\U000111E0", "Sinh"),  # Sinhala Archaic Numbers start
    ("\U000111FF", "Sinh"),  # Sinhala Archaic Numbers end
    ("\U0002F800", "Hani"),  # CJK Compatibility Ideographs Supplement
    ("\U0002FA1F", "Hani"),  # CJK Compatibility Ideographs Supplement end
    ("\U000323B0", "Hani"),  # CJK Extension J start
    ("\U0003347F", "Hani"),  # CJK Extension J end
])
def test_char_script_new_ranges(ch, expected):
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# base_direction — Hebrew RTL
# ---------------------------------------------------------------------------

def test_base_direction_hebrew():
    assert base_direction("שלום עולם") == "rtl"


# ---------------------------------------------------------------------------
# script_to_langs — case sensitivity
# ---------------------------------------------------------------------------

def test_script_to_langs_case_sensitive():
    assert script_to_langs("cyrl") == []
    assert script_to_langs("LATN") == []


# ---------------------------------------------------------------------------
# Hangul — Syllables end and Jamo Extended-B
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch, expected", [
    (chr(0xD7AF), "Hang"),  # Hangul Syllables end
    (chr(0xD7B0), "Hang"),  # Hangul Jamo Extended-B start
    (chr(0xD7FF), "Hang"),  # Hangul Jamo Extended-B end
])
def test_hangul_extended_b(ch, expected):
    assert char_script(ch) == expected


# ---------------------------------------------------------------------------
# script_type typological metadata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code, expected", [
    ("Latn", "alphabet"),
    ("Cyrl", "alphabet"),
    ("Arab", "abjad"),
    ("Hebr", "abjad"),
    ("Deva", "abugida"),
    ("Thai", "abugida"),
    ("Hira", "syllabary"),
    ("Kana", "syllabary"),
    ("Hani", "logographic"),
    ("Hang", "featural"),
])
def test_script_type(code, expected):
    assert SCRIPT_REGISTRY[code].script_type == expected


def test_every_registered_script_is_typed():
    # No entry should be left with the default "other".
    untyped = [c for c, s in SCRIPT_REGISTRY.items() if s.script_type == "other"]
    assert untyped == []


def test_script_type_values_are_from_the_closed_set():
    allowed = {"alphabet", "abjad", "abugida", "syllabary",
               "logographic", "featural", "other"}
    assert all(s.script_type in allowed for s in SCRIPT_REGISTRY.values())


# ---------------------------------------------------------------------------
# script_runs — mixed-script segmentation
# ---------------------------------------------------------------------------

from scriptconv.scripts import script_runs  # noqa: E402


def test_script_runs_mixed():
    assert script_runs("привет hello") == [("Cyrl", "привет "), ("Latn", "hello")]


def test_script_runs_three_scripts():
    assert script_runs("Hello مرحبا world") == [
        ("Latn", "Hello "), ("Arab", "مرحبا "), ("Latn", "world"),
    ]


def test_script_runs_combining_mark_never_splits():
    # Combining acute (U+0301) attaches to the preceding Cyrillic run.
    assert script_runs("приве́т") == [("Cyrl", "приве́т")]


def test_script_runs_leading_neutrals_are_none():
    assert script_runs("  hi") == [(None, "  "), ("Latn", "hi")]


def test_script_runs_empty_and_pure_punctuation():
    assert script_runs("") == []
    assert script_runs("!!! ???") == [(None, "!!! ???")]


def test_script_runs_reconstructs_input():
    for text in ["привет hello", "Hello مرحبا world", "приве́т", "  hi", "日本語 abc"]:
        assert "".join(t for _, t in script_runs(text)) == text
