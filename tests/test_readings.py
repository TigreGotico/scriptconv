import sys
import unittest
from unittest import mock

from scriptconv import to_hiragana, to_katakana
from scriptconv import readings


class TestToHiragana(unittest.TestCase):
    def test_kanji_resolved_to_reading(self):
        self.assertEqual(to_hiragana("日本語"), "にほんご")

    def test_katakana_folded_by_default(self):
        self.assertEqual(to_hiragana("コーヒー"), "こーひー")

    def test_keep_katakana_flag_preserves_loanwords(self):
        self.assertEqual(to_hiragana("コーヒー", keep_katakana=True), "コーヒー")

    def test_keep_katakana_still_converts_kanji(self):
        out = to_hiragana("私はコーヒーが好き", keep_katakana=True)
        self.assertIn("コーヒー", out)
        self.assertNotIn("私", out)
        self.assertNotIn("好", out)

    def test_hiragana_passes_through(self):
        self.assertEqual(to_hiragana("こんにちは"), "こんにちは")

    def test_non_japanese_passes_through(self):
        self.assertEqual(to_hiragana("OVOS 123!"), "OVOS 123!")

    def test_mixed_script_sentence(self):
        out = to_hiragana("東京タワーは333mです")
        self.assertIn("とうきょう", out)
        self.assertIn("333m", out)

    def test_empty_string(self):
        self.assertEqual(to_hiragana(""), "")


class TestToKatakana(unittest.TestCase):
    def test_kanji_resolved_to_reading(self):
        self.assertEqual(to_katakana("日本語"), "ニホンゴ")

    def test_hiragana_transposed(self):
        self.assertEqual(to_katakana("こんにちは"), "コンニチハ")

    def test_katakana_passes_through(self):
        self.assertEqual(to_katakana("コーヒー"), "コーヒー")

    def test_non_japanese_passes_through(self):
        self.assertEqual(to_katakana("OVOS 123!"), "OVOS 123!")

    def test_empty_string(self):
        self.assertEqual(to_katakana(""), "")


class TestDependencyBoundary(unittest.TestCase):
    def test_missing_pykakasi_raises_with_install_hint(self):
        with mock.patch.object(readings, "_kakasi", None), \
                mock.patch.dict(sys.modules, {"pykakasi": None}):
            with self.assertRaises(ImportError) as ctx:
                to_hiragana("日本語")
            self.assertIn("scriptconv[ja]", str(ctx.exception))

    def test_converter_instance_is_cached(self):
        to_hiragana("日本語")
        first = readings._kakasi
        to_katakana("日本語")
        self.assertIs(readings._kakasi, first)


if __name__ == "__main__":
    unittest.main()


class TestTokens(unittest.TestCase):
    def test_yields_reading_tokens_with_all_forms(self):
        from scriptconv import ReadingToken, tokens
        toks = list(tokens("東京タワー"))
        self.assertTrue(all(isinstance(t, ReadingToken) for t in toks))
        origs = [t.orig for t in toks]
        self.assertIn("東京", origs)
        tokyo = toks[origs.index("東京")]
        self.assertEqual(tokyo.hira, "とうきょう")
        self.assertEqual(tokyo.kana, "トウキョウ")

    def test_tokens_cover_input_exactly(self):
        from scriptconv import tokens
        text = "私はcoffeeが好き"
        self.assertEqual("".join(t.orig for t in tokens(text)), text)

    def test_empty_string_yields_nothing(self):
        from scriptconv import tokens
        self.assertEqual(list(tokens("")), [])


class TestSegmentFlag(unittest.TestCase):
    def test_hiragana_wakachigaki(self):
        from scriptconv import to_hiragana
        self.assertEqual(to_hiragana("私は学生です", segment=True),
                         "わたし は がくせい です")

    def test_katakana_wakachigaki(self):
        from scriptconv import to_katakana
        self.assertEqual(to_katakana("私は学生です", segment=True),
                         "ワタシ ハ ガクセイ デス")

    def test_segment_false_is_default_concatenation(self):
        from scriptconv import to_hiragana
        self.assertEqual(to_hiragana("私は学生です"), "わたしはがくせいです")

    def test_segment_collapses_original_whitespace(self):
        from scriptconv import to_hiragana
        out = to_hiragana("東京 大阪", segment=True)
        self.assertNotIn("  ", out)
