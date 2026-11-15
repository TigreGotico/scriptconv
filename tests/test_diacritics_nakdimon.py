"""Hebrew niqqud from Nakdimon: ``diacritize(text, "he", diacritizer_model="nakdimon")``.

Each expected value comes from the reference: OHF-Voice/piper1-gpl at
d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, the text that
``HebrewPhonemizer.phonemize`` passes to ``hebrew_to_ipa``, run as::

    from piper.phonemize_hebrew import HebrewPhonemizer
    HebrewPhonemizer().diacritizer(text)

The sample in ``data/nakdimon_parity_he.jsonl`` holds sentences of the
FLORES-200 devtest with the reference output.
"""
import base64
import http.client
import json
import os
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


# The dotted sentences of Piper's Hebrew tests, then words that Nakdimon
# reads another way when their marks are removed: שָׁלֹם gives שָׁלֵם, and
# qamats qatan (U+05C7) is a mark that Nakdimon never writes.
DOTTED = ["הַכּוֹחַ לְשַׁנּוֹת מַתְחִיל בָּרֶגַע שֶׁבּוֹ אַתָּה מַאֲמִין שֶׁזֶּה אֶפְשָׁרִי!", "הַכּוֹחַ",
          "נִרְאֵית לְעֵינֵינוּ בְּטִפּוֹת", "נִרְאֵית", "בְּטִפּוֹת", "יִשְׁמְרוּ", "מְדַבְּרִים", "שָׁלֹם",
          "ח\u05c7כמה", "כ\u05c7ל העם"]


@pytest.mark.parametrize("dotted", DOTTED)
def test_text_with_niqqud_stays_as_written(dotted):
    assert diacritize(dotted, "he", diacritizer_model="nakdimon") == dotted


# הַךְּ, "strike", is the one word of the reference run with a dagesh in final kaf.
@pytest.mark.parametrize("text, niqqud", [("הך", "ה\u05b7ך\u05bc\u05b0"),
                                           ("והך", "ו\u05b0ה\u05b7ך\u05bc\u05b0")])
def test_final_kaf_takes_a_dagesh(text, niqqud):
    assert diacritize(text, "he", diacritizer_model="nakdimon") == niqqud


def test_phonikud_stays_the_default_for_hebrew():
    class Phonikud:
        def add_diacritics(self, text):
            return "phonikud:" + text

    with patch.object(diacritics, "_phonikud", lambda model: Phonikud()), \
            patch.object(diacritics, "_nakdimon", side_effect=AssertionError("nakdimon ran")):
        assert diacritize("שלום", "he") == "phonikud:שלום"


# A valid ONNX model that is not Nakdimon: one Identity node.
OTHER_MODEL = base64.b64decode("CAg6QgoQCgF4EgF5IghJZGVudGl0eRIIaWRlbnRpdHlaEQoBeBIMCgoIARIGCgIIAQoAYhEKAXkSDAoKCAESBgoCCAEKAEIECgAQDQ==")
PINNED_NAME = "Nakdimon-ab08a8c47daf.onnx"


@pytest.fixture(scope="module")
def model_bytes():
    """The bytes of the pinned model, from the cache that the other tests use."""
    diacritize("שלום", "he", diacritizer_model="nakdimon")
    base = os.environ.get("SCRIPTCONV_CACHE") or os.environ.get(
        "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return (Path(base) / "scriptconv" / "nakdimon" / PINNED_NAME).read_bytes()


def _fresh_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIPTCONV_CACHE", str(tmp_path))
    monkeypatch.setattr(diacritics, "_NAKDIMON_CACHE", {})
    return tmp_path / "scriptconv" / "nakdimon"


def _offline(url):
    raise urllib.error.URLError("network is unreachable")


def test_offline_with_no_cache_raises_model_unavailable(tmp_path, monkeypatch):
    cache = _fresh_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(diacritics.urllib.request, "urlopen", _offline)
    with pytest.raises(ModelUnavailableError, match="Nakdimon"):
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert list(cache.iterdir()) == []


def test_a_download_with_another_sha256_is_discarded(tmp_path, monkeypatch):
    cache = _fresh_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(diacritics.urllib.request, "urlopen", lambda url: BytesIO(b"not the model"))
    with pytest.raises(ModelUnavailableError, match="sha256"):
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize("cached", ["garbage", "truncated", "other model"])
def test_a_cached_model_that_fails_its_check_offline_raises_model_unavailable(
        tmp_path, monkeypatch, model_bytes, cached):
    cache = _fresh_cache(tmp_path, monkeypatch)
    cache.mkdir(parents=True)
    content = {"garbage": b"not a model", "truncated": model_bytes[:len(model_bytes) // 2],
               "other model": OTHER_MODEL}[cached]
    (cache / PINNED_NAME).write_bytes(content)
    monkeypatch.setattr(diacritics.urllib.request, "urlopen", _offline)
    with pytest.raises(ModelUnavailableError, match=PINNED_NAME) as error:
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert "sha256" in str(error.value) and "network is unreachable" in str(error.value)
    assert list(cache.iterdir()) == []


def test_a_cached_model_that_fails_its_check_is_downloaded_again(tmp_path, monkeypatch, model_bytes):
    cache = _fresh_cache(tmp_path, monkeypatch)
    cache.mkdir(parents=True)
    (cache / PINNED_NAME).write_bytes(b"not a model")
    urls = []
    monkeypatch.setattr(diacritics.urllib.request, "urlopen",
                        lambda url: urls.append(url) or BytesIO(model_bytes))
    assert diacritize("הך", "he", diacritizer_model="nakdimon") == "ה\u05b7ך\u05bc\u05b0"
    assert len(urls) == 1
    assert (cache / PINNED_NAME).read_bytes() == model_bytes


class _DroppedResponse(BytesIO):
    def read(self, size=-1):
        raise http.client.IncompleteRead(b"partial", 1024)


def test_a_dropped_download_raises_model_unavailable(tmp_path, monkeypatch):
    cache = _fresh_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(diacritics.urllib.request, "urlopen", lambda url: _DroppedResponse())
    with pytest.raises(ModelUnavailableError, match="IncompleteRead"):
        diacritize("שלום", "he", diacritizer_model="nakdimon")
    assert list(cache.iterdir()) == []


def test_a_missing_package_names_the_extra():
    with patch.dict(sys.modules, {"onnxruntime": None}):
        with pytest.raises(ImportError, match=r"scriptconv\[he\]"):
            diacritize("שלום", "he", diacritizer_model="nakdimon")
