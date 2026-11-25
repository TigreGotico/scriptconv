"""The Leokani G2P backend gives upstream's own output.

The expected values come from upstream: ``goldens.json`` and
``mini/goldens.json`` of the Hugging Face model milliwattlabs/leokani-g2p at
revision a819acc86471a04a01ba3d3f30f3765e4675c7ca, and the examples of its
README at that revision. Upstream's ``tests/test_goldens.py`` reads each golden
the way these tests do: a piece through ``normalize(piece, pauses=False)`` and
``piece``, a line through ``normalize`` and ``phonemize``.
"""
import json
import subprocess
import sys
from unittest.mock import patch

from importlib import metadata

import pytest
from huggingface_hub import hf_hub_download

from scriptconv.phonemizers import (
    ModelUnavailableError,
    Phonemizer,
    UnsupportedLanguageError,
    get_phonemizer,
    get_phonemizer_class,
)
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.leokani import LeokaniPhonemizer

UPSTREAM = ("milliwattlabs/leokani-g2p", "a819acc86471a04a01ba3d3f30f3765e4675c7ca")
GOLDENS = {"micro": "goldens.json", "mini": "mini/goldens.json"}
# Every SAMPLE-th golden of each kind.
SAMPLE = 10


@pytest.fixture(scope="module", params=list(GOLDENS))
def variant(request):
    repo, revision = UPSTREAM
    with open(hf_hub_download(repo, GOLDENS[request.param], revision=revision), encoding="utf-8") as f:
        gold = json.load(f)
    return LeokaniPhonemizer(model=request.param), gold


def test_the_goldens_are_of_the_variant(variant):
    backend, gold = variant
    assert gold["variant"] == backend.model == backend.engine.variant


def test_a_sample_of_the_piece_goldens_reads_as_upstream(variant):
    backend, gold = variant
    sample = gold["pieces"][::SAMPLE]
    got = [(g["piece"], backend.engine.normalize(g["piece"], pauses=False), backend.engine.piece(g["piece"]))
           for g in sample]
    assert len(sample) >= 39
    assert got == [(g["piece"], g["normalized"], g["leokani"]) for g in sample]


def test_a_sample_of_the_line_goldens_reads_as_upstream(variant):
    backend, gold = variant
    sample = (gold["lines"] + gold["edge"])[::SAMPLE]
    got = [(g["text"], backend.engine.normalize(g["text"]), backend.phonemize_string(g["text"], "en-US"))
           for g in sample]
    assert len(sample) >= 211
    assert got == [(g["text"], g["normalized"], g["leokani"]) for g in sample]


@pytest.fixture(scope="module")
def leokani():
    return get_phonemizer(Phonemizer.LEOKANI)


@pytest.mark.parametrize("text, phonemes", [
    # goldens.json, the piece "sunscreen"
    ("sunscreen", "sˈʌnskɹin"),
    # the examples of upstream's README
    ("The wind was cold, so we read inside.", "ðə wˈɪnd wʌz kˈOld, sˌO wi ɹˈid ɪnsˈId."),
    ("Dr. Okafor lands at 7:45 AM.", "dˈɑktəɹ ˈɑkæfəɹ lˈændz æt sˈɛvən fˈɔɹɾi fˈIv ˌAˈɛm."),
])
def test_the_registry_backend_reads_as_upstream(leokani, text, phonemes):
    assert leokani.phonemize_string(text, "en-US") == phonemes


def test_the_misaki_alphabet_gives_the_codes_of_the_ipa_alphabet(leokani):
    misaki = get_phonemizer(Phonemizer.LEOKANI, Alphabet.MISAKI)
    text = "The wind was cold, so we read inside."
    assert misaki.phonemize_string(text, "en-US") == leokani.phonemize_string(text, "en-US")


def test_phonemize_reads_the_words_without_the_punctuation(leokani):
    assert leokani.phonemize("The wind was cold, so we read inside.", "en-US") == \
        [list("ðə wˈɪnd wʌz kˈOld sˌO wi ɹˈid ɪnsˈId")]


def test_the_mini_variant_comes_from_the_registry():
    mini = get_phonemizer(Phonemizer.LEOKANI, model="mini")
    assert mini.engine.variant == "mini"
    assert mini.engine.directory.endswith("/mini")


def test_an_unknown_variant_is_refused():
    with pytest.raises(ValueError, match="'huge'"):
        LeokaniPhonemizer(model="huge")


@pytest.mark.parametrize("lang, tag", [("en-US", "en-US"), ("en-Latn-US", "en-US"), ("en-US-x-nyc", "en-US-x-nyc")])
def test_american_english_is_read(lang, tag):
    assert LeokaniPhonemizer.get_lang(lang) == tag


@pytest.mark.parametrize("lang", ["en", "en-GB", "en-AU", "pt"])
def test_other_english_and_other_languages_are_refused(lang):
    with pytest.raises(UnsupportedLanguageError, match="en-US only"):
        LeokaniPhonemizer.get_lang(lang)


def test_the_identity_names_scriptconv(leokani):
    identity = leokani.identity("en-US")
    assert (identity.backend, identity.distribution, identity.lang) == ("leokani", "scriptconv", "en-US")
    assert identity.revision == f"scriptconv=={metadata.version('scriptconv')}"


def test_a_missing_package_names_the_extra():
    with patch.dict(sys.modules, {"onnxruntime": None}):
        sys.modules.pop("scriptconv.phonemizers.leokani")
        with pytest.raises(ImportError, match=r"scriptconv\[en-phonemizers\]"):
            get_phonemizer_class(Phonemizer.LEOKANI)


def test_offline_with_no_cache_raises_model_unavailable(tmp_path):
    code = ("from scriptconv.phonemizers import ModelUnavailableError\n"
            "from scriptconv.phonemizers.leokani import LeokaniPhonemizer\n"
            "try:\n"
            "    LeokaniPhonemizer()\n"
            "except ModelUnavailableError as e:\n"
            "    print('ModelUnavailableError', e)\n")
    env = {"PATH": "", "HOME": str(tmp_path), "HF_HOME": str(tmp_path / "hf"), "HF_HUB_OFFLINE": "1"}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.stdout.startswith("ModelUnavailableError"), result.stderr
    assert "milliwattlabs/leokani-g2p" in result.stdout
    assert issubclass(ModelUnavailableError, ValueError)
