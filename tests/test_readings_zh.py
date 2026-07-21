import sys
import unittest
from unittest import mock

from scriptconv import to_pinyin, to_bopomofo
from scriptconv import readings


class TestToPinyin(unittest.TestCase):
    def test_hanzi_resolved_with_tone_marks(self):
        self.assertEqual(to_pinyin("中国人"), "zhōng guó rén")

    def test_tone_number_style(self):
        self.assertEqual(to_pinyin("中国人", tone="number"), "zhong1 guo2 ren2")

    def test_tone_none_style(self):
        self.assertEqual(to_pinyin("中国人", tone="none"), "zhong guo ren")

    def test_heteronym_resolved_by_phrase_context(self):
        # 行 reads háng in 银行 (bank) but xíng in 行走 (to walk)
        self.assertIn("háng", to_pinyin("银行"))
        self.assertIn("xíng", to_pinyin("行走"))

    def test_non_chinese_passes_through(self):
        self.assertEqual(to_pinyin("OVOS 123!"), "OVOS 123!")

    def test_mixed_script_sentence(self):
        out = to_pinyin("我有3个apple")
        self.assertIn("wǒ", out)
        self.assertIn("apple", out)

    def test_invalid_tone_raises_value_error(self):
        with self.assertRaises(ValueError):
            to_pinyin("中", tone="fancy")

    def test_empty_string(self):
        self.assertEqual(to_pinyin(""), "")


class TestToBopomofo(unittest.TestCase):
    def test_hanzi_resolved_to_zhuyin(self):
        self.assertEqual(to_bopomofo("中国"), "ㄓㄨㄥ ㄍㄨㄛˊ")

    def test_first_tone_unmarked_second_tone_marked(self):
        out = to_bopomofo("中国")
        self.assertNotIn("ˉ", out)
        self.assertIn("ˊ", out)

    def test_non_chinese_passes_through(self):
        self.assertEqual(to_bopomofo("OVOS 123!"), "OVOS 123!")

    def test_empty_string(self):
        self.assertEqual(to_bopomofo(""), "")


class TestDependencyBoundary(unittest.TestCase):
    def test_missing_pypinyin_raises_with_install_hint(self):
        with mock.patch.object(readings, "_PINYIN_STYLES", None), \
                mock.patch.dict(sys.modules, {"pypinyin": None}):
            with self.assertRaises(ImportError) as ctx:
                to_pinyin("中国")
            self.assertIn("scriptconv[zh]", str(ctx.exception))

    def test_style_table_is_cached(self):
        to_pinyin("中国")
        first = readings._PINYIN_STYLES
        to_bopomofo("中国")
        self.assertIs(readings._PINYIN_STYLES, first)

    def test_chinese_and_japanese_backends_independent(self):
        # pypinyin absence must not break Japanese conversion
        with mock.patch.object(readings, "_PINYIN_STYLES", None), \
                mock.patch.dict(sys.modules, {"pypinyin": None}):
            self.assertEqual(readings.to_hiragana("日本語"), "にほんご")


if __name__ == "__main__":
    unittest.main()
