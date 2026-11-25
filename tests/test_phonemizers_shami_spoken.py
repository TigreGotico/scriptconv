"""The frontend reads the numbers, money and times of Shami text through text2spoken.

Shami declares ``script_languages = {"Latn": "en"}``, so an Arabic run reads in Levantine
(``apc``) and a Latin run in English. Each expected value phonemizes text2spoken's own
output, so the test checks the wiring, not a reading written here.
"""
import time
from pathlib import Path

import pytest
import text2spoken
from text2spoken import FrozenMap, NormalizationParams

from scriptconv.frontend import FrontendConfig, TextFrontend, spoken_normalizer
from scriptconv.phonemizers.shami import ShamiPhonemizer

SHAMI_DIR = Path(__file__).resolve().parents[1] / "scriptconv" / "phonemizers" / "_thirdparty" / "shami"
LATIN_AS_EN = NormalizationParams(script_languages=FrozenMap({"Latn": "en"}))


@pytest.fixture(scope="module")
def shami():
    return ShamiPhonemizer()


@pytest.fixture(scope="module")
def frontend(shami):
    return TextFrontend(FrontendConfig("apc", normalizer=spoken_normalizer()), shami)


@pytest.mark.parametrize("text", ["عندي 25 كتاب.", "الساعة 10:30 والسعر 15%.",
                                  "عندي 25 كتاب. I paid $1.05 and 1999 people came."])
def test_each_script_run_reads_its_numbers_in_its_language(shami, frontend, text):
    spoken = text2spoken.normalize(text, "apc", LATIN_AS_EN)
    assert spoken != text
    assert frontend.phonemize(text) == TextFrontend(FrontendConfig("apc"), shami).phonemize(spoken)


def test_the_english_run_is_not_read_in_arabic():
    text = "1999 people came."
    assert text2spoken.normalize(text, "apc", LATIN_AS_EN) != text2spoken.normalize(text, "apc")


def test_shami_owns_no_stage(shami):
    assert shami.owned_stages == frozenset()


def test_another_hook_gets_no_params(shami):
    calls = []

    def recording(text, lang):
        calls.append((text, lang))
        return text

    assert TextFrontend(FrontendConfig("apc", normalizer=recording), shami).phonemize("عندي 25 كتاب.")
    assert calls == [("عندي 25 كتاب.", "apc")]


def test_a_20000_digit_run_reads_with_no_error(shami):
    start = time.monotonic()
    assert shami.phonemize_string("7" * 20000, "ar")
    assert time.monotonic() - start < 30


def test_no_shami_module_reads_numbers():
    sources = {path.name: path.read_text(encoding="utf-8") for path in SHAMI_DIR.glob("*.py")}
    assert not [name for name, source in sources.items() if "num2words" in source or "def verbalize" in source]
