"""Every written form of a diphthong reads as its ARPABET phone.

A tie bar above or below, or a non-syllabic mark on the glide, does not split
a diphthong. The SSB GOAT row begins with ə, so the tied and non-syllabic
forms of əʊ must read as OW as the other diphthong rows do. Both error modes
must agree.
"""
import unittest

from scriptconv.notation import ipa_to_arpa

TIES = ("\u0361", "\u035c")
NONSYLLABIC = "\u032f"

# ARPABET phone, nucleus, canonical glide, alternate glide. The last row is
# the SSB GOAT vowel.
ROWS = (
    ("AY", "a", "ɪ", "i"),
    ("EY", "e", "ɪ", "i"),
    ("OW", "o", "ʊ", "u"),
    ("OW", "ə", "ʊ", "u"),
    ("AW", "a", "ʊ", "u"),
    ("OY", "ɔ", "ɪ", "i"),
)


def _written_forms(nucleus, glide, alternate):
    yield nucleus + glide
    for written in (glide, alternate):
        yield nucleus + written + NONSYLLABIC
        for tie in TIES:
            yield nucleus + tie + written


class TestEveryDiphthongSpelling(unittest.TestCase):
    def test_all_written_forms_give_the_phone(self):
        for phone, nucleus, glide, alternate in ROWS:
            for form in _written_forms(nucleus, glide, alternate):
                with self.subTest(form=form):
                    self.assertEqual(ipa_to_arpa(form), phone)
                    self.assertEqual(ipa_to_arpa(form, errors="strict"), phone)

    def test_the_reported_examples(self):
        for form in ("ə͡ʊ", "ə͜ʊ", "əʊ̯", "əu̯", "ə͡u", "ə͜u"):
            with self.subTest(form=form):
                self.assertEqual(ipa_to_arpa(form), "OW")
                self.assertEqual(ipa_to_arpa(form, errors="strict"), "OW")

    def test_the_plain_form_is_unchanged(self):
        self.assertEqual(ipa_to_arpa("əʊ"), "OW")
        self.assertEqual(ipa_to_arpa("əʊ", errors="strict"), "OW")

    def test_an_unknown_phoneme_is_still_unknown(self):
        self.assertEqual(ipa_to_arpa("ɸ"), "?")
        with self.assertRaises(Exception):
            ipa_to_arpa("ɸ", errors="strict")


if __name__ == "__main__":
    unittest.main()
