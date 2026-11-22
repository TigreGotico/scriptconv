"""Shami reads a long digit run digit by digit, as mantoq does, and does not raise.

A run of more than 15 digits is not one quantity. Python refuses to turn more
than 4,300 digits into an int, and num2words refuses numbers from about
10**306, so 4,000, 4,400 and 20,000 digits each failed before. The expected
words come from the digit names below, written by hand.
"""
import subprocess
import time

import pytest

from scriptconv.phonemizers._thirdparty.shami import espeak
from scriptconv.phonemizers._thirdparty.shami.normalize import (
    _CURRENCY_RE,
    _PERCENT_RE,
    verbalize,
)
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


@pytest.mark.parametrize("amount, expected", [
    ("١$", "one dollar"),        # Arabic-Indic digit
    ("１$", "one dollar"),        # full-width digit
    ("$5.０", "five dollars"),    # a zero decimal part adds no cents
    ("$5.٠٥", "five dollars and five cents"),
])
def test_an_amount_in_other_digits_reads_as_in_ascii_digits(amount, expected):
    assert verbalize(amount, "en") == expected


@pytest.mark.parametrize("pattern", [_CURRENCY_RE, _PERCENT_RE])
def test_a_long_digit_run_is_scanned_once(pattern):
    # Without the (?<!\d) guard each pattern retried the run from every digit:
    # 20,000 digits took 49 s (currency) and 32 s (percent).
    start = time.perf_counter()
    assert pattern.search("7" * 20000) is None
    assert time.perf_counter() - start < 5



def _words(phonemes):
    return "".join(phonemes[1:-1]).split(" ")


def _unstressed(words):
    return [word.replace("ˈ", "").replace("ˌ", "") for word in words]


@pytest.mark.parametrize("voice, text", [
    ("en-us", "xs, expected"),
    ("en-us", "zhong guo ren"),
    ("ar", "عندي سبعة كتب"),
])
def test_espeak_reads_as_with_the_text_on_the_command_line(voice, text):
    # Without a final newline on stdin, espeak-ng drops the end of the last word
    argv = subprocess.run([espeak.binary(), "-v", voice, "--ipa=1", "-q", "--", text],
                          capture_output=True, text=True, check=True).stdout
    assert espeak.phonemize(text, voice=voice).split() == argv.replace("_", "").split()


def test_espeak_reads_a_text_longer_than_one_command_line_argument():
    # Linux refuses one argument longer than 128 KiB (MAX_ARG_STRLEN) with E2BIG.
    # espeak-ng places the stress of a run by its length, so stress is not compared.
    text = " ".join([SEVEN_AR] * 20000)
    assert len(text.encode()) > 128 * 1024
    seven = _unstressed(espeak.phonemize(SEVEN_AR, voice="ar").split())
    assert _unstressed(espeak.phonemize(text, voice="ar").split()) == seven * 20000


def test_a_long_run_in_arabic_reads_each_digit_through_espeak():
    # Arabic text goes to espeak-ng in one piece. 20,000 digit words passed the
    # argument limit, and 40,000 took longer than a fixed 30 s timeout.
    # The digit word comes from a 16-digit run.
    phonemizer = ShamiPhonemizer()
    short = _words(phonemizer.phonemize("عندي " + "7" * 16, "ar")[0])
    assert len(short) == 17 and len(set(short[1:-1])) == 1
    long = _words(phonemizer.phonemize("عندي " + "7" * 40000, "ar")[0])
    assert long[0] == short[0]
    assert _unstressed(long[1:]) == _unstressed(short[1:2]) * 40000


# Seconds espeak-ng took on the text Shami sends for "عندي " and n digits,
# measured on an 8-core laptop at load 33 to 37.
MEASURED_SECONDS = {5000: 8.19, 10000: 12.50, 20000: 26.81}


@pytest.fixture
def espeak_timeouts(monkeypatch):
    timeouts = []

    def record(cmd, **kwargs):
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    espeak.phonemize.cache_clear()
    monkeypatch.setattr(subprocess, "run", record)
    yield timeouts
    espeak.phonemize.cache_clear()


def test_the_espeak_timeout_grows_with_the_text(espeak_timeouts):
    # A loaded box runs espeak-ng a few times slower, so each timeout leaves
    # four times the measured time. A short text keeps the 30 s bound.
    phonemizer = ShamiPhonemizer()
    phonemizer.phonemize("عندي سبعة كتب", "ar")
    for n in MEASURED_SECONDS:
        phonemizer.phonemize("عندي " + "7" * n, "ar")
    assert len(espeak_timeouts) == 1 + len(MEASURED_SECONDS)
    short, *long = espeak_timeouts
    assert 30 <= short < 31
    for timeout, seconds in zip(long, MEASURED_SECONDS.values()):
        assert timeout >= 4 * seconds
