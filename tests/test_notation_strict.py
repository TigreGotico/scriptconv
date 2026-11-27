"""The strict contract of the notation converters.

``errors="strict"`` never drops a mark, raises on input it cannot map, and
accepts spaces. A space is a character with the Unicode White_Space property:

    0009..000D    ; White_Space # Cc   [5] <control-0009>..<control-000D>
    0020          ; White_Space # Zs       SPACE
    0085          ; White_Space # Cc       <control-0085>
    00A0          ; White_Space # Zs       NO-BREAK SPACE
    1680          ; White_Space # Zs       OGHAM SPACE MARK
    2000..200A    ; White_Space # Zs  [11] EN QUAD..HAIR SPACE
    2028          ; White_Space # Zl       LINE SEPARATOR
    2029          ; White_Space # Zp       PARAGRAPH SEPARATOR
    202F          ; White_Space # Zs       NARROW NO-BREAK SPACE
    205F          ; White_Space # Zs       MEDIUM MATHEMATICAL SPACE
    3000          ; White_Space # Zs       IDEOGRAPHIC SPACE
    -- https://www.unicode.org/Public/UCD/latest/ucd/PropList.txt

Stress marks
    "Officially, the stress marks ˈ ˌ appear before the stressed syllable [...]
    Occasionally the stress mark is placed immediately before the nucleus of
    the syllable, after any consonantal onset."
    -- https://en.wikipedia.org/wiki/International_Phonetic_Alphabet

    The expected ARPABET is the CMU Pronouncing Dictionary entry of the word.

Tie bar
    "[...] the tie bar on t͜s, though the tie bar is basically in free
    variation." -- the same article. ARPABET writes the affricates CH and JH,
    which the ARPABET table of Wikipedia gives as tʃ and dʒ.
"""
import unicodedata

import pytest

from scriptconv import notation
from scriptconv.notation import UnknownSymbolError, arpa_to_ipa, ipa_to_arpa

WHITE_SPACE = [chr(c) for c in (*range(0x09, 0x0E), 0x20, 0x85, 0xA0, 0x1680,
                                *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F,
                                0x205F, 0x3000)]

# str.isspace() is true for these four, and Unicode gives them no White_Space.
NOT_WHITE_SPACE = ["\x1c", "\x1d", "\x1e", "\x1f", "​"]

# One symbol of each notation, in both directions.
STRING_CONVERTERS = [
    (notation.xsampa_to_ipa, "S", "ʃ"), (notation.ipa_to_xsampa, "ʃ", "S"),
    (notation.lexique_to_ipa, "S", "ʃ"), (notation.ipa_to_lexique, "ʃ", "S"),
    (notation.kirshenbaum_to_ipa, "S", "ʃ"), (notation.ipa_to_kirshenbaum, "ʃ", "S"),
    (notation.cotovia_to_ipa, "a", "a"), (notation.ipa_to_cotovia, "a", "a"),
    (notation.rfe_to_ipa, "a", "a"), (notation.ipa_to_rfe, "a", "a"),
    (notation.buckwalter_to_arabic, "b", "ب"),
    (notation.arabic_to_buckwalter, "ب", "b"),
]


def test_the_white_space_list_has_the_property_count():
    assert len(WHITE_SPACE) == 25


@pytest.mark.parametrize("space", WHITE_SPACE)
@pytest.mark.parametrize("convert, symbol, value", STRING_CONVERTERS)
def test_strict_keeps_a_space_between_symbols(convert, symbol, value, space):
    # ipa_to_xsampa decomposes its input, and NFD maps U+2000 and U+2001 to
    # U+2002 and U+2003.
    out = convert(symbol + space + symbol, errors="strict")
    assert unicodedata.normalize("NFD", out) == unicodedata.normalize("NFD", value + space + value)


@pytest.mark.parametrize("errors", ["replace", "ignore"])
@pytest.mark.parametrize("convert, symbol, value", STRING_CONVERTERS)
def test_a_space_is_not_an_unknown_symbol(convert, symbol, value, errors):
    assert convert(symbol + " " + symbol, errors=errors) == value + " " + value


@pytest.mark.parametrize("char", NOT_WHITE_SPACE)
@pytest.mark.parametrize("convert, symbol, value", STRING_CONVERTERS)
def test_strict_refuses_a_control_that_is_not_white_space(convert, symbol, value, char):
    with pytest.raises(UnknownSymbolError) as caught:
        convert(symbol + char + symbol, errors="strict")
    assert caught.value.symbol == char


@pytest.mark.parametrize("space", WHITE_SPACE)
def test_ipa_to_arpa_drops_a_space_under_strict(space):
    assert ipa_to_arpa("ɛ" + space + "ɛ", errors="strict") == "EH EH"


@pytest.mark.parametrize("char", NOT_WHITE_SPACE)
def test_ipa_to_arpa_refuses_a_control_that_is_not_white_space(char):
    with pytest.raises(UnknownSymbolError) as caught:
        ipa_to_arpa("ɛ" + char + "ɛ", errors="strict")
    assert (caught.value.symbol, caught.value.position) == (char, 1)
    assert ipa_to_arpa("ɛ" + char + "ɛ") == "EH ? EH"


@pytest.mark.parametrize("space", WHITE_SPACE)
def test_arpa_to_ipa_splits_tokens_on_white_space(space):
    assert arpa_to_ipa("EH" + space + "EH", errors="strict") == "ɛɛ"


@pytest.mark.parametrize("char", NOT_WHITE_SPACE)
def test_arpa_to_ipa_does_not_split_on_a_control(char):
    with pytest.raises(UnknownSymbolError) as caught:
        arpa_to_ipa("EH" + char + "EH", errors="strict")
    assert caught.value.symbol == "EH" + char + "EH"


@pytest.mark.parametrize("space", WHITE_SPACE)
def test_halabi_keeps_a_space(space):
    assert notation.halabi_to_ipa("b" + space + "b", errors="strict") == "b" + space + "b"


def test_halabi_refuses_a_control_that_is_not_white_space():
    with pytest.raises(UnknownSymbolError) as caught:
        notation.halabi_to_ipa("b\x1cb", errors="strict")
    assert (caught.value.symbol, caught.value.position) == ("\x1c", 1)


def test_iqra_does_not_split_on_a_control():
    assert notation.iqra_halabi_to_ipa("b\x1cb") == "b\x1cb"
    with pytest.raises(UnknownSymbolError) as caught:
        notation.iqra_halabi_to_ipa("b\x1cb", errors="strict")
    assert caught.value.symbol == "b\x1cb"


@pytest.mark.parametrize("space", WHITE_SPACE)
def test_iqra_space_separates_two_phones(space):
    # phoneme_ref has no word boundary, so the space leaves no trace.
    assert notation.iqra_halabi_to_ipa("b a" + space + "b a", errors="strict") == "baba"


@pytest.mark.parametrize("ipa, mark, position", [
    ("kʰæt", "ʰ", 1),          # aspiration
    ("kæ̃t", "̃", 2),  # nasalization
    ("ɛː", "ː", 1),            # length
    ("t͡s", "͡", 1),  # a tie with no ARPABET affricate
])
def test_strict_ipa_to_arpa_names_a_mark_it_cannot_map(ipa, mark, position):
    with pytest.raises(UnknownSymbolError) as caught:
        ipa_to_arpa(ipa, errors="strict")
    assert (caught.value.symbol, caught.value.position) == (mark, position)


def test_default_ipa_to_arpa_still_drops_the_mark():
    assert ipa_to_arpa("kʰæt") == "K AE T"


@pytest.mark.parametrize("ipa, arpa", [
    ("t͡ʃ", "CH"), ("t͜ʃ", "CH"), ("d͡ʒ", "JH"), ("d͜ʒ", "JH"),
])
@pytest.mark.parametrize("errors", ["replace", "strict"])
def test_tied_affricate_is_one_arpabet_phone(ipa, arpa, errors):
    assert ipa_to_arpa(ipa, errors=errors) == arpa


# CMU Pronouncing Dictionary entries. The IPA puts the stress mark before the
# syllable, so before its onset.
CMU_STRESS = [
    ("ˈkæt", "K AE1 T"),
    ("ˈstɹɔŋ", "S T R AO1 NG"),
    ("bəˈnænə", "B AH0 N AE1 N AH0"),
    ("fəˈtɑɡɹəfi", "F AH0 T AA1 G R AH0 F IY0"),
]


@pytest.mark.parametrize("ipa, arpa", CMU_STRESS)
@pytest.mark.parametrize("errors", ["replace", "strict"])
def test_stress_mark_before_the_onset_reaches_the_vowel(ipa, arpa, errors):
    assert ipa_to_arpa(ipa, stress=True, errors=errors) == arpa


@pytest.mark.parametrize("ipa, arpa", CMU_STRESS)
def test_stress_mark_before_the_nucleus_gives_the_same_digits(ipa, arpa):
    onset, rest = ipa.split("ˈ")
    i = next(k for k, ch in enumerate(rest) if ch in "æɔɑ")
    assert ipa_to_arpa(onset + rest[:i] + "ˈ" + rest[i:], stress=True, errors="strict") == arpa


def test_stress_mark_does_not_cross_a_space():
    assert ipa_to_arpa("ˈ kæt", stress=True) == "K AE0 T"
    with pytest.raises(UnknownSymbolError) as caught:
        ipa_to_arpa("ˈ kæt", stress=True, errors="strict")
    assert (caught.value.symbol, caught.value.position) == ("ˈ", 0)


def test_strict_refuses_a_stress_mark_that_no_vowel_follows():
    with pytest.raises(UnknownSymbolError) as caught:
        ipa_to_arpa("kæˈt", stress=True, errors="strict")
    assert (caught.value.symbol, caught.value.position) == ("ˈ", 2)


def test_stress_false_drops_the_stress_mark_on_request():
    assert ipa_to_arpa("ˈkæt", errors="strict") == "K AE T"


# A syllabic consonant is the nucleus of its syllable, and ARPABET gives EL, EM,
# EN and ENG no stress digit.
@pytest.mark.parametrize("ipa", ["ˈl̩ə", "ˈbl̩ə", "ˈm̩ə", "ˈn̩ə", "ˈŋ̍ə", "ˌl̩ə"])
def test_strict_refuses_a_stress_mark_on_a_syllabic_consonant(ipa):
    with pytest.raises(UnknownSymbolError) as caught:
        ipa_to_arpa(ipa, stress=True, errors="strict")
    assert (caught.value.symbol, caught.value.position) == (ipa[0], 0)


@pytest.mark.parametrize("errors", ["replace", "pass", "ignore"])
def test_other_policies_give_the_digit_to_the_next_vowel(errors):
    assert ipa_to_arpa("ˈl̩ə", stress=True, errors=errors) == "EL AH1"


def test_strict_stresses_the_vowel_before_a_syllabic_consonant():
    # The vowel takes the digit first, so no stress is pending at the n.
    assert ipa_to_arpa("ˈbʌtn̩", stress=True, errors="strict") == "B AH1 T EN"
