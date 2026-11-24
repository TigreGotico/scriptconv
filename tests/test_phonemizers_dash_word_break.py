"""A run of dashes between two words must not join them into one word.

A doubled dash reads as one dash and gives a word break. The Armenian hyphen
and the Hebrew maqaf read as the ASCII hyphen. The check covers both
``remove_punctuation`` and the frontend with no punctuation kept, where the
defect was visible.
"""

import unittest
from pathlib import Path
from unittest import mock

import scriptconv.phonemizers.base as base
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Phonemizer


DASH_CASES = (
    ("en", "flew--slowly", "flew slowly"),
    ("en", "flew\u2014\u2014slowly", "flew slowly"),
    ("en", "flew\u2014slowly", "flew slowly"),
    ("en", "flew-slowly", "flew-slowly"),
    ("hy", "բարի֊լույս", "բարի-լույս"),
    ("he", "בית־ספר", "בית-ספר"),
)


def _frontend():
    return TextFrontend(FrontendConfig("en", Phonemizer.GRAPHEMES,
                                       keep_punctuation=False,
                                       stages=Stages(diacritize=False, normalize=False)))


class TestDashRunsKeepAWordBreak(unittest.TestCase):
    def test_the_frontend_separates_every_case(self):
        fe = _frontend()
        for lang, text, expected in DASH_CASES:
            with self.subTest(text=text):
                self.assertEqual("".join(fe.phonemize_flat(text)), expected)

    def test_remove_punctuation_separates_a_doubled_dash(self):
        for text in ("flew--slowly", "flew\u2014\u2014slowly", "flew\u2014--slowly"):
            with self.subTest(text=text):
                self.assertEqual(BasePhonemizer.remove_punctuation(text), "flew slowly")

    def test_remove_punctuation_reads_the_armenian_hyphen(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("բարի֊լույս"), "բարի-լույս")

    def test_remove_punctuation_reads_the_hebrew_maqaf(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("בית־ספר"), "בית-ספר")

    def test_a_single_ascii_hyphen_still_joins_a_compound(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("mother-in-law"), "mother-in-law")

    def test_a_digit_range_still_keeps_its_hyphen(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("1139-1185"), "1139-1185")

    def test_a_doubled_dash_outside_words_is_dropped(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("--flew--"), "flew")

    def test_a_long_run_of_dashes_costs_linear_work(self):
        text = "a" + "-" * 16000 + "b"
        lookups = 0

        class ScannedDashes(frozenset):
            def __contains__(self, c):
                nonlocal lookups
                lookups += 1
                if lookups > 3 * len(text):
                    raise AssertionError(f"over {3 * len(text)} dash lookups for {len(text)} characters")
                return super().__contains__(c)

        with mock.patch.object(base, "_DASH_RUN", ScannedDashes(base._DASH_RUN)):
            self.assertEqual(BasePhonemizer.remove_punctuation(text), "a b")


    def test_the_docs_state_the_immediate_neighbour_rule(self):
        page = (Path(__file__).resolve().parents[1] / "docs" / "phonemizers.md").read_text()
        page = " ".join(page.split())
        for phrase in ("A dash immediately between a letter and a letter",
                       "Two or more hyphens or dashes immediately between two letters or digits"):
            self.assertTrue(phrase in page, f"missing: {phrase}")
        self.assertFalse("A dash run never joins the two words" in page, "the broad claim is back")


if __name__ == "__main__":
    unittest.main()
