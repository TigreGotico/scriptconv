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
import tomllib
from importlib.metadata import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from scriptconv import frontend as frontend_module
from scriptconv.frontend import Chunk, FrontendConfig, Stages, TextFrontend, spoken_normalizer
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
from scriptconv.phonemizers.base import GraphemePhonemizer, UnicodeCodepointPhonemizer, join_sentences
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


class LongVowel(GraphemePhonemizer):
    """Graphemes, with the X-SAMPA length symbol ":" after a vowel at the end of a word."""

    def phonemize_string(self, text, lang):
        return re.sub(r"([aeiou])\b", r"\1:", super().phonemize_string(text, lang))


class Glottal(GraphemePhonemizer):
    """Graphemes, with the X-SAMPA glottal stop "?" for an "h" at the end of a word."""

    def phonemize_string(self, text, lang):
        return re.sub(r"h\b", "?", super().phonemize_string(text, lang))


def build(backend, lang="xx", **config):
    return TextFrontend(FrontendConfig(lang, **config), backend)


class Joined(str):
    """A piece of text that counts the characters that each ``+`` with it copies."""

    copied = 0

    def __add__(self, other):
        Joined.copied += len(self) + len(other)
        return Joined(str.__add__(self, other))

    def __radd__(self, other):
        Joined.copied += len(self) + len(other)
        return Joined(str.__add__(other, self))


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

    def test_the_text_is_normalised_whole_and_each_sentence_diacritized(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.phonemize("ab. cd.") == [list("dnab"), list("dcd")]
        assert stages.log == [("normalize", "ab. cd.", "xx"), ("diacritize", "nab.", "xx", None),
                              ("diacritize", "cd.", "xx", None)]

    def test_flat_runs_the_same_order(self, monkeypatch):
        stages = Recorder(monkeypatch)
        backend = Echo()
        frontend = build(backend, normalizer=stages.normalize,
                         stages=Stages(diacritize=True, casing=stages.casing))
        # normalisation and casing read the text whole, the diacritizer reads
        # each sentence, and the backend reads each chunk without its
        # punctuation, as synthesis does
        assert frontend.phonemize_flat("ab. cd.") == list("dNAB dCD")
        assert stages.log == [("normalize", "ab. cd.", "xx"), ("casing", "nab. cd."),
                              ("diacritize", "NAB.", "xx", None), ("diacritize", "CD.", "xx", None)]
        assert backend.read == [("dNAB", "xx"), ("dCD", "xx")]

    def test_prepare_runs_the_same_stages_as_phonemize(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=stages.normalize, stages=Stages(diacritize=True))
        assert frontend.prepare("ab. cd.") == "dnab. dcd."
        assert stages.stage_names() == ["normalize", "diacritize", "diacritize"]
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


class TestSegmentText:
    """The ``text`` of a segment is the staged source text the backend read."""

    @pytest.mark.parametrize("chunk, text, expected", [
        (Chunk.SENTENCE, "Olá mundo. Tudo bem?", ["Olá mundo.", "Tudo bem?"]),
        (Chunk.CLAUSE, "Olá, mundo. Tudo bem?", ["Olá,", "mundo.", "Tudo bem?"]),
        (Chunk.PARAGRAPH, "Olá mundo. Tudo bem?", ["Olá mundo. Tudo bem?"]),
        (Chunk.NONE, "Olá mundo. Tudo bem?", ["Olá mundo. Tudo bem?"]),
    ])
    def test_the_text_is_the_staged_sentence_or_clause(self, chunk, text, expected):
        frontend = build(Echo(), stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments(text, Stages(chunk=chunk))] == expected

    def test_a_sentence_the_backend_splits_does_not_repeat_its_text(self):
        class Splitter(Echo):
            def phonemize_lazy(self, text, lang):
                yield list(text)
                yield list(text)

        frontend = build(Splitter(), stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments("Olá mundo.",
                                                  Stages(chunk=Chunk.NONE))] == ["Olá mundo."]

    def test_the_normalizer_output_is_the_text(self):
        frontend = build(Echo(), normalizer=lambda text, lang: text.upper(),
                         stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments("Olá mundo. Tudo bem?")] == [
            "OLÁ MUNDO.", "TUDO BEM?"]

    def test_a_block_keeps_its_written_text(self):
        frontend = build(Echo(), stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments("[[ana]] Olá.",
                                                  Stages(chunk=Chunk.SENTENCE))] == [
            "[[ana]]", "Olá."]

    @pytest.mark.parametrize("chunk, text, expected", [
        (Chunk.SENTENCE, "اقرأ [[h a l o]] الآن.", ["اقرأ [[h a l o]]", "الآن."]),
        (Chunk.CLAUSE, "اقرأ [[h a l o]] الآن.", ["اقرأ [[h a l o]]", "الآن."]),
        (Chunk.PARAGRAPH, "اقرأ [[h a l o]] الآن.", ["اقرأ [[h a l o]] الآن."]),
        (Chunk.SENTENCE, "ab [[xy]] cd. ef.", ["ab [[xy]]", "cd.", "ef."]),
        (Chunk.PARAGRAPH, "ab [[xy]] cd. ef.", ["ab [[xy]] cd. ef."]),
        (Chunk.SENTENCE, "a [[x]] b [[y]] c.", ["a [[x]]", "b [[y]]", "c."]),
        (Chunk.CLAUSE, "a [[x]] b [[y]] c.", ["a [[x]]", "b [[y]]", "c."]),
        (Chunk.PARAGRAPH, "a [[x]] b [[y]] c.", ["a [[x]] b [[y]] c."]),
        (Chunk.SENTENCE, "[[ana]].", ["[[ana]]."]),
        (Chunk.CLAUSE, "[[ana]].", ["[[ana]]."]),
        (Chunk.PARAGRAPH, "[[ana]].", ["[[ana]]."]),
        (Chunk.SENTENCE, "Olá [[ana]].", ["Olá [[ana]]."]),
        (Chunk.CLAUSE, "Olá [[ana]].", ["Olá [[ana]]."]),
        (Chunk.PARAGRAPH, "Olá [[ana]].", ["Olá [[ana]]."]),
        (Chunk.SENTENCE, "[[ana]] Olá.", ["[[ana]]", "Olá."]),
        (Chunk.SENTENCE, "Olá [[ana]], tudo bem?", ["Olá [[ana]],", "tudo bem?"]),
        (Chunk.CLAUSE, "Olá [[ana]], tudo bem?", ["Olá [[ana]],", "tudo bem?"]),
        (Chunk.PARAGRAPH, "Olá [[ana]], tudo bem?", ["Olá [[ana]], tudo bem?"]),
        (Chunk.SENTENCE, "Olá [[ana]]! Tudo bem?", ["Olá [[ana]]!", "Tudo bem?"]),
        (Chunk.PARAGRAPH, "Olá [[ana]]! Tudo bem?", ["Olá [[ana]]! Tudo bem?"]),
    ])
    def test_a_block_keeps_the_staged_words_before_it(self, chunk, text, expected):
        frontend = build(Echo(), stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments(text, Stages(chunk=chunk))] == expected

    def test_the_words_before_a_block_are_the_staged_text(self):
        frontend = build(Echo(), normalizer=lambda text, lang: text.upper(),
                         stages=Stages(diacritize=False))
        assert [s.text for s in frontend.segments("ab [[xy]] cd.",
                                                  Stages(chunk=Chunk.SENTENCE))] == [
            "AB [[xy]]", "CD."]


class TestInlineBlocks:
    def test_no_stage_reads_a_block(self, monkeypatch):
        stages = Recorder(monkeypatch)
        frontend = build(Echo(), normalizer=lambda text, lang: text.upper(),
                         stages=Stages(diacritize=True))
        assert frontend.phonemize("ab [[xy]] cd. ef.") == [
            list("dAB") + [" ", "x", "y", " "], list("dCD"), list("dEF")]
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
            list("nab") + [" ", "x", "y", " "] + list("ncd"))
        assert [entry[1] for entry in stages.log] == ["ab", "cd"]

    # A synthesis sentence never starts with a space. The flat stream is the
    # sentences joined: no space after a sentence that ends in a clause symbol
    # or a space, and one space after any other sentence.

    @pytest.mark.parametrize("keep", [True, False])
    def test_an_empty_block_leaves_one_space(self, keep):
        frontend = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize("ab [[]] cd") == [list("ab cd")]
        assert frontend.phonemize_flat("ab [[]] cd") == list("ab cd")

    def test_a_block_after_a_pause_mark_takes_its_space(self):
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False)))
        assert kept.phonemize("Olá, [[ana]]") == [list("olá, ana")]
        assert kept.phonemize_flat("Olá, [[ana]]") == list("olá, ana")

    @pytest.mark.parametrize("text, sentences, flat", [
        ("Um [[x]]. Dois; três.", ["um x.", "dois; três."], "um x.dois; três."),
        ("Olá [[ana]], tudo bem? Sim.", ["olá ana, ", "tudo bem?", "sim."],
         "olá ana, tudo bem?sim."),
        ("Olá, [[ana]], tudo bem?", ["olá, ana, ", "tudo bem?"], "olá, ana, tudo bem?"),
        ("Sim [[a:]]? Não.", ["sim a:?", "não."], "sim a:?não."),
    ])
    def test_a_mark_after_a_block_ends_the_block_clause(self, text, sentences, flat):
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False)))
        assert kept.phonemize(text) == [list(sentence) for sentence in sentences]
        assert kept.phonemize_flat(text) == list(flat)

    @pytest.mark.parametrize("keep, text, sentences, flat", [
        # the block ends in a length symbol, and no mark follows it
        (True, "Olá [[a:]] sim.", ["olá a: ", "sim."], "olá a: sim."),
        # an ellipsis gives no symbol
        (True, "Espera [[a]]... vamos.", ["espera a", "vamos."], "espera a vamos."),
        # with punctuation off, a clause break inside a sentence is a space
        (False, "Um [[x]]. Dois; três.", ["um x", "dois três"], "um x dois três"),
        (False, "Olá, [[ana]], tudo bem?", ["olá ana", "tudo bem"], "olá ana tudo bem"),
        # an empty block reads as no text, so the full stop ends the clause of "ab"
        (True, "ab [[]]. cd", ["ab.", "cd"], "ab.cd"),
        # the comma ends the clause of the word after the block, so it stays with that word
        (True, "Olá [[ˈana]]s, tudo bem?", ["olá ˈana", "s, tudo bem?"], "olá ˈana s, tudo bem?"),
        # a mark with a block directly after it ends no clause
        (True, "[[x]],[[y]]", ["xy"], "xy"),
        (True, "[[x]].[[y]]", ["xy"], "xy"),
        # with punctuation off, no space ends the sentence of the block
        (False, "Sim [[x.]]vem.", ["sim x.", "vem"], "sim x. vem"),
    ])
    def test_a_block_with_no_clause_symbol_keeps_its_space(self, keep, text, sentences, flat):
        frontend = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize(text) == [list(sentence) for sentence in sentences]
        assert frontend.phonemize_flat(text) == list(flat)

    @pytest.mark.parametrize("text", ["[[x]],[[y]]", "[[x]].[[y]]", "[[x]]?[[y]]",
                                      "Sim.[[rui]] vem", "Sim![[rui]] vem"])
    def test_a_mark_before_the_next_block_gives_no_token(self, text):
        def frontend(keep):
            return TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        assert frontend(True).phonemize(text) == frontend(False).phonemize(text)
        assert frontend(True).phonemize_flat(text) == frontend(False).phonemize_flat(text)

    @pytest.mark.parametrize("text, plain", [
        ("Tu viens [[x]] ?", "Tu viens x ?"),
        ("Tu viens [[x]] ?", "Tu viens x ?"),
        ("[[x]] , b", "x , b"),
        ("Um [[x]]. Dois; três.", "Um x. Dois; três."),
        ("[[x]] ; [[y]] !", "x ; y !"),
        ("[[x]],[[y]]", "x,y"),
        ("[[x]].[[y]]", "x.y"),
        # "|" ends a clause with no symbol
        ("Olá [[x]]| vem.", "Olá x| vem."),
        # a clause with no word after the mark gives no space
        ("Olá [[x]]! ... vem.", "Olá x! ... vem."),
        # a pause mark takes its space all the same
        ("Olá [[x]], ... sim.", "Olá x, ... sim."),
        ("Olá [[x]]:", "Olá x:"),
        # a mark directly before the block joins it, and the space before the mark stays
        ("Sim .[[x]] vem.", "Sim .x vem."),
        # a block directly after a word joins it, though a space comes earlier in the text
        ("Olá vem[[rui]] já.", "Olá vemrui já."),
    ])
    def test_a_mark_after_a_block_reads_as_after_a_plain_word(self, text, plain):
        kept = TextFrontend(FrontendConfig("fr", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False)))
        assert kept.phonemize_flat(text) == kept.phonemize_flat(plain)

    def test_a_mark_after_a_space_after_a_block_stays(self):
        kept = TextFrontend(FrontendConfig("fr", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False)))
        assert kept.phonemize("Tu viens [[x]] ?") == [list("tu viens x?")]
        assert kept.phonemize_flat("Tu viens [[x]] ?") == list("tu viens x?")

    def test_the_mark_is_read_after_the_stages(self):
        kept = TextFrontend(FrontendConfig(
            "pt", Phonemizer.GRAPHEMES, keep_punctuation=True, stages=Stages(diacritize=False),
            normalizer=lambda text, lang: text.replace("§", "parágrafo")))
        # the normaliser gives the comma a word, so the comma ends that word's clause
        assert kept.phonemize("Olá [[x]]§, sim.") == [list("olá x"), list("parágrafo, sim.")]
        assert kept.phonemize_flat("Olá [[x]]§, sim.") == list("olá x parágrafo, sim.")

    @pytest.mark.parametrize("text, casing", [
        # a casing stage changes the case of the word that stands for the block
        ("Olá [[x]], b.", str.upper),
        # an empty block is no word, so the comma still has a space after it
        ("Olá [[x]],[[]] b.", None),
        # a closing bracket is no word, so the comma after it ends the block clause
        ("Olá [[x]]), b.", None),
    ])
    def test_the_mark_reads_as_in_plain_text(self, text, casing):
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False, casing=casing)))
        assert kept.phonemize(text) == [list("olá x, "), list("b.")]
        assert kept.phonemize_flat(text) == list("olá x, b.")

    @pytest.mark.parametrize("text, lazy, flat", [
        ("Olá [[x]] sim. [[y]], b.",
         ["Olá", "sim.", "a, b.", ", b."], ["Olá", "sim.", "a, b.", ", b."]),
        # a digit gives the clause a word, as a letter does
        ("Olá [[x]] 2 gatos, b.", ["Olá", "2 gatos, b."], ["Olá", "2 gatos, b."]),
        # no text after the block gives no mark
        ("Olá [[x]]", ["Olá"], ["Olá"]),
    ])
    def test_the_stages_read_the_mark_only_when_one_can_follow_the_block(self, text, lazy, flat):
        read = []

        def casing(text):
            read.append(text)
            return text
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False, casing=casing)))
        kept.phonemize(text)
        assert read == lazy
        read.clear()
        kept.phonemize_flat(text)
        assert read == flat

    @pytest.mark.parametrize("override", ["phonemize_lazy", "phonemize_to_list"])
    def test_a_backend_with_its_own_output_gets_no_mark(self, override):
        def own(self, text, lang):
            return list(text) if override == "phonemize_to_list" else iter([list(text)])
        backend = type("Own", (Echo,), {override: own})

        def frontend(keep):
            return build(backend(), keep_punctuation=keep, stages=Stages(diacritize=False))
        for path in ("phonemize", "phonemize_flat"):
            text = "Um [[x]]. Dois"
            assert getattr(frontend(True), path)(text) == getattr(frontend(False), path)(text)

    # A block reads as the same text with a plain word in its place, so the
    # expected stream is that plain text read by the same frontend.

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("backend", [Phonemizer.GRAPHEMES, Phonemizer.UNICODE,
                                         Phonemizer.ORTHOGRAPHY2IPA])
    @pytest.mark.parametrize("text", [
        "Olá [[x]] sim. [[y]], b.",
        # a block ends the first sentence, and another block starts the second
        "Olá [[ana]]. [[rui]] sim.",
        # a block starts the second sentence
        "Sim. [[rui]] vem.",
        "Tudo bem? [[rui]] sim.",
        # an ellipsis ends the sentence with no token, so the space stays
        "Espera... [[rui]] vamos.",
        # the splitter keeps the clause after "Olá!" in its sentence, so the space stays
        "Olá! [[rui]] tudo bem?",
        # a sentence with no word gives no phonemes, so "Fim." joins the block
        "Fim. ... [[rui]] vem.",
        # the splitter keeps the clause after '."' or "Dr." in its sentence
        'Tudo." [[rui]] vem.',
        "Sim. Dr. [[rui]] vem.",
        # the splitter keeps the clause after "!" or "?!" in its sentence
        "Olá [[rui]]! tudo bem?",
        "Olá [[rui]]?! tudo bem?",
        # a line break or a tab is a space
        "Sim.\n[[rui]] vem.",
        "Sim\n[[rui]] vem.",
        "Sim [[rui]]\nvem.",
        # an empty block reads as no text
        "Sim. [[]] [[rui]] vem.",
    ])
    def test_a_block_after_a_sentence_token_joins_as_in_plain_text(self, keep, backend, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", backend, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        plain = text.replace("[[]]", "").replace("[[", "").replace("]]", "")
        # each block holds the backend's own reading of its word
        blocks = re.sub(r"\[\[(\w+)\]\]",
                        lambda word: f"[[{''.join(frontend.phonemize_flat(word[1]))}]]", text)
        assert frontend.phonemize_flat(blocks) == frontend.phonemize_flat(plain)
        assert join_sentences(frontend.phonemize(blocks), keep) == frontend.phonemize_flat(plain)

    # The unicode backend copies a tab to its output, and a block reads a tab
    # as one space symbol, so the tab row reads the backends that turn a tab
    # into a space.
    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("backend", [Phonemizer.GRAPHEMES, Phonemizer.ORTHOGRAPHY2IPA])
    def test_a_tab_around_a_block_is_a_space(self, keep, backend):
        frontend = TextFrontend(FrontendConfig("pt-PT", backend, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        rui = "".join(frontend.phonemize_flat("rui"))
        expected = frontend.phonemize_flat("Sim\trui\tvem.")
        assert frontend.phonemize_flat(f"Sim\t[[{rui}]]\tvem.") == expected
        assert join_sentences(frontend.phonemize(f"Sim\t[[{rui}]]\tvem."), keep) == expected

    @pytest.mark.parametrize("keep, backend, text, start, tail", [
        # the block symbols end in "." with punctuation off, and still keep their space
        (False, Phonemizer.GRAPHEMES, "Sim. [[x.]]. [[y]] vem.", "sim x. y ", "vem."),
        # "1." gives orthography2ipa no phonemes, so no token comes before the block
        (True, Phonemizer.ORTHOGRAPHY2IPA, '[[ana]]." 1. [[rui]] vem.', "ana rui ", "vem."),
        # the block ends in "." but its clause ends in an ellipsis, which gives no token
        (True, Phonemizer.GRAPHEMES, "[[x.]]... [[y]]", "x. y", ""),
    ])
    def test_a_block_keeps_its_space_unless_it_starts_a_sentence_after_a_token(
            self, keep, backend, text, start, tail):
        frontend = TextFrontend(FrontendConfig("pt-PT", backend, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        expected = list(start) + frontend.phonemize_flat(tail)
        assert frontend.phonemize_flat(text) == expected
        assert join_sentences(frontend.phonemize(text), keep) == expected

    @pytest.mark.parametrize("text", [
        "Sim. [[]]. vem.",
        "Sim. [[ ]]. vem.",
        "Sim. [[]]. 1.",
        "Sim. [[]]. [[rui]] vem.",
        "Sim.[[]]. [[rui]] vem.",
        "Sim. [[]][[rui]] vem.",
        # "!" ends no sentence, so the text after the block keeps its space
        "Sim! [[]] vem.",
        "Sim! [[]]1.",
        "Sim![[]] vem.",
        "Sim.[[]] vem.",
        # the full stop after the block ends the sentence of "Dr."
        "Dr. [[]]. [[rui]] vem.",
        # nothing follows the block, so the full stop before it stays
        "Sim.1. [[]]",
        # a mark directly before a word gives no symbol, and the space before it stays
        "Sim. [[]].[[rui]] vem.",
        "Sim! [[]].[[rui]] vem.",
        # a tab is whitespace, so a block of a tab is empty
        "Sim [[\t]]vem.",
    ])
    @pytest.mark.parametrize("keep", [True, False])
    def test_an_empty_block_reads_as_no_text(self, keep, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES,
                                               keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        plain = re.sub(r"\[\[\s*\]\]", "", text).replace("[[", "").replace("]]", "")
        expected = frontend.phonemize_flat(plain)
        assert frontend.phonemize_flat(text) == expected
        assert join_sentences(frontend.phonemize(text), keep) == expected

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Sim [[x.]][[]]vem.", "Sim [[x.]][[]] vem.",
                                      "Sim. [[]] [[rui]] vem.", "[[x]][[]]. vem."])
    def test_a_text_reads_as_without_its_empty_block(self, keep, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES,
                                               keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        expected = frontend.phonemize_flat(text.replace("[[]]", ""))
        assert frontend.phonemize_flat(text) == expected
        assert join_sentences(frontend.phonemize(text), keep) == expected

    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", [
        "[[x]]. [[?]]... vem.",
        "[[x]]. [[?]] vem.",
        "[[x]]. [[!]] vem.",
        "Sim. [[,]] vem.",
        "[[x]]? [[?]]. vem.",
        "Olá [[x]] [[?]] sim.",
        "Sim [[x.]]...",
        "Sim [[x.]][[]] vem.",
    ])
    def test_a_block_that_ends_in_a_mark_reads_as_a_plain_word(self, keep, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES,
                                               keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        symbols = re.search(r"\[\[([^\]]*\W)\]\]", text)[1]
        # "k" stands for that block in the plain text, and its symbols take its place
        plain = (text.replace(f"[[{symbols}]]", "k").replace("[[]]", "")
                 .replace("[[", "").replace("]]", ""))
        expected = list("".join(frontend.phonemize_flat(plain)).replace("k", symbols))
        assert frontend.phonemize_flat(text) == expected
        assert join_sentences(frontend.phonemize(text), keep) == expected

    @pytest.mark.parametrize("keep, expected", [(True, "sim x. vem."), (False, "sim x. vem")])
    def test_a_hyphen_after_a_block_is_no_letter_of_a_word(self, keep, expected):
        # the hyphen follows a mark, not a letter, so it separates two words
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize_flat("Sim [[x.]]-vem.") == list(expected)

    # tts-punctuation: "A hyphen with a space next to it, or at a word edge,
    # is no part of a word: it gives no symbol, and a space separates the two
    # words." A hyphen next to a block stands at the edge of a word.
    @pytest.mark.parametrize("keep, expected", [(True, "sim vem xy."), (False, "sim vem xy")])
    def test_a_hyphen_before_a_block_is_no_letter_of_a_word(self, keep, expected):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize_flat("Sim vem-[[xy]].") == list(expected)
        assert frontend.phonemize("Sim vem-[[xy]].") == [list(expected)]

    # tts-punctuation: a "!" or "?" between two letters "still separates two
    # words, so it becomes a space". The block is the word after the mark.
    @pytest.mark.parametrize("keep", [True, False])
    @pytest.mark.parametrize("text", ["Sim![[rui]]", "Sim?[[rui]] vem.", "Sim?![[rui]] vem."])
    def test_a_mark_that_separates_two_words_before_a_block_is_a_space(self, keep, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES, keep_punctuation=keep,
                                               stages=Stages(diacritize=False)))
        plain = text.replace("[[", "").replace("]]", "")
        assert "".join(frontend.phonemize_flat(plain)).startswith("sim rui")
        assert frontend.phonemize_flat(text) == frontend.phonemize_flat(plain)

    # A backend can write a phoneme with the character of a clause symbol, as
    # X-SAMPA writes ":" for length and "?" for a glottal stop. That phoneme
    # stays before a block, as before a plain word.
    @pytest.mark.parametrize("backend, text, expected", [
        (LongVowel, "Casa [[rui:]] vem.", "casa: rui: vem."),
        (LongVowel, "Ana [[rui:]]", "ana: rui:"),
        (LongVowel, "Casa\n[[rui:]]", "casa: rui:"),
        (Glottal, "Nah [[rui]] vem.", "na? rui vem."),
        # the clause symbols of the text still read as in the plain text
        (LongVowel, "Uma, [[rui:]] vem.", "uma:, rui: vem."),
        (Glottal, "Bah. [[rui]] vem.", "ba?.rui vem."),
    ])
    def test_a_phoneme_written_as_a_clause_symbol_stays_before_a_block(
            self, backend, text, expected):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES,
                                               keep_punctuation=True,
                                               stages=Stages(diacritize=False)), backend())
        plain = re.sub(r"\[\[(\w+):?\]\]", r"\1", text)
        assert frontend.phonemize_flat(plain) == list(expected)
        assert frontend.phonemize_flat(text) == list(expected)
        assert join_sentences(frontend.phonemize(text), True) == list(expected)

    # The text between the blocks holds no word, so the mark at the end of
    # the first block is its own symbol, and it stays.
    @pytest.mark.parametrize("text, start", [
        ("[[x!]]![[y]] vem.", "x!"),
        ("[[x?]]?[[y]]", "x?"),
        ("Sim [[x.]]![[y]]", "sim x."),
    ])
    def test_a_mark_after_a_block_leaves_the_block_symbols(self, text, start):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.GRAPHEMES,
                                               keep_punctuation=True,
                                               stages=Stages(diacritize=False)))
        assert "".join(frontend.phonemize_flat(text)).startswith(start)
        assert "".join(join_sentences(frontend.phonemize(text), True)).startswith(start)

    # orthography2ipa reads a clause of only digits to nothing, so the "?" of
    # "Sim" is the last symbol before the block. It ends a clause, so it stays.
    @pytest.mark.parametrize("text", ["Sim? 1...\n[[ʁuj]] vem.", "Sim? 1... [[ʁuj]] vem.",
                                      "Sim? 1.[[ʁuj]] vem."])
    def test_the_mark_of_an_earlier_clause_stays_before_a_block(self, text):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ORTHOGRAPHY2IPA,
                                               keep_punctuation=True,
                                               stages=Stages(diacritize=False)))
        sim = frontend.phonemize_flat("Sim?")
        assert sim[-1] == "?"
        assert frontend.phonemize_flat(text)[:len(sim)] == sim
        assert join_sentences(frontend.phonemize(text), True)[:len(sim)] == sim

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

    # A text of empty blocks joins into one piece. When each piece is added
    # to the text joined so far, each + copies all of that text again, and the
    # copies grow with the square of the number of pieces. A join that copies
    # each piece once copies no characters through +.

    @pytest.mark.parametrize("unit", ["ab[[]]", "a [[ ]] ", "[[x]] b[[]]"])
    def test_empty_blocks_join_in_linear_time(self, unit, monkeypatch):
        split = frontend_module._split_blocks
        monkeypatch.setattr(Joined, "copied", 0)
        monkeypatch.setattr(frontend_module, "_split_blocks",
                            lambda text: [Joined(part) for part in split(text)])
        text = unit * 10000
        parts = frontend_module._split_blocks_to_read(text)
        assert "".join(parts) == re.sub(r"\[\[\s*\]\]", "", text)
        assert len(parts) == 2 * text.count("[[x]]") + 1
        assert Joined.copied <= 2 * len(text), Joined.copied

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

    @pytest.mark.timeout(20)
    @pytest.mark.parametrize("unit", ["ab[[]]", "a [[ ]] "])
    def test_a_long_text_of_empty_blocks_joins_in_well_under_two_seconds(self, unit):
        text = unit * 640000
        start = time.perf_counter()
        frontend_module._split_blocks_to_read(text)
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
            ["a", "b", "-", "c"], ["d", "é"]]
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

    def test_a_line_break_inside_a_clause_keeps_the_words_apart(self):
        espeak = EspeakPhonemizer()
        words = " ".join(espeak.phonemize_string(word, "pt") for word in ("Olá", "Tudo bem"))
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.ESPEAK, keep_punctuation=True,
                                           stages=Stages(diacritize=False)), espeak)
        assert kept.phonemize_flat("Olá\nTudo bem.") == list(words + ".")
        assert kept.phonemize("Olá\nTudo bem.") == [list(words + ".")]

    def test_a_sentence_with_no_symbol_keeps_its_last_word_apart(self):
        kept = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True,
                                           stages=Stages(diacritize=False)))
        assert kept.phonemize_flat("Espera... vamos.") == list("espera vamos.")
        assert kept.phonemize("Espera... vamos.") == [list("espera"), list("vamos.")]
        # an inline block joins the sentence before it, and no sentence starts with a space;
        # the block starts a sentence after "vamos.", so it joins with no space
        assert kept.phonemize_flat("Espera... vamos. [[a]]") == list("espera vamos.a")
        assert kept.phonemize("Espera... vamos. [[a]]") == [list("espera"), list("vamos.a")]
        assert kept.phonemize_flat("Sim? Não.") == list("sim?não.")
        assert kept.phonemize("Sim? Não.") == [list("sim?"), list("não.")]
        plain = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES,
                                            stages=Stages(diacritize=False)))
        assert plain.phonemize("Espera... vamos.") == [list("espera"), list("vamos")]

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
        assert frontend.phonemize("ab. cd.") == [["Z", "ab."], ["Z", "cd."]]
        # training reads the sentence path too, not phonemize_to_list
        assert frontend.phonemize_flat("ab. cd.") == ["Z", "ab.", " ", "Z", "cd."]

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
        identity = frontend.identity()
        assert identity.revision.startswith("sc1:")
        assert identity.revision != UnicodeCodepointPhonemizer().identity("pt-PT").revision
        assert identity == PhonemizerIdentity(
            "unicode", "scriptconv", VERSION_STR, "pt-PT", identity.revision, frontend_module.FRONTEND_VERSION)
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

    def test_the_hook_reads_a_portuguese_date(self):
        frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.UNICODE, normalizer=spoken_normalizer(),
                                               stages=Stages(diacritize=False)))
        assert frontend.phonemize("Chego a 12/05/2020.") == [list("Chego a doze de maio de dois mil e vinte")]

    def test_a_missing_extra_names_it(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "text2spoken", None)
        with pytest.raises(ImportError, match=r"scriptconv\[normalize\]"):
            spoken_normalizer()

    def test_the_extra_installs_every_language_extra_of_text2spoken(self):
        """A language extra of text2spoken that holds a requirement, such as `pt` for tugalex, is in the extra. An extra
        with no requirement, kept so that an install that names it still resolves, adds nothing to name."""
        pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
        requirement, = map(Requirement, pyproject["project"]["optional-dependencies"]["normalize"])
        installed = metadata("text2spoken")
        markers = [Requirement(line).marker for line in installed.get_all("Requires-Dist") or []]
        languages = {extra for extra in installed.get_all("Provides-Extra") if extra != "test"
                     and any(marker and marker.evaluate({"extra": extra}) and not marker.evaluate({"extra": ""})
                             for marker in markers)}
        assert requirement.name == "text2spoken"
        assert languages, "no language extra of text2spoken holds a requirement"
        assert languages <= requirement.extras, f"text2spoken extras missing: {sorted(languages - requirement.extras)}"


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
