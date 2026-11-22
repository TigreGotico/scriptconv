"""The Hebrew, Japanese and Thai backends of scriptconv-copyleft resolve through the registry.

Each expected value comes from the reference implementation, piper-tts 1.8.0
(OHF-Voice/piper1-gpl v1.8.0), not from this package:
``HebrewPhonemizer``, ``JapanesePhonemizer`` and ``ThaiPhonemizer``
``.phonemize(text)``. The Hebrew input already carries niqqud, so the
reference reads it without its diacritizer, as ``hebrew_ipa`` does. The
sentences are rows of the scriptconv-copyleft parity samples (FLORES-200
devtest, CC-BY-SA-4.0, and the phonemizer tests of piper1-gpl).
"""
import pytest

from scriptconv.phonemizers import Phonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, get_phonemizer

ROWS = [
    (Phonemizer.HEBREW_IPA, "he", "הַכּוֹחַ לְשַׁנּוֹת מַתְחִיל בָּרֶגַע שֶׁבּוֹ אַתָּה מַאֲמִין שֶׁזֶּה אֶפְשָׁרִי!",
     ["hakoχˈa leʃanˈot mˈatχil baʁegˈa ʃebˈo atˈa maamˈin ʃezˈe efʃaʁˈi"]),
    (Phonemizer.OPENJTALK_PROSODY, "ja", "今日はいい天気ですね。",
     ["kʲo↓owa#i↑i#te↓ɴkidesɯne."]),
    (Phonemizer.TLTK, "th", "สวัสดีครับ วันนี้อากาศดีมาก",
     ["sa2wat2diː1kʰrap4 wan1niː4ʔaː1kaːt2diː1maːk3"]),
]


@pytest.mark.parametrize("member, module, cls", [
    (Phonemizer.HEBREW_IPA, "scriptconv_copyleft.phonemizers.he", "HebrewIPAPhonemizer"),
    (Phonemizer.OPENJTALK_PROSODY, "scriptconv_copyleft.phonemizers.ja_prosody", "OpenJTalkProsodyPhonemizer"),
    (Phonemizer.TLTK, "scriptconv_copyleft.phonemizers.th", "TLTKPhonemizer"),
])
def test_the_member_names_the_copyleft_class(member, module, cls):
    assert PHONEMIZER_REGISTRY[member][:2] == (module, cls)


@pytest.mark.parametrize("member, lang, text, expected", ROWS)
def test_gives_the_symbols_of_the_reference(member, lang, text, expected):
    # one list of symbols per sentence, each symbol one code point
    assert get_phonemizer(member).phonemize(text, lang) == [list(s) for s in expected]
