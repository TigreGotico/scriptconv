"""The g2pW backend gives the symbols of Piper's ``pinyin`` phoneme type.

Each expected value comes from the reference: OHF-Voice/piper1-gpl at
d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, with the g2pW archive of
rhasspy/piper-checkpoints at revision 581dcfb1856912507627724d4ab2817a20e889ca,
run as::

    from piper.phonemize_chinese import ChinesePhonemizer
    ChinesePhonemizer(model_dir="<the unpacked g2pw.tar.gz>").phonemize(text)

The sample in ``data/g2pw_parity_zh.jsonl`` holds sentences of the FLORES-200
devtest that hold no digit, with the reference output. Piper reads digits with
its own number words before g2pW. Here that is the normalisation stage, so no
digit reaches these tests.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scriptconv.phonemizers import (
    Alphabet,
    ModelUnavailableError,
    Phonemizer,
    PhonemizerIdentity,
    UnsupportedLanguageError,
    get_phonemizer,
)
from scriptconv.phonemizers.g2pw import G2PWPhonemizer
from scriptconv.version import VERSION_STR

SAMPLE = [json.loads(line) for line in
          (Path(__file__).parent / "data" / "g2pw_parity_zh.jsonl").read_text(encoding="utf-8").splitlines()
          if not line.startswith("#")]

# Sentences written for this test, with the reference output.
REFERENCE = {
    # 行 reads háng in 银行 and xíng in 行走
    "银行在哪里？": [
        ["y", "in", "2", "h", "ang", "2", "z", "ai", "4", "n", "a", "3", "l", "i", "3", "？"]],
    "我要去行走。": [
        ["w", "o", "3", "y", "ao", "4", "q", "u", "4", "x", "ing", "2", "z", "ou", "3", "。"]],
    # ü is v after n and l, and the final of xue is ue
    "女孩穿着绿色的裙子去学校。": [
        ["n", "v", "3", "h", "ai", "2", "ch", "uan", "1", "zh", "e", "5", "l", "v", "4", "s", "e", "4",
         "d", "e", "5", "q", "un", "2", "z", "i", "5", "q", "u", "4", "x", "ue", "2", "x", "iao", "4",
         "。"]],
    # 乐 reads lè in 快乐 and yuè in 音乐
    "他们很快乐，音乐也很好听。": [
        ["t", "a", "1", "m", "en", "5", "h", "en", "3", "k", "uai", "4", "l", "e", "4", "，", "y", "in",
         "1", "y", "ue", "4", "y", "e", "3", "h", "en", "3", "h", "ao", "3", "t", "ing", "1", "。"]],
    # a lowercase Latin letter that is a symbol stays, H is not a symbol
    "Hello world, 你好！": [
        ["e", "l", "l", "o", " ", "w", "o", "r", "l", "d", ",", " ", "n", "i", "3", "h", "ao", "3", "！"]],
    # a syllable with no initial takes Ø
    "爱好和平的人们。": [
        ["Ø", "ai", "4", "h", "ao", "4", "h", "e", "2", "p", "ing", "2", "d", "e", "5", "r", "en", "2",
         "m", "en", "5", "。"]],
}


@pytest.fixture(scope="module")
def g2pw():
    return G2PWPhonemizer()


@pytest.mark.parametrize("text", REFERENCE)
def test_each_sentence_gives_the_reference_symbols(g2pw, text):
    assert g2pw.phonemize(text, "zh") == REFERENCE[text]


@pytest.mark.parametrize("row", SAMPLE, ids=[row["id"] for row in SAMPLE])
def test_the_flores_sample_gives_the_reference_symbols(g2pw, row):
    assert g2pw.phonemize(row["text"], "zh") == row["symbols"]


def test_the_sample_is_flores_sentences_with_no_digit():
    assert 0 < len(SAMPLE) <= 50
    assert not any(c.isdigit() for row in SAMPLE for c in row["text"])


def test_traditional_characters_read_as_simplified(g2pw):
    assert g2pw.phonemize("銀行在哪裡？", "zh") == REFERENCE["银行在哪里？"]


@pytest.mark.parametrize("digits", ["3", "5", "２０２４"])
def test_a_digit_gives_no_symbol(g2pw, digits):
    assert g2pw.phonemize(digits, "zh") == []


def test_double_quotes_are_removed_before_the_model(g2pw):
    assert g2pw.phonemize("“爱好和平的人们。”", "zh") == REFERENCE["爱好和平的人们。"]


def test_the_list_and_the_string_hold_the_sentences_in_order(g2pw):
    text = "女孩穿着绿色的裙子去学校。"
    symbols = [s for sentence in REFERENCE[text] for s in sentence]
    assert g2pw.phonemize_to_list(text, "zh") == symbols
    assert g2pw.phonemize_string(text, "zh") == " ".join(symbols)


def test_the_normalizer_hook_runs_before_the_backend(g2pw):
    g2pw.normalizer = lambda text, lang: "爱好和平的人们。" if text == "42" else text
    try:
        assert g2pw.phonemize("42", "zh") == REFERENCE["爱好和平的人们。"]
    finally:
        g2pw.normalizer = None


def test_the_registry_builds_the_backend():
    assert isinstance(get_phonemizer(Phonemizer.G2PW, Alphabet.PINYIN), G2PWPhonemizer)
    assert Phonemizer("g2pw") is Phonemizer.G2PW


def test_only_pinyin_symbols_are_written():
    with pytest.raises(ValueError, match="pinyin"):
        G2PWPhonemizer(Alphabet.IPA)


def test_another_language_is_refused(g2pw):
    with pytest.raises(UnsupportedLanguageError):
        g2pw.phonemize("hello", "en")


def test_the_identity_names_scriptconv(g2pw):
    assert g2pw.identity("zh-CN") == PhonemizerIdentity("g2pw", "scriptconv", VERSION_STR, "zh")


def test_a_missing_package_names_the_extra():
    with patch.dict(sys.modules, {"onnxruntime": None}):
        with pytest.raises(ImportError, match=r"scriptconv\[zh-phonemizers\]"):
            G2PWPhonemizer()


def test_offline_with_no_cache_raises_model_unavailable(tmp_path):
    code = ("from scriptconv.phonemizers import ModelUnavailableError\n"
            "from scriptconv.phonemizers.g2pw import G2PWPhonemizer\n"
            "try:\n"
            "    G2PWPhonemizer()\n"
            "except ModelUnavailableError as e:\n"
            "    print('ModelUnavailableError', e)\n")
    env = {"PATH": "", "HOME": str(tmp_path), "HF_HOME": str(tmp_path / "hf"), "HF_HUB_OFFLINE": "1"}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.stdout.startswith("ModelUnavailableError"), result.stderr
    assert "rhasspy/piper-checkpoints" in result.stdout
    assert issubclass(ModelUnavailableError, ValueError)
