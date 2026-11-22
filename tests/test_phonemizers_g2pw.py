"""The g2pW backend gives the reference symbols.

Each expected value comes from the reference: OHF-Voice/piper1-gpl at
d76f335d9eb5dea5ef6d7d70b2d6114e6303fa08, with the g2pW archive of
rhasspy/piper-checkpoints at revision 581dcfb1856912507627724d4ab2817a20e889ca,
run as::

    from piper.phonemize_chinese import ChinesePhonemizer
    ChinesePhonemizer(model_dir="<the unpacked g2pw.tar.gz>").phonemize(text)

The sample in ``data/g2pw_parity_zh.jsonl`` holds sentences of the FLORES-200
devtest that hold no digit, with the reference output. The reference reads
digits with its own number words before g2pW. Here that is the normalisation
stage, so the parity rows hold no digit.
"""
import gzip
import io
import json
import logging
import re
import subprocess
import tarfile
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scriptconv.phonemizers import (
    Alphabet,
    ModelUnavailableError,
    Phonemizer,
    PhonemizerIdentity,
    UnreadTextError,
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
    # The reference keeps the lowercase letters as symbols: e l l o, w o r l d.
    # Latin letters are unread text here, and the space and comma stay.
    "Hello world, 你好！": [
        [" ", ",", " ", "n", "i", "3", "h", "ao", "3", "！"]],
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


def _is_without_letters(reference: list, output: list, letters: str) -> bool:
    """Whether *output* is *reference* with the symbols of *letters* taken out, in their order.

    The reference writes each lowercase ASCII letter of the text as a symbol of
    its own, and the backend reads Latin letters as unread text. A letter such
    as ``a`` is also a final, so the test tries every way to take the letters
    out of the reference.
    """
    reachable = {(0, 0)}
    for symbol in reference:
        following = set()
        for kept, taken in reachable:
            if kept < len(output) and output[kept] == symbol:
                following.add((kept + 1, taken))
            if taken < len(letters) and letters[taken] == symbol:
                following.add((kept, taken + 1))
        reachable = following
    return (len(output), len(letters)) in reachable


@pytest.mark.parametrize("row", SAMPLE, ids=[row["id"] for row in SAMPLE])
def test_the_flores_sample_gives_the_reference_symbols(g2pw, row):
    output = g2pw.phonemize(row["text"], "zh")
    letters = "".join(re.findall("[a-z]", row["text"]))
    if not letters:
        assert output == row["symbols"]
    else:
        assert len(output) <= len(row["symbols"])
        assert _is_without_letters([s for sentence in row["symbols"] for s in sentence],
                                   [s for sentence in output for s in sentence], letters)


def test_the_sample_is_flores_sentences_with_no_digit():
    assert 0 < len(SAMPLE) <= 50
    assert not any(c.isdigit() for row in SAMPLE for c in row["text"])


def test_traditional_characters_read_as_simplified(g2pw):
    assert g2pw.phonemize("銀行在哪裡？", "zh") == REFERENCE["银行在哪里？"]


@pytest.mark.parametrize("digits", ["3", "5", "２０２４"])
def test_a_digit_gives_no_symbol(g2pw, digits):
    assert g2pw.phonemize(digits, "zh") == []


# The reference gives s an 1 for the 3, with its own number words.
APPLES = ["w", "o", "3", "y", "ou", "3", "g", "e", "5", "p", "ing", "2", "g", "uo", "3", "。"]


def test_a_dropped_digit_is_named_in_a_warning(g2pw, caplog):
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize("我有3个苹果。", "zh") == [APPLES]
    assert any("'3'" in record.getMessage() for record in caplog.records)


def test_a_dropped_digit_raises_in_strict_mode(g2pw):
    g2pw.strict = True
    try:
        with pytest.raises(UnreadTextError, match="'3'") as error:
            g2pw.phonemize("我有3个苹果。", "zh")
    finally:
        g2pw.strict = False
    assert error.value.unread == ("3",)


def test_a_full_width_digit_is_unread(g2pw, caplog):
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize("我有３个苹果。", "zh") == [APPLES]
    assert [record.getMessage() for record in caplog.records] == [
        "g2pW gives no symbol for '３' in '我有３个苹果。'; numbers belong to the normalisation stage"]
    g2pw.strict = True
    try:
        with pytest.raises(UnreadTextError) as error:
            g2pw.phonemize("我有３个苹果。", "zh")
    finally:
        g2pw.strict = False
    assert error.value.unread == ("３",)


def test_each_number_is_named_on_its_own(g2pw, caplog):
    sentence = "他跑了3000米，花了15分钟。"
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        g2pw.phonemize(sentence, "zh")
    assert [record.getMessage() for record in caplog.records] == [
        f"g2pW gives no symbol for '3000', '15' in {sentence!r}; numbers belong to the normalisation stage"]
    g2pw.strict = True
    try:
        with pytest.raises(UnreadTextError) as error:
            g2pw.phonemize(sentence, "zh")
    finally:
        g2pw.strict = False
    assert error.value.unread == ("3000", "15")


def test_a_capital_dotted_i_before_a_polyphone_reads_the_polyphone(g2pw, caplog):
    # str.lower() writes İ as two code points. The reference reads "i行长来了。" as
    # i x ing 2 zh ang 3 l ai 2 l e 5 。, and İ is not a symbol.
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize("İ行长来了。", "zh") == [
            ["x", "ing", "2", "zh", "ang", "3", "l", "ai", "2", "l", "e", "5", "。"]]
    assert [record.getMessage() for record in caplog.records] == [
        "g2pW gives no symbol for 'İ' in 'İ行长来了。'"]


@pytest.mark.parametrize("sentence, unread", [
    ("İstanbul的银行。", ("İstanbul",)),
    ("A4纸很好。", ("A4",)),
    ("ПРИВЕТ你好。", ("ПРИВЕТ",)),
])
def test_a_letter_with_no_symbol_raises_in_strict_mode(g2pw, sentence, unread):
    g2pw.strict = True
    try:
        with pytest.raises(UnreadTextError) as error:
            g2pw.phonemize(sentence, "zh")
    finally:
        g2pw.strict = False
    assert error.value.unread == unread


@pytest.mark.parametrize("sentence", ["ibm公司。", "IBM公司。", "iBm公司。"])
def test_a_latin_word_of_any_case_is_unread(g2pw, caplog, sentence):
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize(sentence, "zh") == [["g", "ong", "1", "s", "i", "1", "。"]]
    assert [record.getMessage() for record in caplog.records] == [
        f"g2pW gives no symbol for {sentence[:3]!r} in {sentence!r}"]
    g2pw.strict = True
    try:
        with pytest.raises(UnreadTextError) as error:
            g2pw.phonemize(sentence, "zh")
    finally:
        g2pw.strict = False
    assert error.value.unread == (sentence[:3],)


def test_the_symbol_of_no_initial_in_the_text_is_unread(g2pw, caplog):
    """``Ø`` marks a syllable with no initial in the output, but in the text it is a letter with no reading."""
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize("Ø公司。", "zh") == [["g", "ong", "1", "s", "i", "1", "。"]]
    assert [record.getMessage() for record in caplog.records] == ["g2pW gives no symbol for 'Ø' in 'Ø公司。'"]


@pytest.mark.parametrize("sentence, runs", [
    ("ABC，3个。", "'ABC', '3'"),
    ("Ⅻ月。", "'Ⅻ'"),
    ("½个。", "'½'"),
])
def test_a_run_with_a_number_adds_the_note_on_normalisation(g2pw, caplog, sentence, runs):
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        g2pw.phonemize(sentence, "zh")
    assert [record.getMessage() for record in caplog.records] == [
        f"g2pW gives no symbol for {runs} in {sentence!r}; numbers belong to the normalisation stage"]


def test_a_combining_mark_is_dropped_without_a_warning(g2pw, caplog):
    sentence = "你好\u0301。"
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        assert g2pw.phonemize(sentence, "zh") == [["n", "i", "3", "h", "ao", "3", "。"]]
    assert caplog.records == []
    g2pw.strict = True
    try:
        assert g2pw.phonemize(sentence, "zh") == [["n", "i", "3", "h", "ao", "3", "。"]]
    finally:
        g2pw.strict = False


def test_punctuation_with_no_symbol_is_dropped_without_a_warning(g2pw, caplog):
    with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.g2pw"):
        g2pw.phonemize("《红楼梦》很好。", "zh")
    assert caplog.records == []


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
    identity = g2pw.identity("zh-CN")
    assert identity == PhonemizerIdentity("g2pw", "scriptconv", VERSION_STR, "zh", revision=identity.revision)
    assert identity.revision.startswith("sc2:")


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


def _hub(monkeypatch, files, offline, fail=None):
    """Serve each Hub file from *files*, by its name; record the force_download flags."""
    import huggingface_hub
    real = huggingface_hub.hf_hub_download
    calls = []

    def download(repo_id, filename, repo_type=None, revision=None, force_download=False, **kwargs):
        calls.append((filename.rsplit("/", 1)[-1], force_download))
        if fail:
            raise fail
        name = filename.rsplit("/", 1)[-1]
        if name in files:
            return str(files[name])
        return real(repo_id, filename, repo_type=repo_type, revision=revision)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_OFFLINE", offline)
    return calls


def _truncated_archive() -> bytes:
    """The first part of a gzipped tar archive."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        member = tarfile.TarInfo("g2pw.onnx")
        member.size = 4096
        archive.addfile(member, io.BytesIO(bytes(4096)))
    return gzip.compress(data.getvalue())[:200]


@pytest.mark.parametrize("name, content", [("g2pw.tar.gz", b"not an archive"),
                                           ("g2pw.tar.gz", _truncated_archive()),
                                           ("tokenizer.json", b""),
                                           ("tokenizer.json", b"{not json")],
                         ids=["bad archive", "truncated archive", "empty tokenizer", "invalid tokenizer"])
def test_a_cached_file_that_fails_its_check_offline_raises_model_unavailable(
        tmp_path, monkeypatch, name, content):
    (tmp_path / name).write_bytes(content)
    calls = _hub(monkeypatch, {name: tmp_path / name}, offline=True)
    with pytest.raises(ModelUnavailableError, match=name):
        G2PWPhonemizer()
    assert (name, True) not in calls


def test_a_cached_file_that_fails_its_check_is_downloaded_again_once(tmp_path, monkeypatch):
    (tmp_path / "g2pw.tar.gz").write_bytes(b"not an archive")
    calls = _hub(monkeypatch, {"g2pw.tar.gz": tmp_path / "g2pw.tar.gz"}, offline=False)
    with pytest.raises(ModelUnavailableError, match="g2pw.tar.gz"):
        G2PWPhonemizer()
    assert calls == [("g2pw.tar.gz", False), ("g2pw.tar.gz", True)]


def test_a_dropped_download_raises_model_unavailable(monkeypatch):
    _hub(monkeypatch, {}, offline=False, fail=OSError("Consistency check failed: file should be "
                                                     "of size 112991734 but has size 1048576"))
    with pytest.raises(ModelUnavailableError, match="Consistency check failed"):
        G2PWPhonemizer()
