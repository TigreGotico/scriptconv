"""A language with no diacritizer gets a refusal that names the real reason.

Only European Portuguese keeps a message about native spelling. A tag with no
diacritizer has no overlay marks to remove, and ``diacritize`` leaves its text
unchanged.
"""
import pytest

from scriptconv.diacritics import _supports_strip, diacritize, strip_diacritics

NO_FAMILY = ("en", "eng-GB", "es", "und", "pt-BR")
NATIVE = ("pt", "pt-PT", "por")


@pytest.mark.parametrize("lang", NO_FAMILY)
def test_no_diacritizer_reports_no_overlay_marks(lang):
    with pytest.raises(ValueError) as exc:
        strip_diacritics("café", lang)
    message = str(exc.value)
    assert "no overlay diacritics" in message
    assert "native orthography" not in message
    assert _supports_strip(lang) is False
    assert diacritize("hello", lang) == "hello"


@pytest.mark.parametrize("lang", NATIVE)
def test_native_orthography_keeps_its_own_message(lang):
    with pytest.raises(ValueError, match="native orthography"):
        strip_diacritics("café", lang)
    assert _supports_strip(lang) is False
