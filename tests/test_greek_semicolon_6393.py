"""A Greek question mark spelled with an ISO 639-3 tag still ends a sentence.

The question mark of Greek is `;`. The tag `ell` and the bibliographic `gre`
name the same language as `el`, so the rule must hold for them too. A colon is
still a space in every spelling of the tag.
"""
import pytest

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import Alphabet, BasePhonemizer

GREEK = ("el", "el-GR", "ell", "ell-CY", "gre")
OTHER = ("en", "eng", "bg", "bul")


class Echo(BasePhonemizer):
    """Phonemes are the characters of the text, as in the chunk tests."""

    def __init__(self):
        super().__init__(Alphabet.IPA)

    def phonemize_string(self, text, lang):
        return text


@pytest.mark.parametrize("lang", GREEK)
def test_a_greek_semicolon_ends_the_sentence(lang):
    expected = [list("τι κάνεις"), list("καλά")]
    assert Echo().phonemize("τι κάνεις; καλά.", lang) == expected
    assert TextFrontend(FrontendConfig(lang), Echo()).phonemize("τι κάνεις; καλά.") == expected


@pytest.mark.parametrize("lang", GREEK)
def test_a_greek_colon_is_still_a_space(lang):
    assert Echo().phonemize("ένα: δύο.", lang) == [list("ένα δύο")]


@pytest.mark.parametrize("lang", OTHER)
def test_another_language_semicolon_is_a_space(lang):
    assert Echo().phonemize("a; b.", lang) == [list("a b")]
