"""strip_diacritics keeps a mark that forms a letter of the language's alphabet.

Every string is spelled with explicit code points, so the expected values do
not depend on the normalization form an editor saves. Macedonian ѓ (U+0453) is
г (U+0433) + U+0301 in NFD, and ќ (U+045C) is к (U+043A) + U+0301.
"""
import unicodedata

import pytest

from scriptconv.diacritics import strip_diacritics

ACUTE = "́"
GRAVE = "̀"
GJE, KJE = "ѓ", "ќ"            # ѓ ќ
GJE_CAP, KJE_CAP = "Ѓ", "Ќ"    # Ѓ Ќ
GHE, KA = "г", "к"             # г к
GHE_CAP, KA_CAP = "Г", "К"     # Г К


def test_nfd_macedonian_gje_and_kje_survive():
    # "ќе ѓавол" in NFD: each letter is a base plus U+0301.
    text = KA + ACUTE + "е " + GHE + ACUTE + "авол"
    assert strip_diacritics(text, "mk") == text
    assert strip_diacritics(text, "mk-MK") == text


def test_nfd_macedonian_capitals_survive():
    text = GHE_CAP + ACUTE + "ор" + GHE + ACUTE + "ија " + KA_CAP + ACUTE
    assert strip_diacritics(text, "mk") == text


def test_nfd_macedonian_stress_acute_removed_letter_acute_kept():
    # ѓа́вол in NFD: the acute after г forms ѓ; the acute after а is stress.
    text = GHE + ACUTE + "а" + ACUTE + "вол"
    assert strip_diacritics(text, "mk") == GHE + ACUTE + "авол"


def test_nfd_and_nfc_macedonian_give_the_same_letters():
    nfc = KJE + "е" + ACUTE + " " + GJE + "а" + ACUTE + "вол"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    expected_nfc = KJE + "е " + GJE + "авол"
    assert strip_diacritics(nfc, "mk") == expected_nfc
    assert unicodedata.normalize("NFC", strip_diacritics(nfd, "mk")) == expected_nfc


def test_second_acute_after_a_letter_acute_is_removed():
    assert strip_diacritics(GHE + ACUTE + ACUTE, "mk") == GHE + ACUTE


def test_grave_after_gje_base_is_removed():
    # г + grave composes to no letter, so it is a stress mark.
    assert strip_diacritics(GHE + GRAVE + "а", "mk") == GHE + "а"


@pytest.mark.parametrize("lang", ["ru", "uk", "be", "bg", "kk"])
def test_gje_kje_are_not_letters_outside_macedonian(lang):
    text = GHE + ACUTE + "а " + KA + ACUTE + "а"
    assert strip_diacritics(text, lang) == GHE + "а " + KA + "а"


def test_nfc_macedonian_unchanged():
    text = KJE + "е " + GJE + "авол " + GJE_CAP + KJE_CAP
    assert strip_diacritics(text, "mk") == text


@pytest.mark.parametrize("text,lang,expected", [
    # ru мука́ (flour) and му́ка (torment)
    ("мука" + ACUTE, "ru", "мука"),
    ("му" + ACUTE + "ка", "ru", "мука"),
    # uk за́мок
    ("за" + ACUTE + "мок", "uk", "замок"),
    # bg гра́д and the IBL grave style промѝл written with a combining grave
    ("гра" + ACUTE + "д", "bg", "град"),
    ("проми" + GRAVE + "л", "bg",
     "промил"),
    # mk сѐ written with a combining grave is a sign, not a letter
    ("се" + GRAVE, "mk", "се"),
    # lv and sl: a + acute composes to á, which neither alphabet has
    ("ma" + ACUTE + "ja", "lv", "maja"),
    ("dva" + ACUTE + "jset", "sl", "dvajset"),
])
def test_plain_stress_marks_removed_as_before(text, lang, expected):
    assert strip_diacritics(text, lang) == expected
