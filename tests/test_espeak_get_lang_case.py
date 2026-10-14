"""EspeakPhonemizer.get_lang reads a BCP-47 tag whatever its case (T-2783).

``ESPEAK_LANGS`` is all lowercase. The exact-match check used the tag as
written, so ``pt-BR`` missed it and fell to the bare primary subtag ``pt``,
which is European Portuguese: a phoonnx Brazilian voice phonemized as
European. ``fr-BE`` fell to metropolitan ``fr`` the same way.

These tests need no espeak binary: ``get_lang`` is a classmethod over the
static voice list.
"""
import pytest

from scriptconv.phonemizers.mul import EspeakPhonemizer


@pytest.mark.parametrize("tag, voice", [
    ("pt-BR", "pt-br"),
    ("PT-BR", "pt-br"),
    ("pt_BR", "pt-br"),
    ("fr-BE", "fr-be"),
    ("fr-CH", "fr-ch"),
    ("ES-419", "es-419"),
    ("vi-VN-x-central", "vi-vn-x-central"),
    ("vi-VN-x-south", "vi-vn-x-south"),
])
def test_a_region_tag_keeps_its_region_whatever_its_case(tag, voice):
    assert EspeakPhonemizer.get_lang(tag) == voice


@pytest.mark.parametrize("tag, voice", [
    ("pt-br", "pt-br"),
    ("fr-be", "fr-be"),
    ("en-us", "en-us"),
    ("pt", "pt"),
    ("fr", "fr"),
])
def test_lowercase_tags_are_unchanged(tag, voice):
    assert EspeakPhonemizer.get_lang(tag) == voice


def test_the_bare_language_is_not_silently_substituted_for_a_region():
    # the defect: pt-BR must never resolve to European pt while pt-br exists
    assert EspeakPhonemizer.get_lang("pt-BR") != "pt"
    assert EspeakPhonemizer.get_lang("fr-BE") != "fr"


@pytest.mark.parametrize("tag, voice", [
    ("EN-GB", "en-gb-x-rp"),
    ("zh-CN", "cmn"),
    ("ZH-HK", "yue"),
])
def test_the_existing_aliases_still_apply_in_any_case(tag, voice):
    assert EspeakPhonemizer.get_lang(tag) == voice


def test_an_unknown_tag_still_raises():
    with pytest.raises(ValueError):
        EspeakPhonemizer.get_lang("xx")
