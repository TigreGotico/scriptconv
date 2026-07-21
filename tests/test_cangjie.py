import unittest

from scriptconv import cangjie_code, to_cangjie
from scriptconv import cangjie


class TestCangjieCode(unittest.TestCase):
    def test_official_single_radical_glyphs(self):
        self.assertEqual(cangjie_code("日"), "a")
        self.assertEqual(cangjie_code("木"), "d")

    def test_multi_radical_glyph(self):
        self.assertEqual(cangjie_code("昌"), "aa")

    def test_unmapped_returns_none(self):
        self.assertIsNone(cangjie_code("X"))
        self.assertIsNone(cangjie_code("1"))
        self.assertIsNone(cangjie_code(" "))

    def test_codes_are_lowercase_alpha(self):
        table = cangjie._table()
        self.assertGreater(len(table), 100000)
        sample = list(table.values())[:5000]
        self.assertTrue(all(c.isalpha() and c.islower() for c in sample))


class TestTableIsPackaged(unittest.TestCase):
    def test_data_file_resolvable_via_importlib_resources(self):
        from importlib.resources import files
        raw = files("scriptconv.data").joinpath("cangjie5_tc.tsv.gz").read_bytes()
        self.assertGreater(len(raw), 100000)


class TestToCangjie(unittest.TestCase):
    def test_all_hanzi_sentence(self):
        self.assertEqual(to_cangjie("倉頡"), "oiar grmbc")

    def test_custom_separator(self):
        self.assertEqual(to_cangjie("倉頡", sep="|"), "oiar|grmbc")

    def test_unmapped_runs_stay_contiguous(self):
        self.assertEqual(to_cangjie("我有ABC 123!"), "hqi kb ABC 123!")

    def test_non_chinese_only_passes_through_verbatim(self):
        self.assertEqual(to_cangjie("OVOS 123!"), "OVOS 123!")

    def test_empty_string(self):
        self.assertEqual(to_cangjie(""), "")

    def test_table_loaded_once(self):
        to_cangjie("日")
        first = cangjie._TABLE
        cangjie_code("木")
        self.assertIs(cangjie._TABLE, first)


if __name__ == "__main__":
    unittest.main()
