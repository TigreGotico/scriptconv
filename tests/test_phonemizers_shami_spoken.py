"""Shami reads numbers, money and times through text2spoken, per span.

An Arabic span reads with text2spoken's Levantine (``apc``) reading and an English
span with its English one. Each expected value phonemizes text2spoken's own output,
so the test checks the wiring, not a reading written here.
"""
import time
from pathlib import Path

import pytest
import text2spoken

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers.shami import ShamiPhonemizer

SHAMI_DIR = Path(__file__).resolve().parents[1] / "scriptconv" / "phonemizers" / "_thirdparty" / "shami"


@pytest.fixture(scope="module")
def shami():
    return ShamiPhonemizer()


@pytest.mark.parametrize("text", ["عندي 25 كتاب.", "الساعة 10:30 والسعر 15%."])
def test_an_arabic_span_reads_its_numbers_in_levantine(shami, text):
    spoken = text2spoken.normalize(text, "apc")
    assert spoken != text
    assert shami.phonemize_string(text, "ar") == shami.phonemize_string(spoken, "ar")


def test_the_levantine_reading_is_not_the_standard_arabic_one(shami):
    text = "عندي 25 كتاب."
    levantine = text2spoken.normalize(text, "apc")
    standard = text2spoken.normalize(text, "ar")
    assert levantine != standard
    assert shami.phonemize_string(text, "ar") != shami.phonemize_string(standard, "ar")


@pytest.mark.parametrize("text", ["I paid $1.05 and 1999 people came.", "We met at 10:30."])
def test_an_english_span_reads_its_numbers_in_english(shami, text):
    spoken = text2spoken.normalize(text, "en")
    assert spoken != text
    assert shami.phonemize_string(text, "ar") == shami.phonemize_string(spoken, "ar")


def test_the_frontend_hook_does_not_run_before_shami():
    calls = []

    def recording(text, lang):
        calls.append(text)
        return text

    frontend = TextFrontend(FrontendConfig("ar", normalizer=recording), ShamiPhonemizer())
    assert frontend.phonemize("عندي 25 كتاب.")
    assert calls == []


def test_a_20000_digit_run_reads_with_no_error(shami):
    start = time.monotonic()
    assert shami.phonemize_string("7" * 20000, "ar")
    assert time.monotonic() - start < 30


def test_no_shami_module_imports_num2words():
    assert not [path.name for path in SHAMI_DIR.glob("*.py") if "num2words" in path.read_text(encoding="utf-8")]
