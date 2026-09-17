"""Tests for the africa-g2p-backed phonemizer.

africa-g2p is an optional extra (``scriptconv[africa]``) and is in the
``test`` extra, so these tests call the real library and never skip.
"""
import sys
import unittest

from scriptconv.phonemizers import (
    Alphabet,
    Phonemizer,
    PHONEMIZER_REGISTRY,
    get_phonemizer,
    get_phonemizer_class,
)
from scriptconv.phonemizers.africa import AfricaG2PPhonemizer


class TestAfricaG2PExtra(unittest.TestCase):
    def test_registry_names_the_extra(self):
        module, cls, extra = PHONEMIZER_REGISTRY[Phonemizer.AFRICA_G2P]
        self.assertEqual(extra, "africa")

    def test_a_missing_library_names_the_extra(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "africa_g2p":
                raise ImportError("no module named africa_g2p")
            return real_import(name, *a, **k)

        from scriptconv.phonemizers import africa as mod
        builtins.__import__ = fake_import
        try:
            with self.assertRaises(ImportError) as ctx:
                mod._africa_g2p()
        finally:
            builtins.__import__ = real_import
        self.assertIn("scriptconv[africa]", str(ctx.exception))


class TestAfricaG2PPhonemizer(unittest.TestCase):
    def test_ipa_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kʷ a a b a")

    def test_native_grapheme_output(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.AFRICA_G2P)
        self.assertEqual(p.phonemize_string("Akwaaba", "twi"), "a kw a a b a")

    def test_ethiopic_g_is_the_ipa_letter(self):
        # africa-g2p v0.2.4 fixed the Ethiopic tables, which wrote ASCII g
        # (U+0067) where IPA uses ɡ (U+0261).
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("ግብር", "amh"), "ɡɨ bɨ rɨ")
        self.assertNotIn("g", p.phonemize_string("ገና", "amh"))

    def test_kabuverdianu_reads_letters_not_letter_names(self):
        # Before v0.2.4 the kea table read letter NAMES: kasa gave
        # 'ˈkapɐ a ˈɛs(i) a'.
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("kasa", "kea"), "k a s a")
        self.assertEqual(p.phonemize_string("djuntu", "kea"), "d͡ʒ u n t u")

    def test_engine_is_cached_per_language(self):
        p = AfricaG2PPhonemizer()
        first = p._engine("twi")
        self.assertIs(p._engine("twi"), first)

    def test_supported_langs_includes_twi(self):
        self.assertIn("twi", AfricaG2PPhonemizer.supported_langs())
        self.assertGreater(len(AfricaG2PPhonemizer.supported_langs()), 300)

    def test_region_suffixed_rule_files_resolve_by_their_own_name(self):
        # 11 rule files carry a region suffix instead of a bare ISO 639-3
        # code; each must be selectable by that name (T-2701).
        for code in ("hau-nigeria", "hau-niger", "dop-benin", "ngb-zaire",
                     "sag-congo", "sef-cote_d_ivoire", "snk-senegal"):
            self.assertEqual(AfricaG2PPhonemizer.get_lang(code), code)
            self.assertIn(code, AfricaG2PPhonemizer.supported_langs())

    def test_a_region_suffixed_code_phonemizes(self):
        p = AfricaG2PPhonemizer(alphabet=Alphabet.IPA)
        self.assertEqual(p.phonemize_string("ƙasa", "hau-nigeria"),
                         "kʼ a s a")

    def test_an_underscore_is_read_as_a_hyphen(self):
        self.assertEqual(AfricaG2PPhonemizer.get_lang("HAU_NIGERIA"),
                         "hau-nigeria")

    def test_a_bare_code_with_only_region_files_still_raises(self):
        # africa-g2p ships no bare 'hau'. Choosing a region for the caller
        # would be a claim this wrapper does not make.
        self.assertNotIn("hau", AfricaG2PPhonemizer.supported_langs())
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer.get_lang("hau")

    def test_get_lang_resolves_exact_iso_639_3_code(self):
        self.assertEqual(AfricaG2PPhonemizer.get_lang("twi"), "twi")
        # region subtag is stripped to the primary subtag before lookup
        self.assertEqual(AfricaG2PPhonemizer.get_lang("twi-GH"), "twi")

    def test_get_lang_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer.get_lang("zzz")

    def test_phonemize_string_rejects_unsupported_language(self):
        p = AfricaG2PPhonemizer()
        with self.assertRaises(ValueError):
            p.phonemize_string("hello", "zzz")

    def test_phonemize_returns_sentence_lists(self):
        p = AfricaG2PPhonemizer()
        out = p.phonemize("Akwaaba.", "twi")
        self.assertEqual(len(out), 1)
        self.assertTrue(all(isinstance(s, list) for s in out))

    def test_rejects_unsupported_alphabet(self):
        with self.assertRaises(ValueError):
            AfricaG2PPhonemizer(alphabet=Alphabet.VOSK)


class TestAfricaG2PRegistration(unittest.TestCase):
    def test_registered(self):
        self.assertIn(Phonemizer.AFRICA_G2P, PHONEMIZER_REGISTRY)

    def test_class_resolves_with_the_extra_installed(self):
        # africa-g2p is in the test extra, so it resolves here; without it,
        # resolution raises an ImportError naming scriptconv[africa]
        cls = get_phonemizer_class(Phonemizer.AFRICA_G2P)
        self.assertIs(cls, AfricaG2PPhonemizer)

    def test_get_phonemizer_builds_it(self):
        p = get_phonemizer(Phonemizer.AFRICA_G2P, Alphabet.IPA)
        self.assertIsInstance(p, AfricaG2PPhonemizer)

    def test_no_lang_default_registered(self):
        # design decision: africa-g2p is not made a default for any language,
        # including African languages that currently have no LANG_DEFAULTS
        # entry at all — see the PR body for the reasoning.
        from scriptconv.phonemizers import LANG_DEFAULTS
        for candidates in LANG_DEFAULTS.values():
            self.assertNotIn(Phonemizer.AFRICA_G2P, candidates)


if __name__ == "__main__":
    unittest.main()


class _FakeLoader:
    def __init__(self, tables):
        self._tables = tables

    def load_rules(self, code):
        return self._tables[code]


class _FakePkg:
    """An africa-g2p install in miniature, with a draft table in it.

    The `test` extra pins africa-g2p<0.3, and that line marks no table
    `llm-draft`, so the real library cannot exercise the filter. A caller can
    still install any africa-g2p they like - `ghana-g2p` requires
    `africa-g2p>=0.1.1` with no ceiling - so what a draft table does here is
    pinned against a stand-in that has one.
    """

    __version__ = "0.3.2-fake"

    def __init__(self, tables):
        self._tables = tables
        self.loader = _FakeLoader(tables)

    def available_languages(self):
        return list(self._tables)

    @staticmethod
    def AfricaPipeline(lang, output):  # noqa: N802 - mirrors the real name
        return _FakePipeline(lang, output)


class _FakePipeline:
    """The engine the stand-in install builds: one phoneme per letter.

    What a run returns does not matter here. What matters is that a run is
    reached at all, because that is how a refusal is told from an answer.
    """

    def __init__(self, lang, output):
        self.lang = lang
        self.output = output

    def run(self, text, sep=" "):
        return sep.join(text)


#: Three chart-sourced tables and two drafts, in the shape africa-g2p writes.
FAKE_TABLES = {
    "aaa": {"code": "aaa", "confidence": "omniglot"},
    "bbb": {"code": "bbb", "confidence": "high"},
    "ccc": {"code": "ccc", "confidence": "hand-verified"},
    "ddd": {"code": "ddd", "confidence": "llm-draft"},
    "eee": {"code": "eee", "confidence": "llm-draft"},
}


class TestDraftTablesAreNotOfferedUnasked(unittest.TestCase):
    """A ceiling in an extra cannot hold: `pip install scriptconv[ghana]`
    resolves africa-g2p through ghana-g2p's own unpinned `>=0.1.1` and lands
    on 0.3.2, where 352 of 750 tables say `llm-draft`. So the table's own
    `confidence` field is what decides, not the version."""

    def setUp(self):
        from scriptconv.phonemizers import africa as mod
        self.mod = mod
        self.real = mod._africa_g2p
        mod._africa_g2p = lambda: _FakePkg(FAKE_TABLES)
        mod._draft_codes.cache_clear()

    def tearDown(self):
        self.mod._africa_g2p = self.real
        self.mod._draft_codes.cache_clear()

    def test_a_draft_language_is_not_in_the_supported_list(self):
        langs = AfricaG2PPhonemizer.supported_langs()
        self.assertEqual(sorted(langs), ["aaa", "bbb", "ccc"])
        self.assertNotIn("ddd", langs)
        self.assertNotIn("eee", langs)

    def test_every_chart_sourced_table_is_still_offered(self):
        """The control: the filter must remove drafts and nothing else."""
        langs = AfricaG2PPhonemizer.supported_langs()
        for code in ("aaa", "bbb", "ccc"):
            self.assertIn(code, langs)

    def test_asking_for_a_draft_language_says_why(self):
        with self.assertRaises(ValueError) as ctx:
            AfricaG2PPhonemizer.get_lang("ddd")
        self.assertIn("llm-draft", str(ctx.exception))
        self.assertIn("allow_draft", str(ctx.exception))

    def test_an_unknown_language_still_reads_as_unsupported(self):
        """A control: a code the install has no table for must not be
        reported as a draft."""
        with self.assertRaises(ValueError) as ctx:
            AfricaG2PPhonemizer.get_lang("zzz")
        self.assertIn("unsupported", str(ctx.exception))
        self.assertNotIn("llm-draft", str(ctx.exception))

    def test_the_caller_can_ask_for_the_drafts(self):
        langs = AfricaG2PPhonemizer.supported_langs(allow_draft=True)
        self.assertEqual(sorted(langs), ["aaa", "bbb", "ccc", "ddd", "eee"])
        self.assertEqual(AfricaG2PPhonemizer.get_lang("ddd", allow_draft=True),
                         "ddd")

    def test_phonemize_string_refuses_a_draft_by_default(self):
        """The guard's user-facing path. `get_lang` and `supported_langs` are
        the query surface; `phonemize_string` is where a caller who never
        asked for a draft is actually protected, so the instance flag it
        passes is pinned here and not read off the source."""
        with self.assertRaises(ValueError) as ctx:
            AfricaG2PPhonemizer().phonemize_string("abc", "ddd")
        self.assertIn("llm-draft", str(ctx.exception))
        self.assertIn("allow_draft", str(ctx.exception))

    def test_phonemize_string_answers_when_the_caller_asked(self):
        """The control: the refusal above must come from the flag, not from a
        draft table being unusable."""
        phon = AfricaG2PPhonemizer(allow_draft=True)
        self.assertEqual(phon.phonemize_string("abc", "ddd"), "a b c")

    def test_a_table_that_cannot_be_read_is_not_called_a_draft(self):
        broken = dict(FAKE_TABLES)
        broken["fff"] = None

        class _Raising(_FakePkg):
            def __init__(self):
                super().__init__(broken)

            class loader:  # noqa: N801 - mirrors the module attribute
                @staticmethod
                def load_rules(code):
                    if code == "fff":
                        raise KeyError(code)
                    return broken[code]

        self.mod._africa_g2p = lambda: _Raising()
        self.mod._draft_codes.cache_clear()
        self.assertIn("fff", AfricaG2PPhonemizer.supported_langs())


class TestTheRealInstallIsUnfiltered(unittest.TestCase):
    """Against the pinned line the filter is a no-op, so nothing this repo
    ships today changes. Measured on africa-g2p 0.2.4: 400 tables, 0 drafts."""

    def test_the_pinned_line_loses_no_language(self):
        from scriptconv.phonemizers import africa as mod
        upstream = mod._africa_g2p().available_languages()
        offered = AfricaG2PPhonemizer.supported_langs()
        self.assertEqual(sorted(upstream), sorted(offered))
