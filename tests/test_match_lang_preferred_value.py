"""A deprecated language code and its Preferred-Value name one language.

RFC 5646 section 4.5 replaces a deprecated subtag by its Preferred-Value, so
``ajp`` and ``apc`` measure the same distance to a request, and so do ``yol``
and ``enm`` (IANA Language Subtag Registry). When a supported list holds both
codes, the code the request spells wins the tie, whatever the list order.
"""
import unittest

from linguatag import lang_distance

from scriptconv.phonemizers import BasePhonemizer


class TestPreferredValueTie(unittest.TestCase):
    def test_request_for_the_preferred_value_picks_it(self):
        for tag in ("apc-SY", "apc-LB", "apc-JO", "apc-Arab"):
            with self.subTest(tag=tag):
                self.assertEqual(BasePhonemizer._match_lang(tag, ["ajp", "apc"]),
                                 ("apc", lang_distance(tag, "apc")))

    def test_request_for_the_deprecated_code_picks_it(self):
        for tag in ("yol-IE", "yol-Latn"):
            with self.subTest(tag=tag):
                self.assertEqual(BasePhonemizer._match_lang(tag, ["enm", "yol"]),
                                 ("yol", lang_distance(tag, "yol")))

    def test_list_order_does_not_decide(self):
        for pool in (["ajp", "apc"], ["apc", "ajp"]):
            with self.subTest(pool=pool):
                self.assertEqual(BasePhonemizer.match_lang("apc-SY", pool), "apc")
                self.assertEqual(BasePhonemizer.match_lang("ajp-JO", pool), "ajp")


if __name__ == "__main__":
    unittest.main()
