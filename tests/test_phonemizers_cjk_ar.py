import sys
import unicodedata
import unittest

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
from scriptconv.phonemizers.enums import Alphabet
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


class TestG2PKOnPython313(unittest.TestCase):
    """scriptconv[ko] installs g2pk only below Python 3.13, because
    python-mecab-ko has wheels up to CPython 3.12 only. On 3.13 and later,
    pip builds python-mecab-ko from its sdist, which needs mecab-config
    from an installed MeCab-ko."""

    def _message(self, version_info):
        from unittest.mock import patch
        from scriptconv.phonemizers.ko import G2PKPhonemizer
        with patch.dict(sys.modules, {"g2pk": None}), \
                patch.object(sys, "version_info", version_info):
            with self.assertRaises(ImportError) as ctx:
                G2PKPhonemizer()
        return str(ctx.exception)

    def test_313_says_to_install_mecab_ko_first_not_the_extra(self):
        message = self._message((3, 13, 0, "final", 0))
        self.assertIn("mecab-config", message)
        self.assertIn("'pip install g2pk'", message)
        self.assertNotIn("Python 3.12 or older", message)
        self.assertNotIn("scriptconv[ko]", message)

    def test_312_names_the_extra(self):
        self.assertIn("scriptconv[ko]", self._message((3, 12, 0, "final", 0)))


class TestMisakiKoreanAlphabet(unittest.TestCase):
    """misaki's KOG2P writes the pronunciation in Hangul, not IPA.

    Wikipedia, "Korean phonology", revision 1374882945, section "Consonant
    assimilation": a velar stop becomes [ŋ] before a nasal stop, and
    한국말 is pronounced 한궁말. KOG2P writes conjoining jamo, which is the
    NFD form of the Hangul syllables.
    """

    def test_ipa_is_refused(self):
        with self.assertRaises(ValueError):
            get_phonemizer(Phonemizer.MISAKI_KO, Alphabet.IPA)

    @unittest.skipIf(sys.version_info >= (3, 13), "misaki declares Requires-Python <3.13")
    def test_output_is_the_pronunciation_in_hangul(self):
        from scriptconv.phonemizers.mul import MisakiKoPhonemizer
        p = MisakiKoPhonemizer()
        self.assertEqual(p.alphabet, Alphabet.HANGUL)
        self.assertEqual(p.phonemize_string("한국말", "ko"),
                         unicodedata.normalize("NFD", "한궁말"))


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


class TestPinyinToIpa(unittest.TestCase):
    """Chinese IPA against Wikipedia, "Standard Chinese phonology",
    revision 1384691172. Initials come from the consonant table, finals from
    the five vowel table (Duanmu 2000, p. 37), the nucleus of shi from the
    section "Syllabic consonants", and tone contours from the tone table
    (Chao 1968). pinyin_to_ipa writes affricates with no tie bar, so the
    table's [t͡ɕ] is written tɕ here. Tone 3 is not tested: Chao gives ˨˩˦
    and pinyin_to_ipa gives ˧˩˧, so the cited table cannot decide it."""

    def _phonemizer(self, retone):
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        p = PypinyinPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        p.retone = retone
        return p

    def test_tone_table_examples(self):
        # 巴 bā, 拔 bá, 爸 bà: b [p], a [a], tones ˥ 55, ˧˥ 35, ˥˩ 51
        out = self._phonemizer(False).phonemize_string("巴拔爸", "zh")
        self.assertEqual(out, "pa˥pa˧˥pa˥˩")

    def test_retroflex_and_alveolo_palatal(self):
        # 世 shì: sh [ʂ], -i [ɻ̩], tone ˥˩; 界 jiè: j [t͡ɕ], -ie [je], tone ˥˩
        out = self._phonemizer(False).phonemize_string("世界", "zh")
        self.assertEqual(out, "ʂɻ̩˥˩tɕje˥˩")

    def test_segments_survive_retone(self):
        # 你 nǐ: n [n], -i [i]; 好 hǎo: h [x], -ao [au̯]. Retone only swaps
        # tone letters for arrows, so the segments stay as the table gives.
        out = self._phonemizer(True).phonemize_string("你好", "zh")
        self.assertEqual(out.replace("↓", ""), "nixau̯")

    def test_punctuation_is_kept(self):
        # the docstring of to_ipa: a token with no letters or digits, such
        # as punctuation, is kept as it is
        out = self._phonemizer(False).phonemize_string("巴，爸", "zh")
        self.assertEqual(out, "pa˥，pa˥˩")


class TestPinyinUmlaut(unittest.TestCase):
    """ü after n and l, through each pinyin backend.

    Pinyin keeps the dots of ü only after n and l: 女 nǚ, 旅 lǚ, 略 lüè and
    虐 nüè (Wikipedia, "Pinyin", revision 1384755350, section "The ⟨ü⟩ sound").
    The backends spell it otherwise: g2pc and g2pM write ``u:`` as CC-CEDICT
    does, and xpinyin writes ``v`` and ``nue``.

    The expected IPA comes from Wikipedia, "Standard Chinese phonology",
    revision 1384691172. Initials come from the consonant table, and finals
    from the five vowel table: -ü [y], -üe [ɥe], -ou [ou̯], -ai [ai̯], -e [ɤ].
    儿 ér in 女儿 is an independent morpheme, which the section "Rhotic coda"
    gives as [aɚ̯] in China. Retone writes each tone of the tone table as an
    arrow: high →, rising ↗, dipping ↓, falling ↘, and none for neutral.
    """

    SENTENCE = "女儿去旅游了，忽略了虐待。"
    EXPECTED = "ny↓aɚ̯↗tɕʰy↘ly↓jou̯↗lɤ，xu→lɥe↘lɤnɥe↘tai̯↘。"

    def test_pypinyin(self):
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        p = PypinyinPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        self.assertEqual(p.phonemize_string(self.SENTENCE, "zh"), self.EXPECTED)

    def test_xpinyin(self):
        from scriptconv.phonemizers.zh import XpinyinPhonemizer
        p = XpinyinPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        self.assertEqual(p.phonemize_string(self.SENTENCE, "zh"), self.EXPECTED)

    def test_g2pm(self):
        from scriptconv.phonemizers.zh import G2pMPhonemizer
        p = G2pMPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        self.assertEqual(p.phonemize_string(self.SENTENCE, "zh"), self.EXPECTED)

    def test_g2pc(self):
        # g2pc needs pkuseg, whose sdist builds only when numpy, Cython and
        # setuptools are installed first and build isolation is off. The
        # test extra cannot do that, so g2pc is replaced by the output that
        # g2pc 0.9.9.3 gave for SENTENCE.
        # The pinyin is the fourth field of each word.
        import sys
        import types
        from unittest.mock import patch
        from scriptconv.phonemizers.zh import G2pCPhonemizer
        words = [("女儿", "n", "nu:3 er2", "nu:3 er2"), ("去", "v", "qu4", "qu4"),
                 ("旅游", "v", "lu:3 you2", "lu:3 you2"), ("了", "y", "le5", "le5"),
                 ("，", "w", "，", "，"), ("忽略", "v", "hu1 lu:e4", "hu1 lu:e4"),
                 ("了", "u", "le5", "le5"), ("虐待", "i", "nu:e4 dai4", "nu:e4 dai4"),
                 ("。", "w", "。", "。")]
        g2pc = types.ModuleType("g2pc")
        g2pc.G2pC = lambda: lambda text: words
        with patch.dict(sys.modules, {"g2pc": g2pc}):
            p = G2pCPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        self.assertEqual(p.phonemize_string(self.SENTENCE, "zh"), self.EXPECTED)

    def test_er_is_the_mainland_reading(self):
        # 二 èr: [aɚ̯] in China, section "Rhotic coda"; falling tone ↘
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        p = PypinyinPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        self.assertEqual(p.phonemize_string("二", "zh"), "aɚ̯↘")


class TestErhua(unittest.TestCase):
    """The erhua suffix 儿 and the independent morpheme 儿 ér.

    Wikipedia, "Standard Chinese phonology", revision 1384691172, section
    "Rhotic coda": the suffix is written "in pinyin as r" and "combines with
    the final sound of the syllable". The section "Syllables" writes that coda
    as ɚ̯. The independent morpheme ér is [aɚ̯] in China. Initials and finals
    come from the consonant table and the five vowel table: n [n], -a [a],
    d [t], -ou [ou̯], q [tɕʰ], -ü [y], -e [ɤ], z [ts], -i after z [ɹ̩], which
    retone writes ɨ. Retone writes the dipping tone ↓, the falling tone ↘, the
    rising tone ↗, and nothing for the neutral tone.
    """

    def test_g2pm_suffix_ends_the_syllable_before(self):
        # g2pM: 哪儿 na3 r5, 逗趣儿 dou4 qu4 r5, 哪儿呢？ na3 r5 ne5 ？
        from scriptconv.phonemizers.zh import G2pMPhonemizer
        p = G2pMPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        for text, expected in (("哪儿", "na↓ɚ̯"), ("逗趣儿", "tou̯↘tɕʰy↘ɚ̯"),
                               ("哪儿呢？", "na↓ɚ̯nɤ？")):
            with self.subTest(text=text):
                self.assertEqual(p.phonemize_string(text, "zh"), expected)

    def test_g2pm_suffix_in_strict_mode(self):
        from scriptconv.phonemizers.zh import G2pMPhonemizer
        p = G2pMPhonemizer(alphabet=Alphabet.IPA, jieba=False)
        p.strict = True
        self.assertEqual(p.phonemize_string("哪儿", "zh"), "na↓ɚ̯")

    def test_independent_er_is_a_full_syllable(self):
        # 儿子 érzi and 女儿 nǚ'ér; the backends give 子 different tones
        from scriptconv.phonemizers.zh import (G2pMPhonemizer, PypinyinPhonemizer,
                                               XpinyinPhonemizer)
        cases = {PypinyinPhonemizer: "aɚ̯↗tsɨ", XpinyinPhonemizer: "aɚ̯↗tsɨ↓",
                 G2pMPhonemizer: "aɚ̯↗tsɨ"}
        for cls, erzi in cases.items():
            p = cls(alphabet=Alphabet.IPA, jieba=False)
            with self.subTest(backend=cls.__name__):
                self.assertEqual(p.phonemize_string("儿子", "zh"), erzi)
                self.assertEqual(p.phonemize_string("女儿", "zh"), "ny↓aɚ̯↗")


class TestPinyinUnreadSyllable(unittest.TestCase):
    """A syllable that is not pinyin gives no IPA. It warns, or raises in strict mode."""

    def _phonemizer(self):
        from scriptconv.phonemizers.zh import PypinyinPhonemizer
        return PypinyinPhonemizer(alphabet=Alphabet.IPA, jieba=False)

    def test_warns_and_gives_no_latin(self):
        # 你 nǐ: n [n], -i [i]; 好 hǎo: h [x], -ao [au̯]; dipping tone ↓
        with self.assertLogs("scriptconv.phonemizers.zh", "WARNING") as logs:
            out = self._phonemizer().phonemize_string("你好Hello", "zh")
        self.assertEqual(out, "ni↓xau̯↓")
        self.assertIn("'Hello'", logs.output[0])

    def test_strict_raises(self):
        from scriptconv.phonemizers import UnreadTextError
        p = self._phonemizer()
        p.strict = True
        with self.assertRaises(UnreadTextError) as ctx:
            p.phonemize_string("你好Hello", "zh")
        self.assertEqual(ctx.exception.unread, ("Hello",))

    def test_frontend_strict_reaches_the_backend(self):
        from scriptconv.frontend import FrontendConfig, TextFrontend
        from scriptconv.phonemizers import UnreadTextError
        backend = self._phonemizer()
        frontend = TextFrontend(FrontendConfig(lang="zh", strict=True), backend)
        with self.assertRaises(UnreadTextError):
            frontend.phonemize("你好Hello")
        self.assertFalse(backend.strict)


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

    def test_g2pc_missing_dep_message_gives_the_install_that_works(self):
        # g2pc needs pkuseg, and PyPI has pkuseg wheels for CPython 3.5 to
        # 3.8 only. The pkuseg sdist builds when numpy, Cython and setuptools
        # are installed first and build isolation is off. An extra cannot
        # do that, so the message gives the two commands.
        import sys
        from unittest.mock import patch
        from scriptconv.phonemizers.zh import G2pCPhonemizer
        with patch.dict(sys.modules, {"g2pc": None}):
            with self.assertRaises(ImportError) as ctx:
                G2pCPhonemizer()
        message = str(ctx.exception)
        self.assertIn("pkuseg", message)
        self.assertIn("CPython 3.5 to 3.8", message)
        self.assertIn("'pip install numpy cython setuptools'", message)
        self.assertIn("'pip install --no-build-isolation g2pc'", message)
        self.assertNotIn("fails to build", message)
        self.assertNotIn("scriptconv[", message)

    def test_zh_phonemizers_extra_installs_numpy_for_g2pm(self):
        # g2pM 0.1.2.5 imports numpy in g2pM/g2pM.py and declares no
        # dependencies on PyPI, so the extra that installs g2pM must
        # also install numpy.
        import re
        import tomllib
        from pathlib import Path
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        extra = tomllib.loads(pyproject.read_text(encoding="utf-8"))[
            "project"]["optional-dependencies"]["zh-phonemizers"]
        names = {re.match(r"[A-Za-z0-9_.-]+", req).group(0).lower()
                 for req in extra}
        self.assertIn("g2pm", names)
        self.assertIn("numpy", names)

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
        # so halabi_to_ipa consumes sequences directly
        from scriptconv.notation import halabi_to_ipa
        tokens = ["m", "a", "r", "H", "a", "b", "a", "n", "aa",
                  "_+_", "b", "i", "l", "E", "aa", "l", "a", "m", "i"]
        out = halabi_to_ipa(tokens)
        self.assertIn("ħ", out)
        self.assertIn(" ", out)
        self.assertNotIn("_", out)

    def test_pretokenized_dbl_geminate(self):
        from scriptconv.notation import halabi_to_ipa
        self.assertEqual(halabi_to_ipa(["b", "_dbl_", "a"]), "bːa")


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
