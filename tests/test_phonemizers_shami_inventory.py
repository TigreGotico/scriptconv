"""The two Shami symbol inventories: 88 symbols, and 90 with the pause symbols.

The 90-symbol values come from hams-levantine-tts at commit 80d79d0,
``src/hams_tts/text/phoneme_inventory.py``: ``SYMBOLS = SPECIALS + PUNCT +
SUPRASEGMENTALS + CONSONANTS + VOWELS + [SIL, BRK]`` with ``SIL = "sil"`` and
``BRK = "brk"`` appended after the 88, and ``FOLD_MAP["ᵻ"] = "ə"``. Its
``frontend.py`` reads ``, ; :`` as ``sil`` and ``. ! … —`` as ``brk``.
The lexicon entries used below are ``شو`` -> ``ʃuː`` and ``هلق`` -> ``hallaʔ``.
"""
import pytest

from scriptconv.phonemizers._thirdparty.shami import espeak, frontend
from scriptconv.phonemizers._thirdparty.shami import (
    ID_TO_SYMBOL_90,
    SYMBOL_TO_ID,
    SYMBOL_TO_ID_90,
    VOCAB_SIZE,
    VOCAB_SIZE_90,
    TextFrontend,
    get_inventory,
)
from scriptconv.phonemizers._thirdparty.shami.phoneme_inventory import (
    SYMBOLS,
    SYMBOLS_90,
    fold_to_inventory,
)
from scriptconv.phonemizers.shami import ShamiPhonemizer

NEUTRAL = 3
AR = 1


def test_the_90_inventory_appends_sil_and_brk_after_the_88():
    assert (VOCAB_SIZE, VOCAB_SIZE_90) == (88, 90)
    assert SYMBOLS_90[:88] == SYMBOLS
    assert (SYMBOL_TO_ID_90["sil"], SYMBOL_TO_ID_90["brk"]) == (88, 89)
    assert (ID_TO_SYMBOL_90[88], ID_TO_SYMBOL_90[89]) == ("sil", "brk")
    assert "sil" not in SYMBOL_TO_ID and "brk" not in SYMBOL_TO_ID


@pytest.mark.parametrize("size", [0, 87, 89, 91, None, "90", "88", [90], 88.0, 90.0, True])
def test_an_inventory_other_than_88_or_90_is_refused(size):
    with pytest.raises(ValueError, match="the int 88 or 90"):
        TextFrontend(diacritizer_backend="passthrough", inventory=size)
    with pytest.raises(ValueError, match="the int 88 or 90"):
        ShamiPhonemizer(diacritizer_backend="passthrough", inventory=size)


def test_only_the_90_inventory_folds_the_reduced_vowel_to_schwa():
    assert get_inventory(90).fold("ᵻ") == "ə"
    assert get_inventory(90).tokenize("dᵻl").symbols == ["d", "ə", "l"]
    assert get_inventory(88).fold("ᵻ") == "<unk>"
    assert get_inventory(88).tokenize("dᵻl").symbols == ["d", "<unk>", "l"]
    assert fold_to_inventory("ᵻ") == "<unk>"


def test_the_90_inventory_reads_a_comma_as_sil_and_a_full_stop_as_brk():
    utterance = TextFrontend(diacritizer_backend="passthrough", inventory=90).process("شو، هلق.")
    assert utterance.symbols == [
        "<bos>", "ʃ", "uː", "sil", " ", "h", "a", "l", "l", "a", "ʔ", "brk", "<eos>"]
    assert utterance.phoneme_ids[3] == 88
    assert utterance.phoneme_ids[11] == 89
    assert utterance.language_ids == [0, AR, AR, NEUTRAL, NEUTRAL] + [AR] * 6 + [NEUTRAL, 0]


def test_a_run_of_marks_is_one_pause_and_a_sentence_mark_makes_it_brk():
    symbols = TextFrontend(diacritizer_backend="passthrough", inventory=90).process(
        "شو;: هلق,. بس").symbols
    pauses = [s for s in symbols if s in ("sil", "brk")]
    assert pauses == ["sil", "brk"]


def test_the_88_inventory_has_no_pause_symbols():
    utterance = TextFrontend(diacritizer_backend="passthrough").process("شو، هلق؛ بس! مين…")
    assert not {"sil", "brk"} & set(utterance.symbols)
    assert max(utterance.phoneme_ids) < 88


def test_an_88_and_a_90_front_end_in_one_process_keep_their_own_output():
    text = "شو، هلق. بس"
    fe88 = TextFrontend(diacritizer_backend="passthrough")
    first = fe88.process(text).symbols
    fe90 = TextFrontend(diacritizer_backend="passthrough", inventory=90)
    with_pauses = fe90.process(text).symbols
    assert fe88.process(text).symbols == first
    assert TextFrontend(diacritizer_backend="passthrough", inventory=88).process(text).symbols == first
    assert "sil" not in first and "brk" not in first
    assert with_pauses.count("sil") == 1 and with_pauses.count("brk") == 1
    assert fe90.process(text).symbols == with_pauses


def test_the_phonemizer_passes_the_inventory_to_its_front_end():
    phonemes, lang_ids = ShamiPhonemizer(
        diacritizer_backend="passthrough", inventory=90).phonemize_with_language_ids("شو، هلق.", "ar")
    assert phonemes == [["<bos>", "ʃ", "uː", "sil", " ", "h", "a", "l", "l", "a", "ʔ", "brk", "<eos>"]]
    assert lang_ids[0][3] == lang_ids[0][11] == NEUTRAL
    default = ShamiPhonemizer(diacritizer_backend="passthrough")
    assert default.phonemize("شو، هلق.", "ar") == ShamiPhonemizer(
        diacritizer_backend="passthrough", inventory=88).phonemize("شو، هلق.", "ar")
    assert not {"sil", "brk"} & set(default.phonemize("شو، هلق.", "ar")[0])


def test_the_90_tokeniser_reads_the_ipa_letters_sil_as_the_pause_symbol():
    """Upstream's longest-match tokeniser holds ``sil`` among its symbols, so the
    IPA ``s i l`` of سِلسِلة becomes the pause symbol twice. The 90 inventory keeps
    this, so its ids match the ids that upstream gives for the same text."""
    word = "سِلسِلة"
    assert TextFrontend(diacritizer_backend="passthrough").process(word).symbols == [
        "<bos>", "s", "i", "l", "s", "i", "l", "e", "<eos>"]
    assert TextFrontend(diacritizer_backend="passthrough", inventory=90).process(word).symbols == [
        "<bos>", "sil", "sil", "e", "<eos>"]


# Each row below is the output of upstream 80d79d0, run from a clone with the same
# stubs, for the same text: symbols, then language ids.
_EN = 2
UPSTREAM_PAUSE_ROWS = [
    # A pause takes the place of the word boundary before the next span.
    ("شو, delay", ["<bos>", "ʃ", "uː", "sil", "d", "ɛ", "l", "æ", "j", "<eos>"],
     [0, AR, AR, NEUTRAL, _EN, _EN, _EN, _EN, _EN, 0]),
    ("شو، hello", ["<bos>", "ʃ", "uː", "sil", "h", "ɛ", "l", "l", "ɒ", "<eos>"],
     [0, AR, AR, NEUTRAL, _EN, _EN, _EN, _EN, _EN, 0]),
    # An ellipsis and an em dash are sentence pauses.
    ("شو… هلق", ["<bos>", "ʃ", "uː", "brk", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL, NEUTRAL] + [AR] * 6 + [0]),
    ("شو — هلق", ["<bos>", "ʃ", "uː", "brk", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL, NEUTRAL] + [AR] * 6 + [0]),
    ("شو—هلق", ["<bos>", "ʃ", "uː", "brk", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL, NEUTRAL] + [AR] * 6 + [0]),
    # A question mark is no pause, and it stays on the word.
    ("شو؟ هلق", ["<bos>", "ʃ", "w", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL] + [AR] * 6 + [0]),
    ("شو? هلق", ["<bos>", "ʃ", "w", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL] + [AR] * 6 + [0]),
    # The blank chunks between pauses emit nothing.
    ("شو. . . هلق", ["<bos>", "ʃ", "uː", "brk", "brk", "brk", " ", "h", "a", "l", "l", "a", "ʔ", "<eos>"],
     [0, AR, AR, NEUTRAL, NEUTRAL, NEUTRAL, NEUTRAL] + [AR] * 6 + [0]),
    (". . .", ["<bos>", "brk", "brk", "brk", "<eos>"], [0, NEUTRAL, NEUTRAL, NEUTRAL, 0]),
]


@pytest.mark.parametrize("text, symbols, lang_ids", UPSTREAM_PAUSE_ROWS)
def test_the_90_pauses_match_upstream(monkeypatch, text, symbols, lang_ids):
    monkeypatch.setattr(espeak, "_ESPEAK", None)
    utterance = TextFrontend(diacritizer_backend="passthrough", inventory=90).process(text)
    assert utterance.symbols == symbols
    assert utterance.language_ids == lang_ids
    assert utterance.phoneme_ids == [SYMBOL_TO_ID_90[s] for s in symbols]


_STUB_IPA = {"delay": "dᵻlˈeɪ", "roses": "ɹˈoʊzᵻz", "كتاب": "kᵻtaːb"}


def _stub_espeak(monkeypatch):
    """espeak-ng that writes the reduced vowel ``ᵻ``, with no binary needed."""
    monkeypatch.setattr(espeak, "_ESPEAK", "/stub/espeak-ng")
    monkeypatch.setattr(espeak, "phonemize", lambda text, voice="en-us": " ".join(
        _STUB_IPA.get(word, word) for word in text.split()))


def test_english_spans_use_the_90_inventory(monkeypatch):
    _stub_espeak(monkeypatch)
    utterance = TextFrontend(diacritizer_backend="passthrough", inventory=90).process("delay, roses.")
    assert utterance.symbols == [
        "<bos>", "d", "ə", "l", "ˈ", "e͡ɪ", "sil", " ", "ɹ", "ˈ", "o͡ʊ", "z", "ə", "z", "brk", "<eos>"]
    assert utterance.language_ids == [0] + [_EN] * 5 + [NEUTRAL, NEUTRAL] + [_EN] * 6 + [NEUTRAL, 0]


def test_the_espeak_arabic_path_uses_the_90_inventory(monkeypatch):
    _stub_espeak(monkeypatch)
    monkeypatch.setattr(frontend, "get_diacritizer", lambda backend: None)
    utterance = TextFrontend(inventory=90).process("كتاب, كتاب.")
    assert utterance.symbols == [
        "<bos>", "k", "ə", "t", "aː", "b", "sil", " ", "k", "ə", "t", "aː", "b", "brk", "<eos>"]
    assert utterance.language_ids == [0] + [AR] * 5 + [NEUTRAL, NEUTRAL] + [AR] * 5 + [NEUTRAL, 0]
