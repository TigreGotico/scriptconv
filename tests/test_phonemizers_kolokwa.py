"""The Kolokwa backend gives the output of the upstream model.

Each expected value comes from the upstream code: ``phonemize`` 0.2.4 with
``best_model.pt`` of michsethowusu/kolokwa-g2p at revision
92ed3b721a4f80f98d5b741fdd16352ca320f121, on torch 2.8.0, run as::

    Phonemizer.from_checkpoint("best_model.pt")(text, lang="en_lr")

For the word ``wetin``, the ``lexicon.tsv`` of that revision gives the same IPA.
The words of the first three texts are in the dictionary of the checkpoint.
The other texts hold words that are not, so the ONNX model reads them.
"""
import subprocess
import sys

from importlib import metadata

import pytest

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import (
    Phonemizer,
    UnsupportedLanguageError,
    get_phonemizer,
    phonemizer_for_lang,
)
from scriptconv.phonemizers.lir import KolokwaPhonemizer

REFERENCE = {
    "da man dey go drink cold water": "ðæ mæ̃n de ko tɹɪ̃ŋk ko wɔtə˞",
    "wetin we coming learn about our brother and sister them":
        "wɛtɪ̃ŋ wi kʰʌmɪ̃ŋ læ̃n əbaʊt aʊə˞ pɹʌðə˞ nd sɪstə˞ ðɛ̃m",
    "wetin": "wɛtɪ̃ŋ",
    # the apostrophe goes, and "aarons" and "abigails" are not in the dictionary
    "aaron's abigail's": "ɛɹənz æbɪɡɪlz",
    # DIY splits before each capital; the hyphens and the brackets stay
    "DIY Liberia-Monrovia (wetin?)": "d-a-j la-mɔɹojo (wɛtɪ̃ŋ?)",
    "McDonald's pikin, palava / bluff: 25 people": "mi-tontʰ pʰɪɪ̃, plawɔ / plʌf:  pʰipəl",
    # the model gives id 0 between two ids of k; without it they are one k
    "gaaiqqot": "kɑt",
    # the digit stays in the word, so "man2" is not in the dictionary and the model reads it
    "man2": "mɛ̃n",
}


@pytest.fixture(scope="module")
def kolokwa():
    return get_phonemizer(Phonemizer.KOLOKWA)


@pytest.mark.parametrize("text", REFERENCE)
def test_each_text_gives_the_upstream_ipa(kolokwa, text):
    assert kolokwa.phonemize_string(text, "lir") == REFERENCE[text]


def test_lir_reads_as_the_en_lr_key_of_the_model():
    assert KolokwaPhonemizer.get_lang("lir") == "en_lr"


@pytest.mark.parametrize("lang", ["en", "en-US", "kqr"])
def test_other_languages_are_refused(lang):
    with pytest.raises(UnsupportedLanguageError):
        KolokwaPhonemizer.get_lang(lang)


def test_lir_defaults_to_kolokwa(kolokwa):
    assert type(phonemizer_for_lang("lir")) is KolokwaPhonemizer


def test_identity_has_a_revision(kolokwa):
    identity = kolokwa.identity("lir")
    assert (identity.backend, identity.distribution, identity.lang) == ("kolokwa", "scriptconv", "en_lr")
    assert identity.revision == f"scriptconv=={metadata.version('scriptconv')}"
    assert TextFrontend(FrontendConfig("lir", Phonemizer.KOLOKWA)).identity().revision == identity.revision


def test_offline_with_no_cache_raises_model_unavailable(tmp_path):
    code = ("from scriptconv.phonemizers import ModelUnavailableError\n"
            "from scriptconv.phonemizers.lir import KolokwaPhonemizer\n"
            "try:\n"
            "    KolokwaPhonemizer()\n"
            "except ModelUnavailableError as e:\n"
            "    print('ModelUnavailableError', e)\n")
    env = {"PATH": "", "HOME": str(tmp_path), "HF_HOME": str(tmp_path / "hf"), "HF_HUB_OFFLINE": "1"}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.stdout.startswith("ModelUnavailableError"), result.stderr
    assert "TigreGotico/kolokwa-g2p-onnx" in result.stdout
