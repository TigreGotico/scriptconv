"""misaki codes expand to IPA before another notation reads them.

Each row quotes hexgrad/misaki EN_PHONES.md: the word, its misaki codes and
the IPA the page gives. The ARPABET phone is the CMU Pronouncing Dictionary
phone for that IPA value (EY eɪ, AY aɪ, AW aʊ, OY ɔɪ, OW oʊ, JH dʒ, CH tʃ, AH ʌ).
"""
import pytest

from scriptconv.notation import NOTATION_INFO, Notation, can_convert, convert, misaki_to_ipa
from scriptconv.phonemizers.enums import Alphabet

ROWS = [
    # "`A`: [...] like `hey => hˈA`. Expands to `eɪ` in IPA."
    ("hˈA", "hˈeɪ", "HH EY"),
    # "`I`: [...] like `high => hˈI`. Expands to `aɪ` in IPA."
    ("hˈI", "hˈaɪ", "HH AY"),
    # "`W`: [...] like `how => hˌW`. Expands to `aʊ` in IPA."
    ("hˌW", "hˌaʊ", "HH AW"),
    # "`Y`: [...] like `soy => sˈY`. Expands to `ɔɪ` in IPA."
    ("sˈY", "sˈɔɪ", "S OY"),
    # "`O`: [...] American "oh" vowel sound. Expands to `oʊ` in IPA."
    ("ɡˈO", "ɡˈoʊ", "G OW"),
    # "`ʤ`: [...] merges `dʒ`, like `jump => ʤˈʌmp`"
    ("ʤˈʌmp", "dʒˈʌmp", "JH AH M P"),
    # "`ʧ`: [...] merges `tʃ`, like [...] `lunch => lˈʌnʧ`."
    ("lˈʌnʧ", "lˈʌntʃ", "L AH N CH"),
]


@pytest.mark.parametrize("misaki, ipa, arpa", ROWS)
def test_a_misaki_code_expands_to_the_ipa_of_the_page(misaki, ipa, arpa):
    assert misaki_to_ipa(misaki) == ipa
    assert convert(misaki, Notation.MISAKI, Notation.IPA) == ipa


@pytest.mark.parametrize("misaki, ipa, arpa", ROWS)
def test_misaki_reaches_arpabet_through_ipa(misaki, ipa, arpa):
    assert convert(misaki, "misaki", "arpa") == arpa


def test_the_british_oh_expands_to_its_ipa():
    # "`Q`: [...] British "oh" vowel sound. Expands to `əʊ` in IPA."
    assert misaki_to_ipa("ɡˈQ") == "ɡˈəʊ"


def test_the_small_schwa_reads_as_schwa():
    # "`ᵊ`: Small schwa, muted version of `ə`, like `pixel => pˈɪksᵊl`."
    assert misaki_to_ipa("pˈɪksᵊl") == "pˈɪksəl"


def test_a_symbol_the_page_gives_no_ipa_for_stays_as_written():
    # "`ᵻ`: A sound somewhere in between `ə` and `ɪ`, [...] `boxes => bˈɑksᵻz`."
    assert misaki_to_ipa("bˈɑksᵻz") == "bˈɑksᵻz"


def test_plain_ipa_stays_as_it_is():
    text = "ðə wˈɪnd wʌz kˈɛld, ɹˈid ɪnsˈæd."
    assert misaki_to_ipa(text) == text


def test_misaki_is_an_alphabet_and_a_one_way_notation():
    assert Alphabet.MISAKI.value == Notation.MISAKI.value == "misaki"
    assert can_convert("misaki", "x-sampa")
    assert not can_convert("ipa", "misaki")
    assert not NOTATION_INFO[Notation.MISAKI].lossless_to_ipa
