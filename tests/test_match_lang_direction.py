"""Language matching measures the requested tag against each supported tag.

``linguatag.lang_distance(desired, supported)`` is not symmetric: an Arabic
variety such as ``arz`` is near Modern Standard Arabic, but ``ar`` is not near
``arz``. Each expected value here comes from linguatag itself, called with the
requested tag first.
"""
import unittest

from linguatag import closest_lang, lang_distance

from scriptconv.phonemizers import BasePhonemizer
from scriptconv.phonemizers.ar import HalabiPhonemizer, IqraPhonemizer, MantoqPhonemizer
from scriptconv.phonemizers.mul import EspeakPhonemizer, GruutPhonemizer
from scriptconv.phonemizers.shami import ShamiPhonemizer

ARABIC_VARIETIES = ["arz", "arz-EG", "apc", "apc-SY", "ajp", "acm", "acm-IQ", "afb",
                    "aeb", "ary", "ary-MA", "arq", "ars", "acw"]


class TestMatchLangDirection(unittest.TestCase):
    def test_distance_is_measured_from_the_requested_tag(self):
        for tag in ARABIC_VARIETIES:
            with self.subTest(tag=tag):
                self.assertEqual(BasePhonemizer._match_lang(tag, ["ar", "en"]),
                                 ("ar", lang_distance(tag, "ar")))

    def test_arabic_variety_falls_back_to_msa(self):
        for tag in ARABIC_VARIETIES:
            expected = closest_lang(tag, ["ar"])
            self.assertIsNotNone(expected)
            with self.subTest(tag=tag):
                self.assertEqual(BasePhonemizer.match_lang(tag, ["ar"]), expected)

    def test_msa_request_does_not_fall_back_to_a_variety(self):
        self.assertIsNone(closest_lang("ar", ["arz"]))
        with self.assertRaises(ValueError):
            BasePhonemizer.match_lang("ar", ["arz"])


class TestArabicVarietyPhonemizers(unittest.TestCase):
    def assert_matches_linguatag(self, phonemizer, pool):
        for tag in ARABIC_VARIETIES:
            expected = closest_lang(tag, pool)
            self.assertIsNotNone(expected)
            with self.subTest(phonemizer=phonemizer.__name__, tag=tag):
                self.assertEqual(phonemizer.get_lang(tag), expected)

    def test_espeak(self):
        self.assert_matches_linguatag(EspeakPhonemizer, EspeakPhonemizer.ESPEAK_LANGS)

    def test_gruut(self):
        self.assert_matches_linguatag(GruutPhonemizer, GruutPhonemizer.GRUUT_LANGS)

    def test_msa_only_backends(self):
        for phonemizer in (MantoqPhonemizer, HalabiPhonemizer, IqraPhonemizer):
            self.assert_matches_linguatag(phonemizer, ["ar"])

    def test_shami(self):
        self.assert_matches_linguatag(ShamiPhonemizer, ["ar", "en"])


if __name__ == "__main__":
    unittest.main()
