"""``TextFrontend``: the stage order, inline blocks, owned stages and the failure policy.

Each expected value is worked out by hand from the rule it tests. The fake
backends return the characters of the text they receive, so the text that
reached a backend is the expected phonemes.
"""
import itertools
import logging
import re
import sys
import time

import pytest

from scriptconv import frontend as frontend_module
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend, spoken_normalizer
from scriptconv.graph import ConversionGraph
from scriptconv.phonemizers import (
    Alphabet,
    BasePhonemizer,
    Phonemizer,
    PhonemizerIdentity,
    StageError,
    UnreadTextError,
    UnsupportedLanguageError,
    get_phonemizer,
    phonemize,
)
from scriptconv.phonemizers.mul import EspeakPhonemizer
from scriptconv.version import VERSION_STR


class Echo(BasePhonemizer):
    """Phonemes are the characters of the text. Each text read is recorded with its language."""

    def __init__(self):
        super().__init__(Alphabet.IPA)
        self.read = []

    def phonemize_string(self, text, lang):
        self.read.append((text, lang))
        return text


class Owner(Echo):
    owned_stages = frozenset({"diacritize"})


class NormalizeOwner(Echo):
    owned_stages = frozenset({"normalize"})


class Mute(Echo):
    def phonemize_string(self, text, lang):
        self.read.append((text, lang))
        return ""


class Recorder:
    """Stage functions that log their input and mark their output."""

    def __init__(self, monkeypatch):
        self.log = []
        monkeypatch.setattr(frontend_module, "diacritize", self.diacritize)

    def normalize(self, text, lang):
        self.log.append(("normalize", text, lang))
        return "n" + text

    def casing(self, text):
        self.log.append(("casing", text))
        return text.upper()

    def diacritize(self, text, lang, diacritizer_model=None):
        self.log.append(("diacritize", text, lang, diacritizer_model))
        return "d" + text

    def stage_names(self):
        return [entry[0] for entry in self.log]


def build(backend, lang="xx", **config):
    return TextFrontend(FrontendConfig(lang, **config), backend)


class Scanned(str):
    """A text that counts the characters its ``find`` calls read."""

    def __new__(cls, text):
        scanned = super().__new__(cls, text)
        scanned.read = 0
        return scanned

    def find(self, sub, start=0, end=None):
        end = len(self) if end is None else min(end, len(self))
        found = super().find(sub, start, end)
        self.read += max(0, (end if found == -1 else found + len(sub)) - start)
        return found


class TestStageOrder:
    def test_normalise_then_casing_then_diacritize_then_backend(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, normalizer=stages.normalize,
                         stages=Stages(diacritize=True, casing=stages.casing))
        assert frontend.phonemize("ab") == [list("dNAB")]
        assert stages.log == [("normalize", "ab", "xx"), ("casing", "nab"),
                              ("diacritize", "NAB", "xx", None)]
        assert backend.read == [("dNAB", "xx")]

    def test_each_sentence_runs_the_stages_on_its_own(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab. cd.") == [list("dnab"), list("dncd")]
        assert stages.log == [("normalize", "ab.", "xx"), ("diacritize", "nab.", "xx", None),
                              ("normalize", "cd.", "xx"), ("diacritize", "ncd.", "xx", None)]

    def test_flat_takes_the_text_whole_in_the_same_order(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, normalizer=stages.normalize,
                         stages=Stages(diacritize=True, casing=stages.casing))
        assert frontend.phonemize_flat("ab. cd.") == list("dNAB. CD.")
        assert stages.stage_names() == ["normalize", "casing", "diacritize"]
        assert backend.read == [("dNAB. CD.", "xx")]

    def test_prepare_runs_the_same_stages_as_phonemize(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.prepare("ab. cd.") == "dnab. cd."
        assert stages.stage_names() == ["normalize", "diacritize"]
        assert frontend.prepare("ab", Stages(normalize=False)) == "dab"

    def test_prepare_with_no_stages_normalises(self):
        hook = spoken_normalizer()
        frontend = build(Echo(), "en", normalizer=hook, stages=Stages(diacritize=False))
        text = "I have 5 cats and 20% of them sleep."
        expected = hook(text, "en")
        assert expected != text
        assert frontend.prepare(text) == expected

    def test_a_call_can_skip_the_hook(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize)
        assert frontend.phonemize("ab", Stages(normalize=False, diacritize=False)) == [list("ab")]
        assert stages.log == []


class TestInlineBlocks:
    def test_no_stage_reads_a_block(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=lambda text, lang: text.upper(),
                         stages=Stages(diacritize=True))
        assert frontend.phonemize("ab [[xy]] cd. ef.") == [
            list("dAB") + [" ", "x", "y", " "], list("d CD"), list("dEF")]
        assert all("xy" not in entry[1] and "[" not in entry[1] for entry in stages.log)

    def test_a_block_joins_the_sentence_before_it(self):
        frontend = build(Echo(), stages=Stages(diacritize=False))
        assert frontend.phonemize("ab. cd [[xy]]ef") == [
            list("ab"), list("cd") + [" ", "x", "y"], list("ef")]

    def test_a_leading_block_starts_the_first_sentence(self):
        frontend = build(Echo(), stages=Stages(diacritize=False))
        assert frontend.phonemize("[[ x y ]] ab") == [["x", " ", "y", " "], list("ab")]

    def test_flat_keeps_the_block_symbols_in_place(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize, stages=Stages(diacritize=False))
        assert frontend.phonemize_flat("ab [[xy]] cd") == (
            list("nab ") + [" ", "x", "y", " "] + list("n cd"))
        assert [entry[1] for entry in stages.log] == ["ab ", " cd"]

    def test_the_split_matches_the_block_pattern(self):
        # Every string of up to 7 characters over the symbols that matter.
        pattern = re.compile(r"(\[\[.*?\]\])")
        checked = 0
        for size in range(8):
            for characters in itertools.product("[]a \n", repeat=size):
                text = "".join(characters)
                assert frontend_module._split_blocks(text) == pattern.split(text), text
                checked += 1
        assert checked == sum(5 ** size for size in range(8))

    # The cost of a split is the number of characters its find calls read.
    # A linear scan reads each character a fixed number of times, at most
    # twice here. A quadratic one reads the rest of the line again at each [[,
    # thousands of times on these texts. A scan that reads the text without
    # find is not counted, so it reads less than the text and fails too.

    @pytest.mark.parametrize("path", ["phonemize_lazy", "phonemize", "phonemize_flat", "prepare"])
    def test_unclosed_blocks_cost_linear_time(self, path, monkeypatch):
        split = frontend_module._split_blocks
        costs = []

        def counted_split(text):
            scanned = Scanned(text)
            parts = split(scanned)
            costs.append((len(scanned), scanned.read))
            return parts

        monkeypatch.setattr(frontend_module, "_split_blocks", counted_split)
        run = getattr(build(Echo(), stages=Stages(diacritize=False)), path)
        list(run("a [[ " * 10000))
        assert len(costs) == 1, costs
        size, read = costs[0]
        assert size <= read <= 3 * size, (size, read)

    @pytest.mark.parametrize("unit", ["a [[ ", "[[a]] b ", "a [[ \n", "[[a\n]] "])
    def test_the_split_costs_linear_time(self, unit):
        text = Scanned(unit * 10000)
        frontend_module._split_blocks(text)
        assert len(text) <= text.read <= 3 * len(text), text.read

    # The counter sees only find. Time sees every way to read the text. The
    # real scan of a million characters takes about a millisecond, and a
    # quadratic one takes minutes, so the bound and the timeout leave a wide
    # margin on both sides.

    @pytest.mark.timeout(20)
    @pytest.mark.parametrize("unit", ["a [[ ", "[[a] "])
    def test_a_long_unclosed_text_splits_in_well_under_two_seconds(self, unit):
        text = unit * 200000
        start = time.perf_counter()
        frontend_module._split_blocks(text)
        assert time.perf_counter() - start < 2

    def test_prepare_keeps_the_block_as_written(self, monkeypatch):
        Recorder(monkeypatch)
        frontend = build(Echo(), stages=Stages(diacritize=True))
        assert frontend.prepare("ab [[xy]] cd") == "dab [[xy]] dcd"

    # A hook that joins words with single spaces drops the space at each edge
    # of the text it reads. The space next to a block is part of the text.

    @staticmethod
    def edge_stripping_hook(text, lang):
        return " ".join(text.upper().split())

    @pytest.mark.parametrize("text, pieces", [
        ("  mama\t[[abc]]\nana  ", ["  ", "mama", "\t[[abc]]\n", "ana", "  "]),
        ("[[a]] [[b]]", ["", "", "[[a]] [[b]]", "", ""]),
        (" x  y [[a]]", [" ", "x  y", " [[a]]", "", ""]),
    ])
    def test_prepare_keeps_the_whitespace_at_the_edges_of_each_piece(self, text, pieces):
        frontend = build(Echo(), normalizer=self.edge_stripping_hook, stages=Stages(diacritize=False))
        lead, first, middle, last, trail = pieces
        expected = (lead + self.edge_stripping_hook(first, "xx") + middle
                    + self.edge_stripping_hook(last, "xx") + trail)
        assert frontend.prepare(text, Stages()) == expected

    def test_prepare_mama_abc_ana_keeps_both_spaces(self):
        frontend = build(Echo(), normalizer=self.edge_stripping_hook, stages=Stages(diacritize=False))
        assert frontend.prepare("mama [[abc]] ana", Stages()) == "MAMA [[abc]] ANA"


class TestOwnedStages:
    def test_an_owner_never_gets_a_second_diacritizer(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Owner()
        frontend = build(backend, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab") == [list("ab")]
        assert frontend.phonemize_flat("ab") == list("ab")
        assert frontend.prepare("ab") == "ab"
        assert stages.log == []

    def test_diacritize_false_adds_no_diacritizer_and_the_owner_reads_the_text(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Owner()
        frontend = build(backend, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab", Stages(diacritize=False)) == [list("ab")]
        assert backend.read == [("ab", "xx")]
        assert stages.log == []

    def test_an_owner_still_gets_the_normalisation_hook(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Owner(), normalizer=stages.normalize)
        assert frontend.phonemize("ab") == [list("nab")]
        assert stages.stage_names() == ["normalize"]

    @pytest.mark.parametrize("path", ["phonemize_lazy", "phonemize", "phonemize_flat", "prepare"])
    @pytest.mark.parametrize("call", [None, Stages(), Stages(normalize=True)])
    def test_an_owner_of_normalize_never_gets_the_hook(self, monkeypatch, path, call):
        stages = Recorder(monkeypatch)
        backend = NormalizeOwner()
        frontend = build(backend, normalizer=stages.normalize, stages=Stages(diacritize=False))
        result = getattr(frontend, path)("ab. cd [[xy]] ef", call)
        if path == "prepare":
            assert result == "ab. cd [[xy]] ef"
        else:
            list(result)
            assert backend.read and all("n" not in text for text, _ in backend.read)
        assert stages.log == []

    def test_an_owner_of_normalize_still_gets_the_diacritizer(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(NormalizeOwner(), normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab") == [list("dab")]
        assert frontend.prepare("ab") == "dab"
        assert stages.stage_names() == ["diacritize", "diacritize"]

    def test_an_owner_of_both_stages_reads_the_text_as_given(self, monkeypatch):
        class BothOwner(Echo):
            owned_stages = frozenset({"normalize", "diacritize"})

        stages = Recorder(monkeypatch)
        frontend = build(BothOwner(), normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab") == [list("ab")]
        assert frontend.phonemize_flat("ab") == list("ab")
        assert frontend.prepare("ab") == "ab"
        assert stages.log == []

    def test_a_backend_that_owns_nothing_gets_the_diacritizer(self, monkeypatch):
        stages = Recorder(monkeypatch)
        assert build(Echo(), stages=Stages(diacritize=True)).phonemize("ab") == [list("dab")]
        assert stages.stage_names() == ["diacritize"]


class TestPerCallStages:
    def test_the_call_wins_then_the_frontend(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), stages=Stages(diacritize=True, diacritizer_model="own"))
        assert frontend.phonemize("ab", Stages(diacritize=False)) == [list("ab")]
        assert frontend.phonemize("ab", Stages()) == [list("dab")]
        assert frontend.phonemize("ab", Stages(diacritizer_model="call")) == [list("dab")]
        assert [entry[3] for entry in stages.log] == ["own", "call"]

    def test_a_reference_language_reaches_every_stage_and_the_backend(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, "pt-PT", normalizer=stages.normalize, stages=Stages(diacritize=True))
        frontend.phonemize("ab", Stages(lang="es-ES"))
        assert stages.log == [("normalize", "ab", "es-ES"), ("diacritize", "nab", "es-ES", None)]
        assert backend.read == [("dnab", "es-ES")]

    def test_the_call_language_wins_then_the_frontend_language(self):
        backend = Echo()
        frontend = build(backend, "pt-PT", stages=Stages(diacritize=False, lang="es-ES"))
        frontend.phonemize("ab", Stages(lang="fr-FR"))
        frontend.phonemize("ab", Stages())
        assert backend.read == [("ab", "fr-FR"), ("ab", "es-ES")]

    def test_the_call_casing_wins_over_the_frontend_casing(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), stages=Stages(diacritize=False, casing=stages.casing))
        assert frontend.phonemize("aB", Stages(casing=str.lower)) == [list("ab")]

    def test_the_frontend_normalize_holds_when_the_call_leaves_it_unset(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize,
                         stages=Stages(normalize=False, diacritize=False))
        assert frontend.phonemize("ab", Stages(diacritize=False)) == [list("ab")]
        assert frontend.phonemize("ab", Stages(lang="es-ES")) == [list("ab")]
        assert frontend.phonemize("ab", Stages(normalize=True)) == [list("nab")]
        assert stages.stage_names() == ["normalize"]

    def test_the_hook_runs_when_neither_sets_normalize(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize, stages=Stages(diacritize=False))
        assert frontend.phonemize("ab", Stages(lang="es-ES")) == [list("nab")]
        assert frontend.phonemize("ab", Stages(normalize=False)) == [list("ab")]

    def test_the_frontend_casing_holds_when_the_call_sets_none(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), stages=Stages(diacritize=False, casing=stages.casing))
        assert frontend.phonemize("ab", Stages()) == [list("AB")]


class TestDiacritizeDefault:
    # Arabic, with any region, and the individual Arabic languages in Arabic
    # script. arl is Arabela, arn Mapudungun and arg Aragonese; acy is Arabic in
    # Latin script.
    @pytest.mark.parametrize("lang", ["ar", "ar-EG", "apc", "arz"])
    def test_arabic_diacritizes(self, monkeypatch, lang):
        stages = Recorder(monkeypatch)
        build(Echo(), lang).phonemize("ab")
        assert stages.stage_names() == ["diacritize"]

    @pytest.mark.parametrize("lang", ["arl", "arn", "arg", "ar-Latn", "acy", "en", "he", "ru"])
    def test_other_languages_do_not(self, monkeypatch, lang):
        stages = Recorder(monkeypatch)
        build(Echo(), lang).phonemize("ab")
        assert stages.log == []


class TestFailurePolicy:
    @staticmethod
    def broken(text, lang):
        raise RuntimeError("boom")

    def test_a_failed_stage_warns_and_continues_with_its_input(self, caplog):
        frontend = build(Echo(), normalizer=self.broken, stages=Stages(diacritize=False))
        with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
            assert frontend.phonemize("ab") == [list("ab")]
        assert "normalize failed" in caplog.text and "boom" in caplog.text

    def test_strict_raises_stage_error(self):
        frontend = build(Echo(), normalizer=self.broken, stages=Stages(diacritize=False), strict=True)
        with pytest.raises(StageError, match="normalize failed") as raised:
            frontend.phonemize("ab")
        assert isinstance(raised.value.__cause__, RuntimeError)

    def test_strict_raises_for_a_failed_diacritizer(self, monkeypatch):
        def missing(text, lang, diacritizer_model=None):
            raise ImportError("no diacritizer")
        monkeypatch.setattr(frontend_module, "diacritize", missing)
        frontend = build(Echo(), stages=Stages(diacritize=True), strict=True)
        with pytest.raises(StageError, match="diacritize failed"):
            frontend.prepare("ab")

    def test_a_missing_diacritizer_warns_without_strict(self, monkeypatch, caplog):
        def missing(text, lang, diacritizer_model=None):
            raise ImportError("no diacritizer")
        monkeypatch.setattr(frontend_module, "diacritize", missing)
        frontend = build(Echo(), stages=Stages(diacritize=True))
        with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
            assert frontend.phonemize("ab") == [list("ab")]
        assert "diacritize failed" in caplog.text

    def test_strict_refuses_a_missing_extra_at_construction(self, monkeypatch):
        monkeypatch.setitem(frontend_module._DIACRITIZER_PACKAGES, "he",
                            ("scriptconv_test_no_such_package", "he"))
        with pytest.raises(ImportError, match=r"scriptconv\[he\]"):
            build(Echo(), "he", stages=Stages(diacritize=True), strict=True)
        build(Echo(), "he", stages=Stages(diacritize=True))
        build(Echo(), "he", stages=Stages(diacritize=False), strict=True)
        build(Owner(), "he", stages=Stages(diacritize=True), strict=True)

    def test_unread_text_warns(self, caplog):
        frontend = build(Mute(), stages=Stages(diacritize=False))
        with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
            assert frontend.phonemize("ab. 12. ...") == []
        assert caplog.text.count("no phonemes") == 2

    def test_strict_raises_unread_text_error(self):
        frontend = build(Mute(), stages=Stages(diacritize=False), strict=True)
        with pytest.raises(UnreadTextError) as raised:
            frontend.phonemize("... ab.")
        assert raised.value.unread == ("ab.",)
        with pytest.raises(UnreadTextError):
            frontend.phonemize_flat("ab")
        assert frontend.phonemize("...") == []


class TestBackends:
    def test_grapheme_and_unicode_backends_build_without_get_lang(self):
        graphemes = TextFrontend(FrontendConfig("xx-Test", Phonemizer.GRAPHEMES))
        assert graphemes.phonemize("Ab-c. Dé!", Stages(diacritize=False)) == [
            ["a", "b", " ", "c"], ["d", "é"]]
        codepoints = TextFrontend(FrontendConfig("xx-Test", Phonemizer.UNICODE))
        assert codepoints.phonemize("Dé", Stages(diacritize=False)) == [["D", "e", "́"]]

    def test_get_lang_runs_when_the_backend_has_it(self):
        class Picky(Echo):
            asked = []

            @classmethod
            def get_lang(cls, lang):
                cls.asked.append(lang)
                if lang != "pt-PT":
                    raise UnsupportedLanguageError(lang)
                return lang

        build(Picky(), "pt-PT", stages=Stages(diacritize=False))
        with pytest.raises(UnsupportedLanguageError):
            build(Picky(), "ja", stages=Stages(diacritize=False))
        assert Picky.asked == ["pt-PT", "ja"]

    def test_keep_punctuation_reaches_the_backend(self):
        kept = TextFrontend(FrontendConfig("xx", Phonemizer.UNICODE, keep_punctuation=True))
        assert kept.backend.keep_punctuation is True
        assert kept.phonemize("ab, cd.", Stages(diacritize=False)) == [
            ["a", "b", ",", " ", "c", "d", "."]]
        plain = TextFrontend(FrontendConfig("xx", Phonemizer.UNICODE))
        assert plain.phonemize("ab, cd.", Stages(diacritize=False)) == [list("ab cd")]

    def test_a_given_backend_is_not_changed(self):
        given = get_phonemizer(Phonemizer.UNICODE)
        frontend = TextFrontend(FrontendConfig("xx", keep_punctuation=True,
                                               stages=Stages(diacritize=False)), given)
        assert given.keep_punctuation is False
        assert frontend.backend.keep_punctuation is True
        assert frontend.phonemize("ab, cd.") == [["a", "b", ",", " ", "c", "d", "."]]
        assert given.phonemize("ab, cd.", "xx") == [list("ab cd")]
        same = TextFrontend(FrontendConfig("xx", stages=Stages(diacritize=False)), given)
        assert same.backend is given

    def test_backend_overrides_keep_working(self):
        class Lists(Echo):
            def phonemize_to_list(self, text, lang):
                return ["L", text]

            def phonemize_lazy(self, text, lang):
                yield ["Z", text]

        frontend = build(Lists(), stages=Stages(diacritize=False))
        assert frontend.phonemize_flat("ab. cd.") == ["L", "ab. cd."]
        assert frontend.phonemize("ab. cd.") == [["Z", "ab."], ["Z", "cd."]]

    def test_with_backend_swaps_the_instance_and_keeps_the_config(self):
        first, second = Echo(), Mute()
        frontend = build(first, stages=Stages(diacritize=False))
        swapped = frontend.with_backend(second)
        assert swapped.backend is second and swapped.config is frontend.config
        assert frontend.backend is first
        assert swapped.phonemize_flat("ab") == []
        assert second.read == [("ab", "xx")] and first.read == []

    def test_identity_names_the_backend_and_the_language(self):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.UNICODE))
        assert frontend.identity() == PhonemizerIdentity(
            "unicode", "scriptconv", VERSION_STR, "pt-PT", None)
        reference = TextFrontend(FrontendConfig("pt-PT", Phonemizer.UNICODE, stages=Stages(lang="es")))
        assert reference.identity().lang == "es"


class TestGraph:
    def test_register_adds_the_frontend_route(self):
        graph = ConversionGraph()
        build(Echo(), stages=Stages(diacritize=False)).register(graph)
        assert [list(s) for s in graph.convert("ab. cd.", "text", "ipa")] == [list("ab"), list("cd")]

    def test_the_route_passes_stages(self, monkeypatch):
        stages = Recorder(monkeypatch)
        graph = ConversionGraph()
        build(Echo(), normalizer=stages.normalize, alphabet=Alphabet.XSAMPA).register(graph)
        route = graph.convert("ab", "text", "x-sampa", stages=Stages(normalize=False, diacritize=True))
        assert list(route) == [list("dab")]


class TestSpokenNormalizer:
    def test_it_is_text2spoken_normalize(self):
        import text2spoken
        assert spoken_normalizer() is text2spoken.normalize

    def test_the_hook_reads_numbers(self):
        frontend = TextFrontend(FrontendConfig("en", Phonemizer.UNICODE, normalizer=spoken_normalizer(),
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize("I have 5 cats.") == [list("I have five cats")]

    def test_a_missing_extra_names_it(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "text2spoken", None)
        with pytest.raises(ImportError, match=r"scriptconv\[normalize\]"):
            spoken_normalizer()


class TestModulePhonemize:
    """The module function calls the backend directly, so it reads what the backend reads."""

    @pytest.mark.parametrize("override, text, lang", [
        (Phonemizer.SHAMI, "hello world", "pt-PT"),
        (Phonemizer("kog2p"), "안녕하세요", "en"),
    ])
    def test_a_backend_that_refuses_the_tag_in_get_lang_still_reads_the_text(self, override, text, lang):
        backend = get_phonemizer(override)
        assert phonemize(text, lang, override=override) == backend.phonemize_string(text, lang)

    def test_the_module_function_adds_no_diacritizer(self):
        text = "الطقس جميل جدا اليوم."
        assert phonemize(text, "ar", override=Phonemizer.ESPEAK) == (
            EspeakPhonemizer().phonemize_string(text, "ar"))
