"""Hebrew niqqud from Nakdimon: ``diacritize(text, "he", diacritizer_model="nakdimon")``.

Each expected value comes from the reference: OHF-Voice/piper1-gpl at
d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, the text that
``HebrewPhonemizer.phonemize`` passes to ``hebrew_to_ipa``, run as::

    from piper.phonemize_hebrew import HebrewPhonemizer
    HebrewPhonemizer().diacritizer(text)

The sample in ``data/nakdimon_parity_he.jsonl`` holds sentences of the
FLORES-200 devtest with the reference output.
"""
import json
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from scriptconv import diacritics
from scriptconv.diacritics import diacritize, strip_diacritics
from scriptconv.phonemizers import ModelUnavailableError
from scriptconv.phonemizers._thirdparty.nakdimon import remove_niqqud

SAMPLE = [json.loads(line) for line in
          (Path(__file__).parent / "data" / "nakdimon_parity_he.jsonl").read_text(encoding="utf-8").splitlines()
          if not line.startswith("#")]


@pytest.mark.parametrize("row", SAMPLE, ids=[row["id"] for row in SAMPLE])
def test_the_flores_sample_gives_the_reference_niqqud(row):
    assert diacritize(row["text"], "he", diacritizer_model="nakdimon") == row["niqqud"]


def test_the_sample_holds_at_most_fifty_sentences():
    assert 0 < len(SAMPLE) <= 50


@pytest.mark.parametrize("row", SAMPLE[:5], ids=[row["id"] for row in SAMPLE[:5]])
def test_the_marks_keep_the_letters(row):
    marked = diacritize(row["text"], "he", diacritizer_model="nakdimon")
    assert remove_niqqud(marked) == row["text"]
    assert strip_diacritics(marked, "he") == row["text"]


def test_text_with_niqqud_stays_as_written():
    dotted = SAMPLE[0]["niqqud"]
    assert diacritize(dotted, "he", diacritizer_model="nakdimon") == dotted


def test_phonikud_stays_the_default_for_hebrew():
    class Phonikud:
        def add_diacritics(self, text):
            return "phonikud:" + text

    with patch.object(diacritics, "_phonikud", lambda model: Phonikud()), \
            patch.object(diacritics, "_nakdimon", side_effect=AssertionError("nakdimon ran")):
        assert diacritize("שלום", "he") == "phonikud:שלום"


def _fresh_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIPTCONV_CACHE", str(tmp_path))
    monkeypatch.setattr(diacritics, "_NAKDIMON_CACHE", {})
    return tmp_path / "scriptconv" / "nakdimon"


def test_offline_with_no_cache_raises_model_unavailable(tmp_path, monkeypatch):
    cache = _fresh_cache(tmp_path, monkeypatch)

    def offline(url):
        raise urllib.error.URLError("network is unreachable")

    monkeypatch.setattr(diacritics.urllib.request, "urlopen", offline)
    with pytest.raises(ModelUnavailableError, match="Nakdimon"):
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert list(cache.iterdir()) == []


def test_a_download_with_another_sha256_is_discarded(tmp_path, monkeypatch):
    cache = _fresh_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(diacritics.urllib.request, "urlopen", lambda url: BytesIO(b"not the model"))
    with pytest.raises(ModelUnavailableError, match="sha256"):
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert list(cache.iterdir()) == []


def test_a_missing_package_names_the_extra():
    with patch.dict(sys.modules, {"onnxruntime": None}):
        with pytest.raises(ImportError, match=r"scriptconv\[he\]"):
            diacritize("שלום", "he", diacritizer_model="nakdimon")
