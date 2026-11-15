"""The dizione backend: American English text to IPA and to dizione's tokens.

The expected IPA comes from CMUdict (``cmudict.dict`` of
github.com/cmusphinx/cmudict at commit 74790861, the commit dizione's data was
built from) and the ARPAbet table of dizione's ``convert.py``: ``CONSONANTS``
and ``FULL_VOWELS``. Stress 1 writes ``ˈ`` and stress 2 writes ``ˌ`` directly
before the vowel.
"""
import hashlib

import pytest

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import (
    Alphabet,
    MissingLanguageError,
    Phonemizer,
    UnsupportedLanguageError,
    get_phonemizer,
)
from scriptconv.phonemizers._thirdparty import dizione
from scriptconv.phonemizers._thirdparty.dizione.symbols import SYMBOL_TO_ID, Phonemized
from scriptconv.phonemizers.dizione import DATA_DIR, DizionePhonemizer


@pytest.fixture(scope="module")
def data_dir():
    return DATA_DIR


@pytest.fixture(scope="module")
def phonemizer(data_dir):
    return DizionePhonemizer(data_dir=data_dir)


class TestIPA:
    @pytest.mark.parametrize("text, cmudict, expected", [
        ("cat", "cat K AE1 T", "kˈæt"),
        ("thought", "thought TH AO1 T", "θˈɔːt"),
        ("judge", "judge JH AH1 JH", "dʒˈʌdʒ"),
        ("cheese", "cheese CH IY1 Z", "tʃˈiːz"),
        ("ship", "ship SH IH1 P", "ʃˈɪp"),
        ("bath", "bath B AE1 TH", "bˈæθ"),
        ("mouth", "mouth M AW1 TH", "mˈaʊθ"),
        ("boy", "boy B OY1", "bˈɔɪ"),
        ("nine", "nine N AY1 N", "nˈaɪn"),
        ("yellow", "yellow Y EH1 L OW0", "jˈɛloʊ"),
        ("singing", "singing S IH1 NG IH0 NG", "sˈɪŋɪŋ"),
        ("12", "twelve T W EH1 L V", "twˈɛlv"),
        ("8", "eight EY1 T", "ˈeɪt"),
    ])
    def test_a_word_reads_as_cmudict_writes_it(self, phonemizer, text, cmudict, expected):
        assert phonemizer.phonemize_string(text, "en-US") == expected

    @pytest.mark.parametrize("text, index, cmudict, expected", [
        ("I like to read.", 3, "read(2) R IY1 D", "ɹˈiːd"),
        ("You read it yesterday.", 1, "read R EH1 D", "ɹˈɛd"),
    ])
    def test_the_words_around_a_homograph_pick_its_reading(self, phonemizer, text, index,
                                                           cmudict, expected):
        assert phonemizer.phonemize_string(text, "en-US").split(" ")[index] == expected

    def test_a_word_break_is_one_space_and_punctuation_is_not_written(self, phonemizer):
        assert phonemizer.phonemize_string("Cat, ship!", "en-US") == "kˈæt ʃˈɪp"

    def test_each_sentence_is_one_list(self, phonemizer):
        assert phonemizer.phonemize("Cat. Ship?", "en-US") == [list("kˈæt"), list("ʃˈɪp")]

    def test_an_abbreviation_ends_no_sentence(self, phonemizer):
        assert phonemizer.phonemize("Dr. Ship.", "en-US") == \
            [list(phonemizer.phonemize_string("Doctor Ship.", "en-US"))]

    def test_the_flat_list_is_the_string(self, phonemizer):
        text = "Cat. Ship?"
        assert phonemizer.phonemize_to_list(text, "en-US") == \
            list(phonemizer.phonemize_string(text, "en-US")) == list("kˈæt ʃˈɪp")


class TestTokens:
    def test_tokens_are_dizione_symbols_ids_and_stress(self, phonemizer):
        tokens = phonemizer.tokens("Cat, ship.")
        assert isinstance(tokens, Phonemized)
        assert tokens.symbols == ("<bos>", "k", "æ", "t", ",", "ʃ", "ɪ", "p", ".", "<eos>")
        assert tokens.ids == tuple(SYMBOL_TO_ID[s] for s in tokens.symbols)
        assert tokens.stress == (0, 0, 1, 0, 0, 0, 1, 0, 0, 0)

    @pytest.mark.parametrize("text", ["", "   ", "!!!"])
    def test_text_with_nothing_to_read_is_refused(self, phonemizer, text):
        with pytest.raises(ValueError):
            phonemizer.tokens(text)


class TestNormalization:
    def test_the_backend_owns_the_normalize_stage(self):
        assert DizionePhonemizer.owned_stages == frozenset({"normalize"})

    @pytest.mark.parametrize("written, spoken", [
        ("It costs $12.", "It costs twelve dollars."),
        ("Dr. Patel paid.", "Doctor Patel paid."),
    ])
    def test_the_frontend_gives_the_text_with_its_punctuation(self, phonemizer, written, spoken):
        frontend = TextFrontend(FrontendConfig(lang="en-US", normalizer=lambda text, lang: "x"),
                                backend=phonemizer)
        assert frontend.phonemize(written) == phonemizer.phonemize(spoken, "en-US")


class TestLanguages:
    @pytest.mark.parametrize("lang, resolved", [
        ("en-US", "en-US"), ("en_us", "en-US"), ("en-Latn-US", "en-US"),
        ("en-US-x-nyc", "en-US-x-nyc"),
    ])
    def test_american_english_is_read(self, lang, resolved):
        assert DizionePhonemizer.get_lang(lang) == resolved

    @pytest.mark.parametrize("lang", ["en", "en-GB", "en-AU", "fr-US", "pt-PT"])
    def test_every_other_tag_is_refused_and_names_en_us(self, phonemizer, lang):
        with pytest.raises(UnsupportedLanguageError, match="en-US"):
            phonemizer.phonemize_string("cat", lang)

    @pytest.mark.parametrize("lang", [None, "", "und"])
    def test_a_missing_language_is_its_own_error(self, lang):
        with pytest.raises(MissingLanguageError):
            DizionePhonemizer.get_lang(lang)


class TestEmptyText:
    @pytest.mark.parametrize("text", ["", "!!!"])
    def test_text_with_nothing_to_read_gives_no_sentence(self, phonemizer, text):
        assert phonemizer.phonemize(text, "en-US") == []
        assert phonemizer.phonemize_string(text, "en-US") == ""
        assert phonemizer.phonemize_to_list(text, "en-US") == []


class TestOverrides:
    def test_overrides_belong_to_their_instance(self, data_dir):
        default = DizionePhonemizer(data_dir=data_dir)
        # "cat" written as "kit": K IH1 T
        taught = DizionePhonemizer(data_dir=data_dir, overrides={"cat": "K IH1 T"})
        assert taught.phonemize_string("cat", "en-US") == "kˈɪt"
        assert default.phonemize_string("cat", "en-US") == "kˈæt"
        for word in ("ship", "thought", "yellow", "12"):
            assert taught.phonemize_string(word, "en-US") == default.phonemize_string(word, "en-US")


class TestIdentity:
    def test_the_revision_is_dizione_s_build_fingerprint(self, phonemizer, data_dir):
        identity = phonemizer.identity("en-us")
        assert (identity.backend, identity.lang) == ("dizione", "en-US")
        assert identity.revision == dizione.identity(data_dir)["fingerprint"]

    def test_the_token_convention_is_version_4(self):
        assert dizione.VERSION == 4


class TestConstruction:
    def test_the_registry_builds_it_with_ipa(self, data_dir):
        built = get_phonemizer(Phonemizer.DIZIONE, data_dir=data_dir)
        assert isinstance(built, DizionePhonemizer)
        assert built.alphabet == Alphabet.IPA

    def test_another_alphabet_is_refused(self, data_dir):
        with pytest.raises(ValueError, match="ipa"):
            DizionePhonemizer(Alphabet.ARPA, data_dir=data_dir)

    def test_no_data_dir_reads_the_data_in_the_package(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DIZIONE_DATA", str(tmp_path))
        phonemizer = DizionePhonemizer()
        assert phonemizer.data_dir == DATA_DIR
        assert phonemizer.phonemize_string("cat", "en-US") == "kˈæt"


# sha256 of the files of phonemizer/ of n4ze3m/tiny-voca at revision
# e5f9b11651a4db525fb207a56a91e4df2d1dd387: the LFS sha256 that the Hub
# records for g2p.npz, and the files themselves for the rest.
BUILT = {
    "LICENSE.cmudict": "bd4ce8e44170a5f9f481310ca85c51de3c4f851a65e679b40e603b143bd3542a",
    "LICENSE.homograph-data": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "align.json": "864763dbd558a864950266b2c30627f1cad203e75062ee842ee63c653e823b75",
    "g2p.json": "c518fd839ea0109c0b2b4f778c17506bf0d7653557b8b8c97a4c8dd9883d4432",
    "g2p.npz": "eb3fd519ff00e72d850928d2fccb968adc36134bca2f3bda09de7e794c2ed01b",
    "homographs.json": "9c3a96fcdf79fa27d1b3686dc6a507c37e4f754966928608ee9ddb617ba39192",
    "lexicon.json": "4d67c1f94b86405a5b8766fb13b8cd92a1371204767dd709582a337e8e0ab334",
    "lexicon.tsv": "3fc930345c6b3cabc533981c4b212fa309eec83913fcdbd42919338270d64b06",
    "sources.json": "f4c54924d30a5bc0bc1e3d7b058adb924484b3fab8541bc8d8bcecfb028fdbad",
}


def test_the_package_holds_the_pinned_data():
    found = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in DATA_DIR.iterdir() if path.is_file()}
    assert found == BUILT
