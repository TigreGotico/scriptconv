import unittest

from scriptconv.phonemizers import (
    Alphabet,
    BasePhonemizer,
    GraphemePhonemizer,
    LANG_DEFAULTS,
    PHONEMIZER_REGISTRY,
    Phonemizer,
    UnicodeCodepointPhonemizer,
    get_phonemizer,
    get_phonemizer_class,
    phonemizer_for_lang,
)


class TestEnums(unittest.TestCase):
    def test_wire_format_values_present(self):
        # spot-check the string values that voice configs store
        self.assertEqual(Phonemizer.ESPEAK.value, "espeak")
        self.assertEqual(Phonemizer.ARBTOK.value, "arbtok")
        self.assertEqual(Phonemizer.MIRANDESE.value, "mwl_phonemizer")
        self.assertEqual(Phonemizer.KOG2PK.value, "kog2p")
        self.assertEqual(Phonemizer.VOSK.value, "vosk")
        self.assertEqual(Alphabet.XSAMPA.value, "x-sampa")
        self.assertEqual(Alphabet.VOSK.value, "vosk")
        self.assertEqual(len(list(Phonemizer)), 42)
        self.assertEqual(len(list(Alphabet)), 22)  # incl. MANTOQ, VOSK


class TestRegistryCompleteness(unittest.TestCase):
    def test_every_member_registered(self):
        for member in Phonemizer:
            self.assertIn(member, PHONEMIZER_REGISTRY, member)

    def test_every_member_resolves_or_raises_named_importerror(self):
        """No silent gaps: each member yields a class or an ImportError whose
        message names the extra to install."""
        for member in Phonemizer:
            try:
                cls = get_phonemizer_class(member)
            except ImportError as e:
                self.assertIn("scriptconv[", str(e), member)
            else:
                self.assertTrue(issubclass(cls, BasePhonemizer), member)

    def test_unicode_and_graphemes_need_no_extra(self):
        self.assertTrue(issubclass(get_phonemizer_class(Phonemizer.UNICODE),
                                   UnicodeCodepointPhonemizer))
        self.assertTrue(issubclass(get_phonemizer_class(Phonemizer.GRAPHEMES),
                                   GraphemePhonemizer))


class TestBaseContract(unittest.TestCase):
    def test_phonemize_returns_sentence_lists(self):
        g = GraphemePhonemizer()
        out = g.phonemize("First one. Second one!", "en")
        self.assertEqual(len(out), 2)
        self.assertTrue(all(isinstance(s, list) for s in out))

    def test_lazy_equals_eager(self):
        g = GraphemePhonemizer()
        text = "One. Two? Three!"
        self.assertEqual(list(g.phonemize_lazy(text, "en")),
                         g.phonemize(text, "en"))

    def test_empty_text_yields_nothing(self):
        self.assertEqual(GraphemePhonemizer().phonemize("", "en"), [])

    def test_normalizer_hook_injected_at_constructor(self):
        norm = lambda t, l: t.replace("2", "two")
        g = GraphemePhonemizer(normalizer=norm)
        self.assertIn("two", "".join(g.phonemize("2 cats", "en")[0]))

    def test_no_normalization_by_default(self):
        g = GraphemePhonemizer()
        self.assertIn("2", "".join(g.phonemize("2 cats", "en")[0]))

    def test_match_lang_rejects_unsupported(self):
        with self.assertRaises(ValueError):
            BasePhonemizer.match_lang("zz-XX", ["en", "pt"])
        self.assertEqual(BasePhonemizer.match_lang("en-US", ["en", "pt"]), "en")

    def test_unicode_codepoint_nfd(self):
        u = UnicodeCodepointPhonemizer()
        self.assertEqual(len(u.phonemize_string("ã", "pt")), 2)  # a + combining


class TestLangDefaults(unittest.TestCase):
    def test_arabic_defaults_to_arbtok(self):
        # hard org rule: Arabic IPA via arbtok — resolving may raise
        # ImportError (extra not installed) but must NEVER fall back silently
        self.assertEqual(LANG_DEFAULTS["ar"], (Phonemizer.ARBTOK,))

    def test_cotovia_only_for_cotovia_alphabet(self):
        # requesting IPA must never yield Cotovía (it emits its own notation);
        # the in-house chain falls through to orthography2ipa (or espeak)
        gl_ipa = phonemizer_for_lang("gl", alphabet=Alphabet.IPA)
        self.assertIn(type(gl_ipa).__name__,
                      ("Orthography2IPAPhonemizer", "EspeakPhonemizer"))
        self.assertNotEqual(type(gl_ipa).__name__, "CotoviaPhonemizer")
        gl_ctv = phonemizer_for_lang("gl", alphabet=Alphabet.COTOVIA)
        self.assertEqual(type(gl_ctv).__name__, "CotoviaPhonemizer")

    def test_fallback_prefers_o2i_then_espeak(self):
        # in-house first: orthography2ipa is the usual default when it has a
        # spec for the language; espeak only as last resort
        from unittest import mock
        import scriptconv.phonemizers.registry as reg
        with mock.patch.object(reg, "_o2i_supports", return_value=True):
            with mock.patch.object(reg, "get_phonemizer") as gp:
                reg.phonemizer_for_lang("de-DE")
                self.assertEqual(gp.call_args[0][0], Phonemizer.ORTHOGRAPHY2IPA)
        with mock.patch.object(reg, "_o2i_supports", return_value=False):
            de = reg.phonemizer_for_lang("de-DE")
            self.assertEqual(type(de).__name__, "EspeakPhonemizer")

    def test_arabic_never_falls_through(self):
        # hard org rule: Arabic IPA only via arbtok — with arbtok ineligible
        # (wrong alphabet), the resolver raises instead of degrading to
        # o2i/espeak
        with self.assertRaises((ValueError, ImportError)):
            phonemizer_for_lang("ar", alphabet=Alphabet.ARPA)

    def test_override_wins(self):
        g = phonemizer_for_lang("de", override=Phonemizer.GRAPHEMES)
        self.assertIsInstance(g, GraphemePhonemizer)

    def test_normalizer_kwarg_threads_through_factory(self):
        norm = lambda t, l: t.upper()
        g = get_phonemizer(Phonemizer.GRAPHEMES, normalizer=norm)
        self.assertIs(g.normalizer, norm)

    def test_normalizer_set_on_wrapper_with_custom_init(self):
        # EspeakPhonemizer.__init__ does not accept normalizer= — the factory
        # sets the attribute after construction
        norm = lambda t, l: t
        e = get_phonemizer(Phonemizer.ESPEAK, normalizer=norm)
        self.assertIs(e.normalizer, norm)


class TestByT5NoNetwork(unittest.TestCase):
    def test_missing_model_raises_not_downloads(self):
        from scriptconv.phonemizers.mul import ByT5Phonemizer
        with self.assertRaises(ValueError) as ctx:
            ByT5Phonemizer(model=None)
        self.assertIn("never downloads", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class TestFacadeAndGraph(unittest.TestCase):
    def test_phonemize_facade(self):
        from scriptconv.phonemizers import phonemize
        out = phonemize("hola", "es", override=Phonemizer.GRAPHEMES)
        self.assertEqual(out, "hola")

    def test_register_is_opt_in_default_graph_untouched(self):
        from scriptconv.graph import DEFAULT_GRAPH
        from scriptconv import phonemizers
        self.assertNotIn("text", DEFAULT_GRAPH.nodes)
        g = DEFAULT_GRAPH.extend(phonemizers.register)
        self.assertIn("text", g.nodes)
        self.assertNotIn("text", DEFAULT_GRAPH.nodes)

    def test_graph_edge_dispatches_with_override(self):
        from scriptconv.graph import DEFAULT_GRAPH
        from scriptconv import phonemizers
        g = DEFAULT_GRAPH.extend(phonemizers.register)
        out = g.convert("abc", "text", "ipa", lang="en",
                        override=Phonemizer.GRAPHEMES)
        self.assertEqual(out, "abc")

    def test_graph_edge_chains_to_arpa(self):
        from scriptconv.graph import DEFAULT_GRAPH
        from scriptconv import phonemizers
        g = DEFAULT_GRAPH.extend(phonemizers.register)
        self.assertTrue(g.can_convert("text", "arpa"))


class TestModelForwarding(unittest.TestCase):
    def test_model_forwards_to_variant_param(self):
        from unittest import mock
        import scriptconv.phonemizers.registry as reg

        seen = {}

        class FakeEngineBackend(BasePhonemizer):
            def __init__(self, engine=None, alphabet=Alphabet.IPA):
                seen["engine"] = engine
                super().__init__(alphabet)

            def phonemize_string(self, text, lang):
                return text

        with mock.patch.object(reg, "get_phonemizer_class",
                               return_value=FakeEngineBackend):
            reg.get_phonemizer(Phonemizer.AHOTTS, model="classic")
        self.assertEqual(seen["engine"], "classic")

    def test_model_none_forwards_nothing(self):
        g = get_phonemizer(Phonemizer.GRAPHEMES, model=None)
        self.assertIsInstance(g, GraphemePhonemizer)


