import unittest

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class


class TestVendoredKorean(unittest.TestCase):
    def test_hangul2ipa_pipeline(self):
        from scriptconv.phonemizers._thirdparty.hangul2ipa import hangul2ipa
        out = hangul2ipa("안녕하세요")
        self.assertTrue(out and all(ord(c) > 64 for c in out))

    def test_ko_tables_packaged_via_resources(self):
        import os
        from scriptconv.phonemizers import _thirdparty
        tables = os.path.join(os.path.dirname(_thirdparty.__file__), "ko_tables")
        self.assertTrue(os.path.isfile(os.path.join(tables, "ipa.csv")))


class TestVendoredChinese(unittest.TestCase):
    def test_zh_num(self):
        from scriptconv.phonemizers._thirdparty.zh_num import num2str
        self.assertEqual(num2str("123"), "一百二十三")


class TestShamiFrontend(unittest.TestCase):
    def test_codeswitch_language_ids_align(self):
        from scriptconv.phonemizers.shami import ShamiPhonemizer
        p = ShamiPhonemizer()
        phonemes, lang_ids = p.phonemize_with_language_ids("مرحبا hello", "ar")
        self.assertEqual(len(phonemes), len(lang_ids))
        for ph, ids in zip(phonemes, lang_ids):
            self.assertEqual(len(ph), len(ids))

    def test_lazy_matches_eager(self):
        from scriptconv.phonemizers.shami import ShamiPhonemizer
        p = ShamiPhonemizer()
        text = "مرحبا. كيف حالك؟"
        eager = p.phonemize_with_language_ids(text, "ar")
        lazy = list(p.phonemize_with_language_ids_lazy(text, "ar"))
        self.assertEqual(eager[0], [ph for ph, _ in lazy])


class TestLicensingStubs(unittest.TestCase):
    def test_mantoq_stub_explains_licensing(self):
        cls = get_phonemizer_class(Phonemizer.MANTOQ)
        with self.assertRaises(ImportError) as ctx:
            cls()
        self.assertIn("BY-NC", str(ctx.exception).replace("CC BY-NC", "BY-NC"))

    def test_kog2p_stub_explains_licensing(self):
        cls = get_phonemizer_class(Phonemizer.KOG2PK)
        with self.assertRaises(ImportError) as ctx:
            cls()
        self.assertIn("GPL", str(ctx.exception))

    def test_no_gpl_or_nc_files_in_tree(self):
        import pathlib, re
        root = pathlib.Path("scriptconv")
        offenders = []
        for f in root.rglob("*.py"):
            head = f.read_text(errors="ignore")[:800]
            if re.search(r"@license:\s*GPL|Creative Commons Attribution-NonCommercial"
                         r"|creativecommons\.org/licenses/by-nc", head):
                offenders.append(str(f))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
