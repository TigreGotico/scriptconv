"""strip_diacritics keeps a mark that forms a letter of the language's alphabet.

Every string is spelled with explicit code points, so the expected values do
not depend on the normalization form an editor saves. Macedonian ѓ (U+0453) is
г (U+0433) + U+0301 in NFD, and ќ (U+045C) is к (U+043A) + U+0301.
"""
import unicodedata

import pytest

from scriptconv.diacritics import strip_diacritics

ACUTE = "\u0301"
GRAVE = "\u0300"
GJE, KJE = "\u0453", "\u045c"            # ѓ ќ
GJE_CAP, KJE_CAP = "\u0403", "\u040c"    # Ѓ Ќ
GHE, KA = "\u0433", "\u043a"             # г к
GHE_CAP, KA_CAP = "\u0413", "\u041a"     # Г К


def test_nfd_macedonian_gje_and_kje_come_out_precomposed():
    # "ќе ѓавол" in NFD: each letter is a base plus U+0301.
    text = KA + ACUTE + "\u0435 " + GHE + ACUTE + "\u0430\u0432\u043e\u043b"
    expected = KJE + "\u0435 " + GJE + "\u0430\u0432\u043e\u043b"
    assert strip_diacritics(text, "mk") == expected
    assert strip_diacritics(text, "mk-MK") == expected


def test_nfd_macedonian_capitals_come_out_precomposed():
    text = (GHE_CAP + ACUTE + "\u043e\u0440" + GHE + ACUTE + "\u0438\u0458\u0430 "
            + KA_CAP + ACUTE)
    assert strip_diacritics(text, "mk") == (
        GJE_CAP + "\u043e\u0440" + GJE + "\u0438\u0458\u0430 " + KJE_CAP)


def test_nfd_macedonian_stress_acute_removed_letter_acute_kept():
    # ѓа́вол in NFD: the acute after г forms ѓ; the acute after а is stress.
    text = GHE + ACUTE + "\u0430" + ACUTE + "\u0432\u043e\u043b"
    assert strip_diacritics(text, "mk") == GJE + "\u0430\u0432\u043e\u043b"


@pytest.mark.parametrize("nfc", [
    KJE + "\u0435 " + GJE + "\u0430\u0432\u043e\u043b",                      # ќе ѓавол
    GJE_CAP + "\u043e\u0440" + GJE + "\u0438\u0458\u0430 " + KJE_CAP,        # Ѓорѓија Ќ
    GJE + "\u0430" + ACUTE + "\u0432\u043e\u043b",                           # ѓа́вол
    "\u043a\u0443" + KJE + "\u0430" + ACUTE,                                 # куќа́
    "\u043b\u0443" + GJE + "\u0435" + ACUTE + " \u043d\u043e" + KJE,         # луѓе́ ноќ
])
def test_nfd_and_nfc_macedonian_strip_to_the_same_bytes(nfc):
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    assert strip_diacritics(nfd, "mk") == strip_diacritics(nfc, "mk")


def test_second_acute_after_a_letter_acute_is_removed():
    assert strip_diacritics(GHE + ACUTE + ACUTE, "mk") == GJE
    assert strip_diacritics(GJE + ACUTE, "mk") == GJE


def test_grave_after_gje_base_is_removed():
    # г + grave composes to no letter, so it is a stress mark.
    assert strip_diacritics(GHE + GRAVE + "\u0430", "mk") == GHE + "\u0430"


@pytest.mark.parametrize("lang", ["ru", "uk", "be", "bg", "kk"])
def test_gje_kje_are_not_letters_outside_macedonian(lang):
    text = GHE + ACUTE + "\u0430 " + KA + ACUTE + "\u0430"
    assert strip_diacritics(text, lang) == GHE + "\u0430 " + KA + "\u0430"


def test_nfc_macedonian_unchanged():
    text = KJE + "\u0435 " + GJE + "\u0430\u0432\u043e\u043b " + GJE_CAP + KJE_CAP
    assert strip_diacritics(text, "mk") == text


@pytest.mark.parametrize("text,lang,expected", [
    # ru мука́ (flour) and му́ка (torment)
    ("\u043c\u0443\u043a\u0430" + ACUTE, "ru", "\u043c\u0443\u043a\u0430"),
    ("\u043c\u0443" + ACUTE + "\u043a\u0430", "ru", "\u043c\u0443\u043a\u0430"),
    # uk за́мок
    ("\u0437\u0430" + ACUTE + "\u043c\u043e\u043a", "uk", "\u0437\u0430\u043c\u043e\u043a"),
    # bg гра́д and the IBL grave style промѝл written with a combining grave
    ("\u0433\u0440\u0430" + ACUTE + "\u0434", "bg", "\u0433\u0440\u0430\u0434"),
    ("\u043f\u0440\u043e\u043c\u0438" + GRAVE + "\u043b", "bg",
     "\u043f\u0440\u043e\u043c\u0438\u043b"),
    # mk сѐ written with a combining grave is a sign, not a letter
    ("\u0441\u0435" + GRAVE, "mk", "\u0441\u0435"),
    # lv and sl: a + acute composes to á, which neither alphabet has
    ("ma" + ACUTE + "ja", "lv", "maja"),
    ("dva" + ACUTE + "jset", "sl", "dvajset"),
])
def test_plain_stress_marks_removed_as_before(text, lang, expected):
    assert strip_diacritics(text, lang) == expected
