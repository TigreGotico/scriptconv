import unittest

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
from scriptconv.phonemizers.registry import get_phonemizer


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

    def test_zh_num_fullwidth_digits_normalized(self):
        # zh_num.DIGITS is keyed by ASCII "0"-"9"; full-width digits (e.g.
        # "３") must be NFKC-folded before lookup or num2str raises KeyError
        import unicodedata
        from scriptconv.phonemizers._thirdparty.zh_num import num2str
        fullwidth = "１２３"
        self.assertEqual(
            num2str(unicodedata.normalize("NFKC", fullwidth)),
            num2str("123"),
        )


class TestPinyinRetone(unittest.TestCase):
    def test_retone_tone_marks(self):
        from scriptconv.phonemizers.zh import BaseChinesePinyinPhonemizer
        retoned = BaseChinesePinyinPhonemizer._retone("ma˥")
        self.assertEqual(retoned, "ma→")

    def test_retone_leftover_syllabic_mark_does_not_raise(self):
        # any pinyin_to_ipa output carrying an unanticipated combining
        # U+0329 (not attached to ɻ/ɹ) must degrade gracefully, not crash
        from scriptconv.phonemizers.zh import BaseChinesePinyinPhonemizer
        leftover = "n" + chr(809)
        retoned = BaseChinesePinyinPhonemizer._retone(leftover)
        self.assertEqual(retoned, leftover)


class TestZhBackendFriendlyImportErrors(unittest.TestCase):
    def _assert_friendly(self, module_name, cls, extra):
        # sys.modules[name] = None makes the `import` statement raise
        # ImportError regardless of whether the package is actually
        # installed, so this simulates the missing-dependency case cleanly
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules, {module_name: None}):
            with self.assertRaises(ImportError) as ctx:
                cls()
        self.assertIn(f"scriptconv[{extra}]", str(ctx.exception))

    def test_pypinyin_missing_dep_message(self):
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        self._assert_friendly("pypinyin", PypinyinPhonemizer, "zh")

    def test_xpinyin_missing_dep_message(self):
        from scriptconv.phonemizers.zh import XpinyinPhonemizer
        self._assert_friendly("xpinyin", XpinyinPhonemizer, "zh-phonemizers")

    def test_g2pm_missing_dep_message(self):
        from scriptconv.phonemizers.zh import G2pMPhonemizer
        self._assert_friendly("g2pM", G2pMPhonemizer, "zh-phonemizers")

    def test_g2pc_missing_dep_message(self):
        from scriptconv.phonemizers.zh import G2pCPhonemizer
        self._assert_friendly("g2pc", G2pCPhonemizer, "zh-phonemizers")

    def test_pinyin_to_ipa_missing_dep_message(self):
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        self._assert_friendly("pinyin_to_ipa", PypinyinPhonemizer, "zh-phonemizers")


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

    def test_phonemize_lazy_matches_phonemize(self):
        """phoonnx (and any streaming caller) consumes phonemize_lazy only."""
        from scriptconv.phonemizers.shami import ShamiPhonemizer
        p = ShamiPhonemizer()
        text = "\u0627\u0644\u062c\u0648 \u062d\u0644\u0648 \u0627\u0644\u064a\u0648\u0645. \u0627\u0644\u0634\u062c\u0631\u0629 \u0643\u0628\u064a\u0631\u0629."
        self.assertEqual(p.phonemize(text, "ar"),
                         list(p.phonemize_lazy(text, "ar")))

    def test_phonemize_lazy_keeps_multichar_symbols_whole(self):
        """Every yielded token is a whole inventory symbol, never a shredded
        fragment. The exact phoneme sequence depends on which optional Arabic
        diacritizer backend is installed, so the assertions are invariants over
        the inventory, not a hardcoded transcription: a bare length mark can
        only appear if a long-vowel symbol was split, and every token must be
        a real ShamiVITS symbol."""
        from scriptconv.phonemizers.shami import ShamiPhonemizer, SYMBOL_TO_ID
        p = ShamiPhonemizer()
        tokens = [t for sent in p.phonemize_lazy("\u0627\u0644\u0634\u062c\u0631\u0629 \u0643\u0628\u064a\u0631\u0629.", "ar")
                  for t in sent]
        self.assertNotIn("\u02d0", tokens)
        for t in tokens:
            self.assertIn(t, SYMBOL_TO_ID, f"{t!r} is not a ShamiVITS symbol")
        # If any multi-character symbol was produced, it survived whole.
        multi = [t for t in tokens if len(t) > 1 and not t.startswith("<")]
        for t in multi:
            self.assertIn(t, SYMBOL_TO_ID)

    def test_frontend_symbols_are_public(self):
        from scriptconv.phonemizers.shami import (
            TextFrontend,
            SYMBOL_TO_ID,
            ID_TO_SYMBOL,
            VOCAB_SIZE,
            get_default_frontend,
        )
        self.assertTrue(callable(TextFrontend))
        self.assertTrue(callable(get_default_frontend))
        self.assertIsInstance(SYMBOL_TO_ID, dict)
        self.assertTrue(SYMBOL_TO_ID)
        self.assertEqual(VOCAB_SIZE, len(ID_TO_SYMBOL))


class TestLicensingStubs(unittest.TestCase):
    def test_mantoq_wrapper_constructs_from_vendored_copy(self):
        cls = get_phonemizer_class(Phonemizer.MANTOQ)
        p = cls()
        out = p.phonemize_string("مرحبا", "ar")
        self.assertTrue(out)
        self.assertNotIn("_", out)

    def test_kog2p_wrapper_constructs_from_vendored_copy(self):
        cls = get_phonemizer_class(Phonemizer.KOG2PK)
        p = cls()
        self.assertTrue(callable(p.g2p))

    def test_encumbered_licenses_only_inside_quarantine(self):
        import pathlib, re
        root = pathlib.Path("scriptconv")
        offenders = []
        for f in root.rglob("*.py"):
            if "_vendored" in f.parts:
                continue
            head = f.read_text(errors="ignore")[:800]
            if re.search(r"@license:\s*GPL|Creative Commons Attribution-NonCommercial"
                         r"|creativecommons\.org/licenses/by-nc", head):
                offenders.append(str(f))
        self.assertEqual(offenders, [])

    def test_quarantine_carries_license_notices(self):
        import pathlib
        base = pathlib.Path("scriptconv/phonemizers/_vendored")
        self.assertTrue((base / "mantoq" / "LICENSE.md").is_file())
        self.assertTrue((base / "kog2p" / "LICENSE.md").is_file())

    def test_quarantine_not_imported_at_package_import(self):
        import subprocess, sys
        code = ("import sys, scriptconv, scriptconv.phonemizers; "
                "bad=[m for m in sys.modules if '_vendored' in m]; "
                "print(bad); sys.exit(1 if bad else 0)")
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()


class TestMantoqTokensToIpa(unittest.TestCase):
    def test_pretokenized_sequence_accepted(self):
        # the mantoq package's g2p returns a token LIST; joining is ambiguous
        # so mantoq_to_ipa consumes sequences directly
        from scriptconv.notation import mantoq_to_ipa
        tokens = ["m", "a", "r", "H", "a", "b", "a", "n", "aa",
                  "_+_", "b", "i", "l", "E", "aa", "l", "a", "m", "i"]
        out = mantoq_to_ipa(tokens)
        self.assertIn("ħ", out)
        self.assertIn(" ", out)
        self.assertNotIn("_", out)

    def test_pretokenized_dbl_geminate(self):
        from scriptconv.notation import mantoq_to_ipa
        self.assertEqual(mantoq_to_ipa(["b", "_dbl_", "a"]), "bːa")


class TestUnsupportedAlphabetIsAClearError(unittest.TestCase):
    """A wrapper asked for an alphabet it cannot emit must say so.

    ``get_phonemizer`` injects its own ``alphabet=`` default (IPA) into every
    constructor declaring the parameter, so the Japanese wrappers — which emit
    romanizations, never IPA — were hit by ordinary registry use and raised a
    bare ``AssertionError`` with an empty message.
    """

    def test_registry_default_raises_valueerror_naming_the_alphabets(self):
        from scriptconv.phonemizers.enums import Alphabet
        for member in (Phonemizer.OPENJTALK, Phonemizer.CUTLET,
                       Phonemizer.PYKAKASI):
            with self.subTest(phonemizer=member.value):
                try:
                    get_phonemizer(member)
                except ImportError:
                    self.skipTest(f"{member.value} backend not installed")
                except ValueError as e:
                    self.assertIn("ipa", str(e))
                    self.assertIn(Alphabet.HEPBURN.value, str(e))
                else:
                    self.fail("expected ValueError for an unemittable alphabet")

    def test_openjtalk_default_alphabet_is_one_it_can_emit(self):
        cls = get_phonemizer_class(Phonemizer.OPENJTALK)
        import inspect
        from scriptconv.phonemizers.enums import Alphabet
        default = inspect.signature(cls.__init__).parameters["alphabet"].default
        self.assertIn(default, (Alphabet.HEPBURN, Alphabet.KANA))
