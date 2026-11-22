"""Shami reads a long digit run digit by digit, as mantoq does, and does not raise.

A run of more than 15 digits is not one quantity. Python refuses to turn more
than 4,300 digits into an int, and num2words refuses numbers from about
10**306, so 4,000, 4,400 and 20,000 digits each failed before. The expected
words come from the digit names below, written by hand.
"""
import pytest

from scriptconv.phonemizers._thirdparty.shami.normalize import verbalize
from scriptconv.phonemizers.shami import ShamiPhonemizer

SEVEN_AR = "سَبعة"
SEVEN_EN = "seven"


@pytest.mark.parametrize("n", [4000, 4400, 20000])
def test_a_long_arabic_digit_run_reads_each_digit(n):
    assert verbalize("7" * n, "ar") == " ".join([SEVEN_AR] * n)


@pytest.mark.parametrize("n", [4000, 4400, 20000])
def test_a_long_english_digit_run_reads_each_digit(n):
    assert verbalize("7" * n, "en") == " ".join([SEVEN_EN] * n)


def test_a_long_run_with_a_decimal_part_reads_each_digit_of_both():
    assert verbalize("7" * 20 + ".5", "en") == " ".join([SEVEN_EN] * 20) + " point five"


def test_a_long_amount_of_money_reads_each_digit():
    assert verbalize("$" + "7" * 5000, "en") == " ".join([SEVEN_EN] * 5000) + " dollars"
    assert verbalize("$" + "7" * 5000, "ar") == " ".join([SEVEN_AR] * 5000) + " دولار"


def test_fifteen_digits_still_read_as_one_quantity():
    # 10**14 is 100 million millions in the Levantine table: مية مَلايين مَلايين
    assert verbalize("1" + "0" * 14, "ar") == "مية مَلايين مَلايين"
    assert verbalize("1" + "0" * 15, "ar") == " ".join(["واحَد"] + ["صِفِر"] * 15)


def test_one_dollar_is_singular_and_cents_keep_their_reading():
    assert verbalize("$1.05", "en") == "one dollar and five cents"
    assert verbalize("$01", "en") == "one dollar"


# 4,000 digits overflowed num2words, and 4,400 passed the int limit
@pytest.mark.parametrize("n", [4000, 4400])
def test_the_backend_reads_a_long_run_as_its_separate_digits(n):
    phonemizer = ShamiPhonemizer()
    assert phonemizer.phonemize("7" * n, "ar") == phonemizer.phonemize(" ".join("7" * n), "ar")
