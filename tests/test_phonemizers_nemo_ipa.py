"""The NeMo IPA backend gives the symbols that NVIDIA NeMo's English IpaG2p gives.

``tests/data/nemo_en_ids.json`` holds 63 lines. Each has the text, and the ids
and tokens that ``IPATokenizer.encode`` of the Magpie TTS ``english_phoneme``
sub-tokenizer gives with ``phoneme_probability`` 1.0, from an unmodified
nemo_toolkit 3.0.0 (NeMo commit fd6a877539710e2b98f28c43272ff81312f83417). The
generator is ``knowledge/wiki/audits/phoonnx-magpie-english/gen_nemo_ids.py`` of
the AgentWorkspaces tree. ``tests/data/nemo_vocab.json`` is the 96-token
vocabulary of that tokenizer, which is the first 96 tokens of the Magpie TTS
tokenizer asset. The expected string of a line is ``"".join(tokens)``.
"""
import inspect
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scriptconv.phonemizers import (
    ModelUnavailableError,
    Phonemizer,
    UnsupportedLanguageError,
    get_phonemizer,
    get_phonemizer_class,
)
from scriptconv.phonemizers.nemo_ipa import DATA_FILES, DATA_REPO, DATA_REVISION, NemoIpaPhonemizer

DATA = Path(__file__).parent / "data"
GOLD = json.loads((DATA / "nemo_en_ids.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def nemo():
    return NemoIpaPhonemizer()


def test_the_gold_has_63_lines():
    assert len(GOLD) == 63


def test_every_gold_line_reads_as_nemo(nemo):
    got = [(g["text"], nemo.phonemize_string(g["text"], "en-US")) for g in GOLD]
    assert got == [(g["text"], "".join(g["tokens"])) for g in GOLD]


def test_the_vocabulary_is_that_of_the_tokenizer(nemo):
    nemo_vocabulary = json.loads((DATA / "nemo_vocab.json").read_text(encoding="utf-8"))
    assert nemo.vocabulary == set(nemo_vocabulary[:-2])
    assert nemo_vocabulary[-2:] == ["<pad>", "<oov>"]


def test_the_output_holds_only_vocabulary_symbols(nemo):
    text = "Zoë's naïve ½ cup of Zorblax-ish 日本 café ≠ tea; 100% sure…"
    assert set(nemo.phonemize_string(text, "en-US")) <= nemo.vocabulary


def test_a_text_of_spaces_gives_nothing_and_inner_spaces_stay(nemo):
    assert nemo.phonemize_string("   ", "en-US") == ""
    assert nemo.phonemize_string(" cat  dog ", "en-US") == " " + nemo.phonemize_string("cat  dog", "en-US")


def test_a_dictionary_word_with_apostrophe_s_or_s_takes_the_ending(nemo):
    assert nemo.phonemize_string("airport's airports Jones's", "en-US") == (
        nemo.phonemize_string("airport", "en-US") + "s " + nemo.phonemize_string("airport", "en-US") + "s "
        + nemo.phonemize_string("Jones", "en-US") + "ɪz")


def test_a_hyphen_splits_a_word_that_the_dictionary_lacks(nemo):
    assert nemo.phonemize_string("cat-zzqx", "en-US") == nemo.phonemize_string("cat", "en-US") + "-ZZQX"


def test_there_is_no_probability_parameter():
    assert "phoneme_probability" not in inspect.signature(NemoIpaPhonemizer.__init__).parameters
    assert not hasattr(NemoIpaPhonemizer, "phoneme_probability")


def test_a_local_dictionary_and_heteronyms_replace_the_downloads(tmp_path):
    dictionary = tmp_path / "dictionary.txt"
    dictionary.write_text(";;; comment\nCAT  ˈkæt\nREAD  ˈɹɛd\nREAD(1)  ˈɹid\nDOG  ˈdɔɡ\n", encoding="utf-8")
    heteronyms = tmp_path / "heteronyms"
    heteronyms.write_text("dog\n", encoding="utf-8")
    local = NemoIpaPhonemizer(dictionary=dictionary, heteronyms=heteronyms)
    assert local.phonemize_string("cat read dog", "en-US") == "ˈkæt ˈɹɛd DOG"
    assert local.vocabulary >= set("CATREDOG")


def test_a_local_file_changes_the_revision(tmp_path, nemo):
    dictionary = tmp_path / "dictionary.txt"
    dictionary.write_text("CAT  ˈkæt\n", encoding="utf-8")
    heteronyms = tmp_path / "heteronyms"
    heteronyms.write_text("dog\n", encoding="utf-8")
    default = nemo.identity("en-US")
    local = NemoIpaPhonemizer(dictionary=dictionary, heteronyms=heteronyms).identity("en-US")
    other_heteronyms = tmp_path / "heteronyms-2"
    other_heteronyms.write_text("cat\n", encoding="utf-8")
    other = NemoIpaPhonemizer(dictionary=dictionary, heteronyms=other_heteronyms).identity("en-US")
    assert (default.backend, default.distribution, default.lang) == ("nemo_ipa", "scriptconv", "en-US")
    assert len({default.revision, local.revision, other.revision}) == 3
    assert default.revision.startswith("sc2:")


def test_the_registry_resolves_the_backend():
    assert Phonemizer.NEMO_IPA.value == "nemo_ipa"
    assert get_phonemizer_class(Phonemizer.NEMO_IPA) is NemoIpaPhonemizer
    assert isinstance(get_phonemizer(Phonemizer.NEMO_IPA), NemoIpaPhonemizer)


@pytest.mark.parametrize("lang, tag", [("en-US", "en-US"), ("en-Latn-US", "en-US"), ("en-US-x-nyc", "en-US-x-nyc")])
def test_american_english_is_read(lang, tag):
    assert NemoIpaPhonemizer.get_lang(lang) == tag


@pytest.mark.parametrize("lang", ["en", "en-GB", "en-AU", "pt"])
def test_other_english_and_other_languages_are_refused(lang):
    with pytest.raises(UnsupportedLanguageError, match="en-US only"):
        NemoIpaPhonemizer.get_lang(lang)


def test_no_stage_is_owned():
    assert NemoIpaPhonemizer.owned_stages == frozenset()


def test_the_pins_name_the_data_files():
    assert DATA_REPO == "Phoonnx/magpietts-multi-357m-unicode"
    assert DATA_REVISION == "a0e169ad4a160578974af51181a126d52dab6ab6"
    assert [sha for _, sha in DATA_FILES.values()] == [
        "7ea5c4c2c59cc780748b24d4ab60bd689779c4ac4ea7e27c0a8c3e20f300c0fa",
        "b701909aedf753172eff223950f8859cd4b9b4c80199cf0a6e9ac4a307c8f8ec"]


def test_a_missing_hub_package_names_the_extra():
    with patch.dict(sys.modules, {"huggingface_hub": None}):
        with pytest.raises(ImportError, match=r"scriptconv\[en-phonemizers\]"):
            NemoIpaPhonemizer()


def test_offline_with_no_cache_raises_model_unavailable(tmp_path):
    code = ("from scriptconv.phonemizers import ModelUnavailableError\n"
            "from scriptconv.phonemizers.nemo_ipa import NemoIpaPhonemizer\n"
            "try:\n"
            "    NemoIpaPhonemizer()\n"
            "except ModelUnavailableError as e:\n"
            "    print('ModelUnavailableError', e)\n")
    env = {"PATH": "", "HOME": str(tmp_path), "HF_HOME": str(tmp_path / "hf"), "HF_HUB_OFFLINE": "1"}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.stdout.startswith("ModelUnavailableError"), result.stderr
    assert DATA_REPO in result.stdout
    assert issubclass(ModelUnavailableError, ValueError)
