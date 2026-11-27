"""The dizione backend: American English text to IPA and to dizione's tokens.

The expected IPA comes from CMUdict (``cmudict.dict`` of
github.com/cmusphinx/cmudict at commit 74790861, the commit dizione's data was
built from) and the ARPAbet table of dizione's ``convert.py``: ``CONSONANTS``
and ``FULL_VOWELS``, and its rule that an unstressed ``ER`` is ``ɚ``. Stress 1
writes ``ˈ`` and stress 2 writes ``ˌ`` directly before the vowel.
"""
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

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
from scriptconv.phonemizers.dizione import DATA_DIR, DizionePhonemizer, _token_clauses
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY


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
        ("yesterday", "yesterday Y EH1 S T ER0 D EY2", "jˈɛstɚdˌeɪ"),
        ("afternoon", "afternoon AE2 F T ER0 N UW1 N", "ˌæftɚnˈuːn"),
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

    def test_a_comma_ends_no_sentence(self, phonemizer):
        assert phonemizer.phonemize("Cat, ship.", "en-US") == [list("kˈæt ʃˈɪp")]

    def test_the_sentence_marks_are_dizione_s(self, phonemizer):
        assert phonemizer.phonemize("Cat\u2026 ship.", "en-US") == [list("kˈæt ʃˈɪp")]

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

    # Recorded from upstream dizione.phonemize at 8cd889e over the same data.
    @pytest.mark.parametrize("text, symbols, stress", [
        # capitals: "AI" is read as two letters
        ("It is AI.", ("<bos>", "ɪ", "ɾ", "<sp>", "ɪ", "z", "<sp>", "eɪ", "aɪ", ".", "<eos>"),
         (0, 0, 0, 0, 0, 0, 0, 2, 1, 0, 0)),
        # "i am" is one unit of data/phrases.txt, with no word break
        ("I am here.", ("<bos>", "aɪ", "ɐ", "m", "<sp>", "h", "ɪɹ", ".", "<eos>"),
         (0, 0, 0, 0, 0, 0, 1, 0, 0)),
    ])
    def test_tokens_equal_upstream(self, phonemizer, text, symbols, stress):
        tokens = phonemizer.tokens(text)
        assert (tokens.symbols, tokens.stress) == (symbols, stress)

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

    def test_a_normalizer_set_on_the_backend_runs(self, data_dir):
        backend = get_phonemizer(Phonemizer.DIZIONE, data_dir=data_dir,
                                 normalizer=lambda text, lang: text.replace("dog", "cat"))
        assert backend.phonemize("dog", "en-US") == [list("kˈæt")]


def check_join_rule(whole, parts):
    """The join rule for segments that each have their own ``<bos>`` and ``<eos>``.

    1. Join the segments.
    2. Drop each inner ``<eos>`` ``<bos>`` pair together with its ids and
       stress values. The first ``<bos>`` and the last ``<eos>`` stay.
    3. The result equals *whole* (``tokens(text)``) in symbols, ids and stress.
    4. At every cut, the word gap (``<sp>``) or punctuation symbol that *whole*
       has there appears exactly once: the symbols on the two sides of the cut
       are the symbols on the two sides of the same place in *whole*.
    """
    assert all(part.symbols[0] == "<bos>" and part.symbols[-1] == "<eos>" for part in parts)
    assert all(len(part.symbols) == len(part.ids) == len(part.stress) for part in parts)
    symbols = [s for part in parts for s in part.symbols]
    ids = [i for part in parts for i in part.ids]
    stress = [v for part in parts for v in part.stress]
    inner = {index for index in range(1, len(symbols) - 1)
             if (symbols[index], symbols[index + 1]) == ("<eos>", "<bos>")}
    inner |= {index + 1 for index in inner}
    keep = [index for index in range(len(symbols)) if index not in inner]
    assert [symbols[i] for i in keep] == list(whole.symbols)
    assert [ids[i] for i in keep] == list(whole.ids)
    assert [stress[i] for i in keep] == list(whole.stress)
    cut = 0
    for left, right in zip(parts, parts[1:]):
        cut += len(left.symbols) - 2
        assert (left.symbols[-2], right.symbols[1]) == (whole.symbols[cut], whole.symbols[cut + 1])


class TestWholeText:
    """dizione reads the whole text once and cuts its own output at its own marks."""

    TEXTS = [
        "Hello, world. Mrs. Jones met Mr. Smith at St. Paul's!",
        "Really?! \"Stop.\" Then he left...",
        "Jan. 1, 2000. See p. 12 and No. 5.",
        "Hi?, there; ok: fine. .",
        "One sentence with no mark",
        "Prof. Close the door. Prof. X",
    ]

    def test_it_reads_whole_text(self, phonemizer):
        assert DizionePhonemizer.reads_whole_text is True
        assert DizionePhonemizer.owned_stages == frozenset({"normalize"})

    @pytest.mark.parametrize("text", TEXTS)
    def test_the_sentences_follow_the_join_rule(self, phonemizer, text):
        sentences = phonemizer.token_segments(text)
        check_join_rule(phonemizer.tokens(text), sentences)
        assert sum(segment.ends_sentence for segment in phonemizer.phonemize_segments(text, "en-US")) \
            == len(sentences) == len(phonemizer.phonemize(text, "en-US"))

    @pytest.mark.parametrize("text", TEXTS)
    def test_the_clauses_follow_the_join_rule(self, phonemizer, text):
        whole = phonemizer.tokens(text)
        check_join_rule(whole, _token_clauses(whole))

    def test_a_sentence_ends_after_its_run_of_marks(self, phonemizer):
        sentences = phonemizer.token_segments("Really?! Yes.")
        assert [s.symbols[-3:] for s in sentences] == [("?", "!", "<eos>"), ("s", ".", "<eos>")]

    def test_an_abbreviation_ends_no_sentence(self, phonemizer):
        assert len(phonemizer.token_segments("Mrs. Jones met Mr. Smith.")) == 1

    def test_the_segments_carry_the_marks_and_the_stress(self, phonemizer):
        segments = list(phonemizer.phonemize_segments("Hello, world! Hi; there", "en-US"))
        assert [("".join(s.phonemes), s.mark, s.ends_sentence) for s in segments] == [
            ("həlˈoʊ", ",", False), ("wˈɜːld", "!", True), ("hˈaɪ", ";", False), ("ðˈɛɹ", None, True)]
        hello = segments[0]
        assert len(hello.streams["stress"]) == len(hello.phonemes)
        # the stress mark and its vowel "oʊ" carry stress 1, every other character 0
        assert hello.streams["stress"] == (0, 0, 0, 1, 1, 1)

    def test_text_with_nothing_to_read_gives_no_segment(self, phonemizer):
        assert list(phonemizer.phonemize_segments("  ", "en-US")) == []
        assert list(phonemizer.phonemize_segments("...", "en-US")) == []

    def test_the_segments_check_the_language(self, phonemizer):
        with pytest.raises(UnsupportedLanguageError):
            next(phonemizer.phonemize_segments("cat", "en-GB"))


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
        with pytest.raises(UnsupportedLanguageError, match="en-US"):
            phonemizer.phonemize("cat", lang)

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
    def test_the_revision_is_the_same_for_two_instances(self, phonemizer, data_dir):
        assert phonemizer.identity("en-US").revision is not None
        assert DizionePhonemizer(data_dir=data_dir).identity("en-US") == phonemizer.identity("en-US")

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


def test_without_numpy_the_import_names_the_extra_that_installs_it():
    code = ("import sys; sys.modules['numpy'] = None\n"
            "from scriptconv.phonemizers.dizione import DizionePhonemizer")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1])
    assert result.returncode != 0
    assert "ImportError: numpy is required for the dizione phonemizer" in result.stderr
    assert "scriptconv[en-phonemizers]" in result.stderr


def test_the_extra_that_the_registry_names_for_dizione_holds_numpy():
    extra = PHONEMIZER_REGISTRY[Phonemizer.DIZIONE][2]
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = pyproject["project"]["optional-dependencies"][extra]
    assert any(requirement.split(">")[0].split("<")[0].split("=")[0].strip() == "numpy" for requirement in requirements)
