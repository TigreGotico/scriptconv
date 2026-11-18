"""A spelling longer than any word of dizione's lexicon is read in pieces.

dizione forms the pronunciation of one spelling in the engine's ``word()``: it
looks the spelling up, derives it from a shorter word, builds it from two words,
and else hands the whole spelling to the unknown-word model. The model emits a
phone stream, and the aligner then matches letters to phones with a table of one
cell per letter and per phone, so the work grows with the product of the two: a
run of letters far longer than any word exhausts the memory of the machine. The
backend bounds the spelling there, in the engine, and not in the text, so every
mark, hyphen, apostrophe and part of a web address keeps the reading it had.

Measured against dev (the branch point) on ``phonemize_string``, in a process
under ``RLIMIT_AS`` of 3 000 000 KiB with a limit of 20 s:

    input                        dev                  this backend
    "abcdefghij" * 2000          no finish in 20 s    4.4 s
    "abcdefghi-" * 2000          1.3 s                1.3 s
    ("x" * 27 + "'") * 700       no finish in 20 s    2.8 s
    "abcdefghij" * 2000 + "."    no finish in 20 s    4.0 s

dev raises ``MemoryError`` on the runs that no longer finish, or holds the
machine until the limit ends it. A run of hyphenated parts is one word of
dizione's own tokenization each, so the bound never applied to it.
"""
import resource
import subprocess
import sys

import pytest

from scriptconv.phonemizers import dizione
from scriptconv.phonemizers.dizione import DATA_DIR, DizionePhonemizer

# The cap comes from the data: the longest word of the lexicon that dizione
# reads, "antidisestablishmentarianism".
CAP = max(len(line.split("\t", 1)[0])
          for line in (DATA_DIR / "lexicon.tsv").read_text(encoding="utf-8").splitlines() if line)

# Recorded from dev, before this change, with the same data.
RECORDED = [
    ('He said "antidisestablishmentarianism", then left.',
     "hiː sˈɛd ˌæntaɪdˌɪsəstˌæblɪʃməntˈɛɹiənˌɪzəm ðˈɛn lˈɛft"),
    ("a mother-in-law-to-be-and-father-in-law pair",
     "ɐ mˈʌðɚɹɪnlˈɔːtəbiːændfˈɑːðɚɹɪnlˈɔː pˈɛɹ"),
    ("see www.example.com/a/very/long/path/here now",
     "sˈiː ɛɡzˈæmpəl dˈɑːt kˈɑːm slˈæʃ ˈeɪ slˈæʃ vˈɛɹi slˈæʃ lˈɔŋ slˈæʃ pˈæθ slˈæʃ hˈɪɹ nˈaʊ"),
    ("It is antidisestablishmentarianism.",
     "ɪɾ ɪz ˌæntaɪdˌɪsəstˌæblɪʃməntˈɛɹiənˌɪzəm"),
]

_INPUTS = {
    "letters": "abcdefghij" * 2000,
    "hyphens": "abcdefghi-" * 2000,
    "apostrophes": ("x" * 27 + "'") * 700,
    "full stop": "abcdefghij" * 2000 + ".",
}

_PROBE = """
import resource, sys, time
from scriptconv.phonemizers.dizione import DizionePhonemizer

text = {
    "letters": "abcdefghij" * 2000,
    "hyphens": "abcdefghi-" * 2000,
    "apostrophes": ("x" * 27 + "'") * 700,
    "full stop": "abcdefghij" * 2000 + ".",
}[sys.argv[1]]
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
start = time.monotonic()
DizionePhonemizer().phonemize_string(text, "en-US")
elapsed = time.monotonic() - start
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(elapsed, after - before)
"""


@pytest.fixture(scope="module")
def phonemizer():
    return DizionePhonemizer()


def test_the_bound_is_the_longest_word_of_the_lexicon():
    assert dizione._MAX_WORD_LENGTH == CAP
    assert CAP == len("antidisestablishmentarianism")


@pytest.mark.parametrize("text, expected", RECORDED, ids=[text[:20] for text, _ in RECORDED])
def test_the_reading_is_the_one_dev_gives(phonemizer, text, expected):
    assert phonemizer.phonemize_string(text, "en-US") == expected
    assert phonemizer.phonemize(text, "en-US") == [list(expected)]


@pytest.mark.parametrize("name", _INPUTS, ids=_INPUTS)
def test_a_run_too_long_for_a_word_finishes_in_time_and_memory(name):
    limit = 3_000_000 * 1024
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, name], capture_output=True, text=True, timeout=20,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_AS, (limit, limit)))
    assert proc.returncode == 0, proc.stderr[-2000:]
    elapsed, growth = (float(value) for value in proc.stdout.split())
    assert elapsed < 20
    # ru_maxrss is in KiB on Linux.
    assert growth < 500 * 1024


def test_a_word_over_the_bound_reads_as_its_pieces(phonemizer):
    # 40 letters, no hyphen: no word of the lexicon, so dizione reads 28 and 12.
    text = "abcdefghij" * 4
    assert len(text) == 40 > CAP
    pieces = [text[start:start + CAP] for start in range(0, len(text), CAP)]
    assert [len(piece) for piece in pieces] == [CAP, 40 - CAP]
    expected = "".join(phonemizer.phonemize_string(piece, "en-US") for piece in pieces)
    assert phonemizer.phonemize_string(text, "en-US") == expected
    assert phonemizer.phonemize(text, "en-US") == [list(expected)]


def test_the_longest_word_of_the_lexicon_is_read_whole(phonemizer):
    assert phonemizer.phonemize_string("antidisestablishmentarianism", "en-US") == \
        "ˌæntaɪdˌɪsəstˌæblɪʃməntˈɛɹiənˌɪzəm"


def test_hyphenated_parts_are_words_of_their_own(phonemizer):
    # Each part of a hyphenated word is read as a word, however long the
    # compound: the bound is per spelling, not per run of non-whitespace.
    text = "antidisestablishmentarianism-antidisestablishmentarianism"
    part = phonemizer.phonemize_string("antidisestablishmentarianism", "en-US")
    assert phonemizer.phonemize_string(text, "en-US") == part + part
