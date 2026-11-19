"""The F5-TTS text backends give the tokens of the upstream text functions.

``data/f5tts_parity.jsonl`` holds the reference tokens, recorded with the
upstream functions run unmodified in their own environment:

    convert_char_to_pinyin([text])[0]   # SWivid/F5-TTS 600e5fd, src/f5_tts/model/utils.py
    list(text_list_formatter([text])[0])   # SWivid/Habibi-TTS 9274498, src/habibi_tts/model/utils.py

SILMA TTS (silma-ai/silma-tts 2816b5a) passes the text string to the model as
it is, which gives the Habibi-TTS tokens.
"""
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer
from scriptconv.phonemizers.base import Segment
from scriptconv.phonemizers.f5tts import F5TTSCharPhonemizer, F5TTSPinyinPhonemizer

ROWS = [json.loads(line) for line in
        (Path(__file__).parent / "data" / "f5tts_parity.jsonl").read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")]


@pytest.fixture(scope="module")
def pinyin():
    return F5TTSPinyinPhonemizer()


@pytest.mark.parametrize("row", ROWS, ids=lambda row: str(row["id"]))
def test_the_pinyin_tokens_equal_f5_tts(pinyin, row):
    assert pinyin.phonemize_to_list(row["text"], "zh") == row["f5_tts"]


@pytest.mark.parametrize("row", ROWS, ids=lambda row: str(row["id"]))
def test_the_char_tokens_equal_habibi_tts(row):
    assert F5TTSCharPhonemizer().phonemize_to_list(row["text"], "ar") == row["habibi_tts"]


def test_the_language_does_not_change_the_tokens(pinyin):
    row = next(r for r in ROWS if r["text"] == "我们用iPhone打电话。")
    for lang in ("zh", "en", "tw", "multi"):
        assert pinyin.phonemize_to_list(row["text"], lang) == row["f5_tts"]


class TestFrontend:
    """The frontend gives each sentence whole to the backend and appends no clause symbol."""

    @pytest.mark.parametrize("keep_punctuation", [False, True])
    @pytest.mark.parametrize("text", ["他说：“好的”；然后走了！", "“Akwaaba,” ɔbaa no kae.",
                                      "هل تحب القهوة؟"])
    def test_a_sentence_keeps_every_mark(self, keep_punctuation, text):
        for backend in (F5TTSPinyinPhonemizer(), F5TTSCharPhonemizer()):
            frontend = TextFrontend(FrontendConfig(lang="zh", keep_punctuation=keep_punctuation), backend=backend)
            assert frontend.phonemize(text) == [backend.text_tokens(text)]

    def test_each_sentence_is_one_chunk_with_the_upstream_tokens_of_that_sentence(self, pinyin):
        expected = {r["text"]: r["f5_tts"] for r in ROWS}
        frontend = TextFrontend(FrontendConfig(lang="en"), backend=pinyin)
        assert frontend.phonemize("Is it far? No, it is close.") == [expected["Is it far?"],
                                                                     expected["No, it is close."]]


def test_the_marks_after_an_inline_block_are_tokens(pinyin):
    expected = {r["text"]: r for r in ROWS}
    assert pinyin.mark_symbols(";”") == Segment(tuple(expected[";”"]["f5_tts"]))
    assert F5TTSCharPhonemizer().mark_symbols(" ؟") == Segment(tuple(expected[" ؟"]["habibi_tts"]))


def test_a_stress_mark_stays_a_token():
    assert F5TTSCharPhonemizer().phonemize_to_list("приве́т", "ru") == list("приве́т")


class TestRegistry:
    def test_the_registry_builds_each_backend(self):
        assert isinstance(get_phonemizer(Phonemizer.F5TTS_CHAR, Alphabet.UNICODE), F5TTSCharPhonemizer)
        assert isinstance(get_phonemizer(Phonemizer.F5TTS_PINYIN, Alphabet.UNICODE), F5TTSPinyinPhonemizer)

    def test_the_identity_names_the_variant(self, pinyin):
        assert pinyin.identity("zh").backend == "f5tts_pinyin"
        assert pinyin.identity("zh").distribution == "pypinyin"
        assert F5TTSCharPhonemizer().identity("ar").backend == "f5tts_char"

    def test_neither_backend_owns_a_stage(self):
        assert F5TTSCharPhonemizer.owned_stages == F5TTSPinyinPhonemizer.owned_stages == frozenset()

    def test_another_alphabet_is_refused(self):
        with pytest.raises(ValueError):
            F5TTSCharPhonemizer(alphabet=Alphabet.IPA)

    @pytest.mark.parametrize("module", ["rjieba", "pypinyin"])
    def test_a_missing_dependency_names_the_extra(self, module):
        with mock.patch.dict(sys.modules, {module: None}):
            with pytest.raises(ImportError, match=r"scriptconv\[zh-phonemizers\]"):
                F5TTSPinyinPhonemizer()


def test_no_backend_offers_the_stress_reader_of_dizione():
    """A phonemizer with a callable ``tokens`` reads as dizione, which gives symbols with a stress value each."""
    for backend in (F5TTSCharPhonemizer(), F5TTSPinyinPhonemizer()):
        assert not callable(getattr(backend, "tokens", None))
