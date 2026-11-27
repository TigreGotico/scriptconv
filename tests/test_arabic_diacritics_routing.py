"""Arabic tashkeel follows the language and the script a tag names.

The expected lists below do not come from linguatag. They come from two
published tables:

- ISO 639-3 macrolanguage mappings, the rows with ``M_Id`` ``ara``
  (https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3-macrolanguages.tab).
  ``ajp`` and ``bbz`` have status R (retired) and are kept, because a tag with
  a retired code still names an Arabic variety.
- CLDR 49 ``likelySubtags.json``. It gives Arabic script for every member
  except ``acy`` (``acy-Latn-CY``, Cypriot Maronite Arabic) and ``pga``
  (``pga-Latn-SS``, Juba Arabic). Tashkeel marks Arabic script only, so these
  two route to tashkeel only with an explicit ``Arab`` script subtag.
"""
import sys
import types

import pytest

from scriptconv import diacritics
from scriptconv.diacritics import (
    _ARABIC_MARKS,
    _diacritizer_family,
    _overlay_marks,
    diacritize,
    strip_diacritics,
)
from scriptconv.graph import DEFAULT_GRAPH

ISO_639_3_ARA_MEMBERS = (
    "aao", "abh", "abv", "acm", "acq", "acw", "acx", "acy", "adf", "aeb",
    "aec", "afb", "ajp", "apc", "apd", "arb", "arq", "ars", "ary", "arz",
    "auz", "avl", "ayh", "ayl", "ayn", "ayp", "bbz", "pga", "shu", "ssh",
)
CLDR_LATIN_SCRIPT_MEMBERS = ("acy", "pga")

ARABIC_SCRIPT_TAGS = tuple(
    t for t in ISO_639_3_ARA_MEMBERS if t not in CLDR_LATIN_SCRIPT_MEMBERS
) + (
    "ar", "ara", "ar-EG", "ar_SA", "AR-eg", "ar-Arab", "ar-Arab-EG", "ar-001",
    "arz-EG", "arz-Arab", "apc-Arab-SY", "ars-SA", "ary-x-casa",
    "acy-Arab", "pga-Arab",
    # Hassaniyya: its own ISO 639-3 code, Arabic script in CLDR (mey-Arab-DZ).
    "mey",
)

NOT_ARABIC_SCRIPT_TAGS = CLDR_LATIN_SCRIPT_MEMBERS + (
    "ar-Latn", "ar-Latn-x-buckwalt", "arz-Latn",
    "mey-SN",                   # CLDR: mey-Latn-SN
    "arg", "arn", "arl",        # Aragonese, Mapudungun, Arabela
    "mt", "mt-MT",              # Maltese: Semitic, Latin script, not Arabic
    "fa", "ur", "und-Arab",     # Arabic script, other languages
    "en", "es", "und",
)


def test_expected_lists_do_not_overlap():
    assert not set(ARABIC_SCRIPT_TAGS) & set(NOT_ARABIC_SCRIPT_TAGS)
    assert len(ISO_639_3_ARA_MEMBERS) == 30


@pytest.mark.parametrize("lang", ARABIC_SCRIPT_TAGS)
def test_arabic_in_arabic_script_routes_to_tashkeel(lang):
    assert _diacritizer_family(lang) == "ar"
    assert _overlay_marks(lang) == _ARABIC_MARKS


@pytest.mark.parametrize("lang", NOT_ARABIC_SCRIPT_TAGS)
def test_other_tags_do_not_route_to_tashkeel(lang):
    assert _diacritizer_family(lang) is None
    with pytest.raises(ValueError):
        strip_diacritics("café", lang)


@pytest.mark.parametrize("lang", ("arz", "apc-Arab-SY", "ars-SA", "mey"))
def test_strip_removes_tashkeel_for_arabic_lects(lang):
    assert strip_diacritics("مُحَمَّد", lang) == "محمد"


def test_two_letter_tags_other_than_ar_need_no_linguatag(monkeypatch):
    monkeypatch.setitem(sys.modules, "linguatag", None)
    assert diacritize("hello", "en") == "hello"
    with pytest.raises(ValueError):
        strip_diacritics("café", "en")
    for lang in ("ar", "arz"):
        with pytest.raises(ImportError, match=r"scriptconv\[phonemizers\]"):
            strip_diacritics("مُحَمَّد", lang)


class _FakeTashkeel:
    """A text2tashkeel stand-in that records its constructor and calls."""

    def __init__(self):
        self.built = []
        self.calls = []
        fake = self

        class Diacritizer:
            def __init__(self, model, waqf=False):
                fake.built.append((model, waqf))
                self.waqf = waqf

            def diacritize(self, text):
                fake.calls.append((text, self.waqf))
                return f"{text}|waqf={self.waqf}"

        self.module = types.ModuleType("text2tashkeel")
        self.module.Diacritizer = Diacritizer


@pytest.fixture
def fake_tashkeel(monkeypatch):
    fake = _FakeTashkeel()
    monkeypatch.setitem(sys.modules, "text2tashkeel", fake.module)
    monkeypatch.setattr(diacritics, "_TASHKEEL_CACHE", {})
    return fake


@pytest.mark.parametrize("lang", ("arz", "apc", "ary", "acm", "ajp", "aeb",
                                  "afb", "ars", "mey", "ar-EG"))
def test_arabic_lects_reach_text2tashkeel(fake_tashkeel, lang):
    assert diacritize("نص", lang) == "نص|waqf=False"
    assert fake_tashkeel.calls == [("نص", False)]


def test_waqf_reaches_text2tashkeel(fake_tashkeel):
    assert diacritize("نص", "ar") == "نص|waqf=False"
    assert diacritize("نص", "ar", waqf=False) == "نص|waqf=False"
    assert diacritize("نص", "arz", waqf=True) == "نص|waqf=True"
    assert diacritize("نص", "ar", diacritizer_model="rawi", waqf=True) == "نص|waqf=True"
    assert fake_tashkeel.built == [("rawi-ensemble", False),
                                   ("rawi-ensemble", True),
                                   ("rawi", True)]


def test_waqf_reaches_text2tashkeel_through_the_graph(fake_tashkeel):
    graph = DEFAULT_GRAPH.extend(diacritics.register)
    out = graph.convert("نص", "text", "text-diacritized", lang="apc", waqf=True)
    assert out == "نص|waqf=True"
    assert fake_tashkeel.built == [("rawi-ensemble", True)]


def test_latin_script_arabic_never_reaches_text2tashkeel(fake_tashkeel):
    for lang in ("ar-Latn", "acy", "pga", "arg"):
        assert diacritize("nass", lang, waqf=True) == "nass"
    assert fake_tashkeel.built == []


class TestRealText2tashkeel:
    """The installed text2tashkeel, with the model that ships in its wheel."""

    SENTENCE = "ذهب الولد إلى المدرسة"

    def test_waqf_none_matches_text2tashkeel_default(self):
        import text2tashkeel
        assert diacritize(self.SENTENCE, "ar") == text2tashkeel.diacritize(self.SENTENCE)

    def test_waqf_true_gives_the_pausal_form(self):
        import text2tashkeel
        full = text2tashkeel.diacritize(self.SENTENCE)
        pausal = diacritize(self.SENTENCE, "arz", waqf=True)
        assert pausal == text2tashkeel.pausal(full)
        assert pausal != full
