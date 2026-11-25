"""The check for whitespace before a block reads only the end of the text.

The old pattern ``r"\\s\\W*$"`` searched from every whitespace character to
the end, which took quadratic time on a long run of whitespace followed by a
word. The tests below hold the exact regex result as the reference and bound
the work of the end-only scan.
"""
import random
import re
import unittest

from scriptconv import frontend as frontend_module
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers.enums import Phonemizer

REFERENCE = re.compile(r"\s\W*$")

# Word characters, whitespace and marks, including a trailing-newline case.
ALPHABET = "aB_9 \t\n\u00a0\u2003\u3000.,!-'"

CASES = (
    ("", False),
    ("a", False),
    (" ", True),
    (" \n", True),
    ("a ", True),
    ("a \n", True),
    ("a\n", True),
    ("a\t", True),
    ("a,", False),
    ("a, ", True),
    ("a, !", True),
    ("a, !b", False),
    ("a-b", False),
    ("a-", False),
    ("a_-", False),
    ("_ ", True),
    ("9 ", True),
    (" _,", False),
    ("a\u2163", False),
    ("a\u00b2", False),
    ("a\u00a0", True),
    ("a\u00a0b", False),
    ("a\u2003", True),
    ("a\u3000", True),
    ("a\u2028", True),
    ("é ", True),
    ("中, ", True),
    ("\u200b", False),
    ("\u200b ", True),
    ("a" + " " * 20000 + "b", False),
    ("a" + " " * 20000, True),
)


class CountingString(str):
    """A string that counts the characters an end-only scan reads."""

    def __init__(self, *args):
        self.reads = 0

    def __getitem__(self, index):
        self.reads += 1
        return super().__getitem__(index)


def _check(text):
    return bool(frontend_module._space_before_block(text))


class TestSpaceBeforeBlockEquivalence(unittest.TestCase):
    def test_curated_texts_keep_the_regex_result(self):
        for text, expected in CASES:
            with self.subTest(text=text[:40]):
                self.assertEqual(bool(REFERENCE.search(text)), expected)
                self.assertEqual(_check(text), expected)

    def test_every_short_string_keeps_the_regex_result(self):
        for first in ALPHABET:
            for second in ALPHABET:
                for third in ALPHABET:
                    text = first + second + third
                    with self.subTest(text=text):
                        self.assertEqual(_check(text), bool(REFERENCE.search(text)))

    def test_seeded_longer_strings_keep_the_regex_result(self):
        rng = random.Random(408)
        for _ in range(500):
            text = "".join(rng.choice(ALPHABET) for _ in range(rng.randrange(41)))
            with self.subTest(text=text):
                self.assertEqual(_check(text), bool(REFERENCE.search(text)))


class TestSpaceBeforeBlockReadsOnlyTheEnd(unittest.TestCase):
    def test_a_long_whitespace_run_before_a_word_reads_one_character(self):
        text = CountingString("a" + " " * 16000 + "b")
        self.assertFalse(_check(text))
        self.assertEqual(text.reads, 1)

    def test_a_long_trailing_whitespace_run_reads_one_character(self):
        text = CountingString("a" + " " * 16000)
        self.assertTrue(_check(text))
        self.assertEqual(text.reads, 1)

    def test_a_long_mark_run_costs_linear_work(self):
        text = CountingString("a" + "," * 16000 + "b")
        self.assertFalse(_check(text))
        self.assertLessEqual(text.reads, len(text) + 1)

    def test_a_space_inside_a_mark_run_stops_the_scan(self):
        text = CountingString("a" + "," * 16000 + " " + "," * 16000)
        self.assertTrue(_check(text))
        self.assertLessEqual(text.reads, 16002)


class TestBlockJoinUnchanged(unittest.TestCase):
    def test_a_long_whitespace_run_before_a_block_gives_the_same_reading(self):
        fe = TextFrontend(FrontendConfig(
            "en", Phonemizer.GRAPHEMES,
            stages=Stages(diacritize=False, normalize=False)))
        short = "".join(fe.phonemize_flat("a [[QZ]] b"))
        long = "".join(fe.phonemize_flat("a" + " " * 20000 + "[[QZ]] b"))
        self.assertEqual(long, short)
        self.assertEqual(short, "a QZ b")


if __name__ == "__main__":
    unittest.main()
