"""Charsiu picks the dictionary whose data is in the script the request names.

CharsiuG2P (github.com/lingjzhu/CharsiuG2P) trains each label on one file in
``dicts/``:

- ``srp.tsv`` is Serbian in Cyrillic, eSpeak NG output over a word list
  (``sources/espeak-ng/srp.tsv``, ``sources/wordlist/srp.tsv``); first rows
  ``је je``, ``и ˈi``. Serbian defaults to Cyrillic. Its tag ties with
  ``hbs-cyrl``, and the list order in ``BYT5_LANGS`` breaks the tie.
- ``hbs-cyrl.tsv`` and ``hbs-latn.tsv`` are the WikiPron Serbo-Croatian lists
  (``sources/info/wikipron/hbs_cyrl_broad_info.txt``); ``hbs-latn`` is the only
  Latin-script Serbian data.
- ``bos.tsv`` is Bosnian in Latin script; there is no Croatian file.
- ``zho-s.tsv`` and ``zho-t.tsv`` are ipa-dict ``zh_hans.txt`` and
  ``zh_hant.txt`` (``sources/info/others/zh-hans_info.txt``, ``zh-hant_info.txt``),
  Mandarin readings such as 學 ɕɥœ˧˥. Cantonese has its own list, ``yue.tsv``.
- ``kur.tsv`` is the AsoSoft Kurdish G2P data, whose README says "Central
  Kurdish words in Standard Arabic script". No file holds Kurmanji.
"""
import unittest

from scriptconv.phonemizers import UnsupportedLanguageError
from scriptconv.phonemizers.mul import CharsiuPhonemizer


class TestCharsiuMatchTags(unittest.TestCase):
    def assertPicks(self, label, tags):
        for tag in tags:
            with self.subTest(tag=tag):
                self.assertEqual(CharsiuPhonemizer.get_lang(tag), label)

    def test_serbian_in_cyrillic_reaches_the_serbian_list(self):
        self.assertPicks("srp", ["sr-Cyrl", "sr", "sr-RS", "sr-Cyrl-RS", "srp-Cyrl"])

    def test_serbian_in_latin_reaches_the_latin_list(self):
        self.assertPicks("hbs-latn", ["sr-Latn", "hbs-latn", "sr-Latn-RS"])

    def test_bosnian_and_croatian_reach_the_bosnian_list(self):
        self.assertPicks("bos", ["bs", "hr"])

    def test_simplified_chinese_reaches_zh_hans(self):
        self.assertPicks("zho-s", ["zh", "zh-CN", "zh-Hans", "cmn"])

    def test_traditional_chinese_reaches_zh_hant(self):
        self.assertPicks("zho-t", ["zh-Hant", "zh-TW", "zh-Hant-TW"])

    def test_simplified_tag_is_mandarin(self):
        self.assertEqual(CharsiuPhonemizer.MATCH_TAGS["zho-s"], "cmn-Hans")

    def test_other_chinese_languages_do_not_reach_mandarin(self):
        for tag in ("yue-Hant-TW", "nan-Hant-TW"):
            with self.subTest(tag=tag):
                try:
                    picked = CharsiuPhonemizer.get_lang(tag)
                except UnsupportedLanguageError:
                    continue
                self.assertNotIn(picked, ("zho-s", "zho-t"))

    def test_central_kurdish_reaches_the_kurdish_list(self):
        self.assertPicks("kur", ["ckb", "ckb-Arab", "ckb-IQ"])

    def test_kurmanji_has_no_charsiu_data(self):
        for tag in ("ku", "kmr", "ku-Latn"):
            with self.subTest(tag=tag):
                with self.assertRaises(UnsupportedLanguageError):
                    CharsiuPhonemizer.get_lang(tag)

    def test_every_label_picks_itself(self):
        for label in CharsiuPhonemizer.BYT5_LANGS:
            self.assertPicks(label, [label])

    def test_a_label_in_upper_case_picks_itself(self):
        self.assertPicks("zho-t", ["ZHO-T"])
        self.assertPicks("hbs-cyrl", ["HBS-CYRL"])
        self.assertPicks("kur", ["KUR"])


if __name__ == "__main__":
    unittest.main()
