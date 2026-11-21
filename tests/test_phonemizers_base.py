import unicodedata
import unittest
from unittest import mock

from scriptconv.phonemizers import (
    Alphabet,
    BasePhonemizer,
    GraphemePhonemizer,
    LANG_DEFAULTS,
    MissingLanguageError,
    PHONEMIZER_REGISTRY,
    Phonemizer,
    UnicodeCodepointPhonemizer,
    get_phonemizer,
    get_phonemizer_class,
    phonemizer_for_lang,
)
from scriptconv.phonemizers import base


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
        self.assertEqual(Phonemizer.GHANA_G2P.value, "ghana_g2p")
        self.assertEqual(Phonemizer.MATOUB_KAB.value, "matoub_kab")
        self.assertEqual(Phonemizer.DIZIONE.value, "dizione")
        self.assertEqual(Phonemizer.G2PW.value, "g2pw")
        self.assertEqual(len(list(Phonemizer)), 55)  # +HALABI, +IQRA, +GHANA_G2P, +PHONETISAURUS, +MATOUB_KAB, +DIZIONE, +G2PW, +F5TTS_CHAR, +F5TTS_PINYIN, +HEBREW_IPA, +OPENJTALK_PROSODY, +TLTK
        self.assertEqual(len(list(Alphabet)), 23)  # incl. HALABI, VOSK, AFRICA_G2P


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

    def test_match_lang_unsupported_tag_keeps_plain_valueerror(self):
        # a real, present-but-unsupported tag (e.g. Tetun) is a phonemizer
        # capability gap, not a missing-language config defect
        with self.assertRaises(ValueError) as cm:
            BasePhonemizer.match_lang("tet", ["en", "pt"])
        self.assertNotIsInstance(cm.exception, MissingLanguageError)
        self.assertIn("unsupported language code", str(cm.exception))

    def test_match_lang_rejects_a_tag_with_an_empty_subtag(self):
        # BCP 47 subtags are 1 to 8 characters, so these tags name no language
        for malformed in ("ar-", "AR-", "ar_", "-ar", "ar--EG"):
            with self.subTest(tag=malformed):
                with self.assertRaises(ValueError) as cm:
                    BasePhonemizer.match_lang(malformed, ["ar", "en"])
                self.assertIn("unsupported language code", str(cm.exception))

    def test_match_lang_missing_language_raises_distinct_error(self):
        for missing in (None, "", "und"):
            with self.assertRaises(MissingLanguageError) as cm:
                BasePhonemizer.match_lang(missing, ["eu"])
            # still a ValueError so existing `except ValueError` callers work
            self.assertIsInstance(cm.exception, ValueError)
            self.assertNotIn("unsupported language code", str(cm.exception))

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



class TestChunkTextDigitColon(unittest.TestCase):
    """A delimiter directly between two digits (a clock time, a score) is
    not a sentence-internal boundary — splitting "16:30" into "16" and "30"
    sends "... às 16" and "30 ..." to the per-chunk phonemizer/normalizer,
    which reads the time as two separate numbers instead of one."""

    def test_clock_time_stays_in_one_chunk(self):
        chunks = BasePhonemizer.chunk_text(
            "A reunião é às 16:30, não te esqueças.")
        self.assertEqual(chunks, [
            ("A reunião é às 16:30, não te esqueças.", ".", True),
        ])

    def test_score_splits_only_at_the_first_colon(self):
        chunks = BasePhonemizer.chunk_text(
            "Placar final: 3:2 para o Porto.")
        self.assertEqual(chunks, [
            ("Placar final", ":", False),
            ("3:2 para o Porto.", ".", True),
        ])

    def test_word_colon_still_splits(self):
        chunks = BasePhonemizer.chunk_text("Nota: fim.")
        self.assertEqual(chunks, [
            ("Nota", ":", False),
            ("fim.", ".", True),
        ])

    def test_semicolons_unaffected(self):
        chunks = BasePhonemizer.chunk_text("Um; dois; três.")
        self.assertEqual(chunks, [
            ("Um", ";", False),
            ("dois", ";", False),
            ("três.", ".", True),
        ])

    def test_digit_colon_space_still_splits(self):
        # a digit on only one side of the delimiter is not a digit:digit
        # token, so it keeps splitting as before.
        chunks = BasePhonemizer.chunk_text("12: pontos")
        self.assertEqual(chunks, [
            ("12", ":", False),
            ("pontos", ".", True),
        ])


class TestRemovePunctuationKeepsDigitInternal(unittest.TestCase):
    """remove_punctuation must keep a punctuation character sandwiched
    between two digits (clock times, decimals, ranges) — otherwise
    "16:30" reaches the phonemizer as "1630" and gets read as one large
    integer instead of an hour and a minute, matching chunk_text's
    digit:digit exemption above."""

    def test_clock_time_colon_kept(self):
        self.assertEqual(
            BasePhonemizer.remove_punctuation(
                "A reunião é às 16:30, não te esqueças."),
            "A reunião é às 16:30 não te esqueças",
        )

    def test_decimal_comma_kept(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("10,4"), "10,4")

    def test_decimal_dot_kept(self):
        self.assertEqual(
            BasePhonemizer.remove_punctuation("92.073"), "92.073")

    def test_range_hyphen_kept(self):
        self.assertEqual(
            BasePhonemizer.remove_punctuation("1139-1185"), "1139-1185")

    def test_word_colon_still_stripped(self):
        self.assertEqual(
            BasePhonemizer.remove_punctuation("Nota: fim."), "Nota fim")

    def test_ordinal_mark_still_stripped(self):
        # "3.º" — the dot follows a digit but precedes a letter (the
        # masculine ordinal indicator), so it is not digit:digit and is
        # stripped like any other punctuation, giving "3º".
        self.assertEqual(BasePhonemizer.remove_punctuation("3.º"), "3º")


class TestRemovePunctuationSeparatesWords(unittest.TestCase):
    """A "!" or "?" between two letters, with no space after it, is no
    clause break, but it still separates two words."""

    def test_mark_between_letters_becomes_a_space(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("Sim!Não! talvez"), "Sim Não talvez")
        self.assertEqual(BasePhonemizer.remove_punctuation("Isto?Aquilo"), "Isto Aquilo")

    def test_a_run_of_marks_becomes_one_space(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("Sim?!Não"), "Sim Não")

    def test_a_mark_that_the_table_reads_as_a_question_mark(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("نعم؟لا"), "نعم لا")
        self.assertEqual(BasePhonemizer.remove_punctuation("نعم!؟لا"), "نعم لا")

    def test_a_stress_mark_before_the_mark(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("да\u0301!нет"), "да\u0301 нет")

    def test_other_marks_still_join(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("U.S.A.! go"), "USA go")
        self.assertEqual(BasePhonemizer.remove_punctuation("Sim! Não"), "Sim Não")
        self.assertEqual(BasePhonemizer.remove_punctuation("Sim !Não"), "Sim Não")
        self.assertEqual(BasePhonemizer.remove_punctuation("!Sim um!"), "Sim um")
        self.assertEqual(BasePhonemizer.remove_punctuation("10,4 16:30"), "10,4 16:30")
        self.assertEqual(BasePhonemizer.remove_punctuation("你好！我们"), "你好我们")

    def test_a_long_run_of_marks_costs_linear_work(self):
        # the walk back over combining marks and the scan along the run of
        # marks each read a character a fixed number of times
        marks = 16000
        text = "a" + "\u0301" * marks + "!" * marks + "b"
        lookups = scans = 0

        def category(c):
            nonlocal lookups
            lookups += 1
            if lookups > 3 * len(text):
                raise AssertionError(f"over {3 * len(text)} category lookups for {len(text)} characters")
            return unicodedata.category(c)

        class ScannedMarks(frozenset):
            def __contains__(self, c):
                nonlocal scans
                scans += 1
                if scans > 3 * len(text):
                    raise AssertionError(f"over {3 * len(text)} mark lookups for {len(text)} characters")
                return super().__contains__(c)

        with mock.patch.object(base, "unicodedata", mock.Mock(category=category)), \
                mock.patch.object(base, "_SEPARATING_MARKS", ScannedMarks(base._SEPARATING_MARKS)):
            self.assertEqual(BasePhonemizer.remove_punctuation(text), "a" + "\u0301" * marks + " b")


class TestRemovePunctuationAfterStressMark(unittest.TestCase):
    """A stress mark (U+0301) after the vowel before a hyphen or apostrophe
    still leaves a letter on both sides, so the compound keeps its joint."""

    def test_hyphen_after_stressed_vowel_kept(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("когда\u0301-нибудь"),
                         "когда\u0301-нибудь")

    def test_hyphen_in_a_sentence_kept(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("Кто\u0301-то пришёл когда\u0301-нибудь."),
                         "Кто\u0301-то пришёл когда\u0301-нибудь")

    def test_apostrophe_after_stressed_vowel_kept(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("le\u0301'ami"), "le\u0301'ami")

    def test_hyphen_after_a_lone_mark_stripped(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("\u0301-нибудь"), "\u0301нибудь")

    def test_a_long_run_of_marks_costs_linear_work(self):
        marks = 16000
        text = "a" + "\u0301" * marks + "-b"
        lookups = 0

        def category(c):
            nonlocal lookups
            lookups += 1
            if lookups > 3 * len(text):
                raise AssertionError(f"over {3 * len(text)} category lookups for {len(text)} characters")
            return unicodedata.category(c)

        with mock.patch.object(base, "unicodedata", mock.Mock(category=category)):
            self.assertEqual(BasePhonemizer.remove_punctuation(text), text)


class TestGraphemeHyphen(unittest.TestCase):
    """A grapheme backend's symbols are the letters of the word, so a hyphen
    between two letters stays, as an apostrophe does in ``d'água``. A hyphen
    with a space next to it or at a word edge separates words."""

    def test_hyphen_between_letters_stays(self):
        for lang, text in (("ig", "Nna m na-arụ ọrụ."), ("st", "Maseru ke motse-moholo wa Lesotho.")):
            with self.subTest(lang=lang):
                self.assertEqual(GraphemePhonemizer().phonemize_string(text, lang), text.lower())

    def test_hyphen_after_a_stressed_vowel_stays(self):
        self.assertEqual(GraphemePhonemizer().phonemize_string("когда\u0301-нибудь", "ru"),
                         "когда\u0301-нибудь")

    def test_hyphen_through_the_frontend_in_both_modes(self):
        from scriptconv.frontend import FrontendConfig, TextFrontend
        for keep, end in ((False, ""), (True, ".")):
            with self.subTest(keep_punctuation=keep):
                frontend = TextFrontend(FrontendConfig("st", keep_punctuation=keep), GraphemePhonemizer())
                self.assertEqual(frontend.phonemize("Maseru ke motse-moholo wa Lesotho."),
                                 [list("maseru ke motse-moholo wa lesotho" + end)])

    def test_hyphen_that_is_not_inside_a_word_is_a_space(self):
        g = GraphemePhonemizer()
        self.assertEqual(g.phonemize_string("kum - ayibo", "xh"), "kum ayibo")
        self.assertEqual(g.phonemize_string("pre- and post", "en"), "pre and post")
        self.assertEqual(g.phonemize_string("-kum ayibo-", "xh"), "kum ayibo")
        self.assertEqual(g.phonemize_string("-kum", "xh"), "kum")
        self.assertEqual(g.phonemize_string("10-20", "en"), "10 20")


class TestRemovePunctuationHyphensAndDashes(unittest.TestCase):
    """tts-punctuation: "A hyphen between two letters is part of the word",
    and "A hyphen with a space next to it, or at a word edge, is no part of a
    word: it gives no symbol, and a space separates the two words." A dash is
    no letter of a word either. The hyphen forms are the characters that
    Unicode names HYPHEN, NON-BREAKING HYPHEN, SMALL HYPHEN-MINUS and
    FULLWIDTH HYPHEN-MINUS."""

    def test_every_form_of_the_hyphen_between_two_letters_is_a_hyphen(self):
        for hyphen in "‐‑﹣－":
            with self.subTest(hyphen=hex(ord(hyphen))):
                self.assertEqual(BasePhonemizer.remove_punctuation(f"guarda{hyphen}chuva."), "guarda-chuva")

    def test_a_dash_between_two_letters_is_a_space(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("Lisboa–Porto."), "Lisboa Porto")
        self.assertEqual(BasePhonemizer.remove_punctuation("sim—não"), "sim não")

    def test_a_hyphen_between_a_letter_and_a_digit_is_a_space(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("COVID-19 chegou."), "COVID 19 chegou")
        self.assertEqual(BasePhonemizer.remove_punctuation("3-D"), "3 D")
        self.assertEqual(BasePhonemizer.remove_punctuation("COVID–19"), "COVID 19")

    def test_a_mark_between_two_digits_stays(self):
        self.assertEqual(BasePhonemizer.remove_punctuation("1139-1185"), "1139-1185")
        self.assertEqual(BasePhonemizer.remove_punctuation("1139–1185"), "1139–1185")

    def test_the_grapheme_backend_reads_the_hyphen_at_a_digit_as_a_space(self):
        self.assertEqual(GraphemePhonemizer().phonemize_to_list("COVID-19", "en"), list("covid 19"))
