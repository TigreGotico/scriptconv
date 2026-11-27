"""Language tags reach the phonemizer backends in any BCP 47 spelling; linguatag decides what they mean."""
import types

import pytest

from scriptconv.frontend import TextFrontend
from scriptconv.phonemizers.mul import EpitranPhonemizer, GoruutPhonemizer, _is_hk_cantonese
from scriptconv.phonemizers.pt import TugaphonePhonemizer


@pytest.mark.parametrize("tag", [
    "yue", "yue-HK", "yue_MO", "yue-Hant", "YUE_hant_hk", "yue-Hant-MO", "yue-Hans", "zh-HK", "zh_MO", "zh-Hant-HK",
    "zho-HK", "zh-Hani-HK",
])
def test_cantonese_and_chinese_in_hong_kong_or_macau_resolve_to_the_cantonese_resources(tag):
    assert _is_hk_cantonese(tag) is True


@pytest.mark.parametrize("tag", ["zh", "zh-TW", "zh-Hant", "zh-CN", "cmn-HK", "en-HK", "ja", "zh-Hans-HK", "zh_hans_mo",
                                 "yue-Latn", "yue-Arab-HK", "zh-Latn-HK"])
def test_other_chinese_is_not_hong_kong_cantonese(tag):
    assert _is_hk_cantonese(tag) is False


@pytest.mark.parametrize("tag, name", [
    ("en-US", "EnglishAmerican"), ("en_US", "EnglishAmerican"), ("EN_us", "EnglishAmerican"),
    ("en-GB", "EnglishBritish"), ("en_gb", "EnglishBritish"), ("en-UK", "EnglishBritish"),
    ("eng-GB", "EnglishBritish"),
])
def test_goruut_reads_english_by_the_standardized_tag(tag, name):
    assert GoruutPhonemizer.get_lang(tag) == name


@pytest.mark.parametrize("tag, name", [("zh-Hans-HK", "ChineseMandarin"), ("zh-Hans-MO", "ChineseMandarin"),
                                       ("zh-Hant-HK", "Cantonese"), ("yue-Hans", "Cantonese")])
def test_goruut_gives_cantonese_only_to_a_han_script_in_hong_kong_or_macau(tag, name):
    assert GoruutPhonemizer.get_lang(tag) == name


@pytest.mark.parametrize("tag", ["yue-Latn", "yue-Arab"])
def test_goruut_has_no_cantonese_for_a_non_han_script(tag):
    with pytest.raises(ValueError):
        GoruutPhonemizer.get_lang(tag)


@pytest.mark.parametrize("tag", ["ja", "jpn", "ja-JP", "ja_Jpan", "JA", "ja-Latn"])
def test_epitran_refuses_japanese_without_a_kana_script(tag):
    with pytest.raises(ValueError, match="kana"):
        EpitranPhonemizer.get_lang(tag)


@pytest.mark.parametrize("tag", ["ko", "kor", "KO_KR", "ko-Kore"])
def test_epitran_hints_at_hangul_for_a_refused_korean_tag(tag):
    with pytest.raises(ValueError, match="Hangul"):
        EpitranPhonemizer.get_lang(tag)


@pytest.mark.parametrize("tag", ["pt-PT-x-porto", "pt_PT_x_porto", "PT-pt-X-Porto", "por-PT-x-porto"])
def test_tugaphone_lect_passes_through_in_any_spelling(tag):
    assert TugaphonePhonemizer.get_lang(tag) == "pt-PT-x-porto"


@pytest.mark.parametrize("config, tag, same", [
    ("pt-PT", "pt_pt", True), ("pt-PT", "por-PT", True), ("he", "iw", True), ("en-US", "EN_us", True),
    ("pt-PT", "pt-BR", False), ("en-US", "en-GB", False),
])
def test_the_frontend_keeps_the_backend_language_for_the_same_standardized_tag(config, tag, same):
    frontend = types.SimpleNamespace(config=types.SimpleNamespace(lang=config, phonemizer_lang="PL"))
    assert (TextFrontend._backend_lang(frontend, tag) == "PL") is same
