"""Clause marks next to a digit, and a colon inside a word, in ``remove_punctuation`` and ``chunk_text``."""
import unittest

from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import BasePhonemizer, GraphemePhonemizer


class TestMarksAfterADigitAndInAWord(unittest.TestCase):
    """tts-punctuation: a "!" or "?" with no space after it "is no clause
    break and gives no token, but it still separates two words, so it becomes
    a space"; a number is a word. "The rule that a mark must be followed by a
    space stays for the other marks, so `10,4` and `16:30` never split."""

    def test_a_mark_after_a_digit_separates_two_words(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("Pay 4.50!They go."), "Pay 4.50 They go")
        self.assertEqual(BasePhonemizer.remove_punctuation("Pay 4.50?!They go."), "Pay 4.50 They go")

    def test_a_mark_between_two_digits_stays(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("16!30"), "16!30")

    def test_the_grapheme_backend_reads_a_mark_after_a_digit_as_a_space(self):
        for keep, end in ((False, ""), (True, ".")):
            with self.subTest(keep_punctuation=keep):
                frontend = TextFrontend(FrontendConfig("en", keep_punctuation=keep), GraphemePhonemizer())
                self.assertEqual(frontend.phonemize_flat("Pay 4.50!They go."), list("pay 4.50 they go" + end))

    def test_a_colon_at_the_end_of_the_text_cuts_it(self):
        self.assertEqual(BasePhonemizer.chunk_text("Disse isto:")[0], ("Disse isto", ":", False))

    def test_a_colon_inside_a_word_does_not_cut_it(self):
        # FLORES-200 ben_Beng devtest writes "নি:সন্দেহে" ("without doubt") with an ASCII colon
        self.assertEqual(BasePhonemizer.chunk_text("নি:সন্দেহে ভালো।"), [("নি:সন্দেহে ভালো।", ".", True)])
        self.assertEqual(["".join(chunk) for chunk in GraphemePhonemizer().phonemize("নি:সন্দেহে ভালো।", "bn")],
                         ["নিসন্দেহে ভালো"])

    def test_the_word_reads_the_same_with_punctuation_on_and_off(self):
        on = GraphemePhonemizer()
        on.keep_punctuation = True
        self.assertEqual(on.phonemize_to_list("নি:সন্দেহে ভালো।", "bn"),
                         GraphemePhonemizer().phonemize_to_list("নি:সন্দেহে ভালো।", "bn"))

    def test_a_colon_or_semicolon_before_whitespace_still_cuts(self):
        self.assertEqual(BasePhonemizer.chunk_text("Nota: fim; sim."),
                         [("Nota", ":", False), ("fim", ";", False), ("sim.", ".", True)])
