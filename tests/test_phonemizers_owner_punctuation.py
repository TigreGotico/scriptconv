"""A backend that owns normalization reads its text with punctuation kept.

Governing clause, ``knowledge/wiki/concepts/speech-stack-contract.md``:

    ``owned_stages`` names the stages that a backend always runs itself, and
    ``TextFrontend`` skips them. A stage that a backend runs only with an
    optional dependency is not owned. A backend that owns normalisation
    receives its text with punctuation kept, because ``remove_punctuation``
    (``base.py:189``) drops the ``.`` of ``Dr.`` and the ``%`` of ``20%``.

Each expected value comes from the engine itself, called directly on the words
a reader says. The code under test is the path through ``BasePhonemizer``, so
the engine is the independent side of every comparison.
"""
import sys
import types

import ahotts_g2p
import phonikud
import pytest
from arbtok.plugin import ArbtokG2PPlugin
from euskaphone import EuskaPhonemizer
from tugaphone.lattice_core import phonemize as tugaphone_reads

from scriptconv.phonemizers.ar import ArbtokPhonemizer, MantoqPhonemizer
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.eu import AhoTTSPhonemizer, EuskaphonePhonemizer
from scriptconv.phonemizers.he import PhonikudPhonemizer
from scriptconv.phonemizers.ja import OpenJTaklPhonemizer
from scriptconv.phonemizers.mwl import MirandesePhonemizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer
from scriptconv.phonemizers.shami import ShamiPhonemizer
from scriptconv.phonemizers.vi import VIPhonemePhonemizer


def spoken(sentences):
    """The sentences of a ``phonemize`` result as one string."""
    return " ".join("".join(sentence) for sentence in sentences)


class Recording(BasePhonemizer):
    """Records what reaches the engine, and repeats all of it in its output."""

    def __init__(self):
        super().__init__()
        self.received = []

    def phonemize_string(self, text, lang):
        self.received.append(text)
        return text.upper()


class RecordingOwner(Recording):
    owned_stages = frozenset({"normalize"})


@pytest.fixture(scope="module")
def tugaphone():
    return TugaphonePhonemizer()


@pytest.fixture
def punctuated():
    phonemizer = TugaphonePhonemizer()
    phonemizer.keep_punctuation = True
    return phonemizer


class TestTugaphoneReadsWrittenForms:
    def test_title_is_read_as_a_word(self, tugaphone):
        assert tugaphone.phonemize("O Dr. Silva chegou.", "pt-PT") == \
            [list(tugaphone_reads("O doutor Silva chegou.", "pt-PT"))]

    def test_percent_is_read_as_words(self, tugaphone):
        assert tugaphone.phonemize("Subiu 20% ontem.", "pt-PT") == \
            [list(tugaphone_reads("Subiu vinte por cento ontem.", "pt-PT"))]

    def test_percent_before_the_full_stop_is_read(self, tugaphone):
        assert tugaphone.phonemize("Subiu 20%.", "pt-PT") == \
            [list(tugaphone_reads("Subiu vinte por cento.", "pt-PT"))]

    def test_title_at_the_end_of_a_sentence_is_read(self, tugaphone):
        assert tugaphone.phonemize("Falei com o Dr.", "pt-PT") == \
            [list(tugaphone_reads("Falei com o doutor.", "pt-PT"))]

    def test_title_the_sentence_splitter_cuts_is_read(self, tugaphone):
        # chunk_text ends a sentence after "Prof.", so the words arrive in two
        # chunks. The reading of each word is still the written form's.
        assert spoken(tugaphone.phonemize("O Prof. Silva chegou.", "pt-PT")) == \
            tugaphone_reads("O professor Silva chegou.", "pt-PT")

    def test_text_with_nothing_to_expand_is_unchanged(self, tugaphone):
        text = "Olá, mundo! Tudo bem?"
        assert spoken(tugaphone.phonemize(text, "pt-PT")) == \
            tugaphone_reads("Olá mundo Tudo bem", "pt-PT")


class TestTugaphoneKeepsPunctuationFlag:
    TEXT = "O Dr. Silva chegou, subiu 20%."

    def expected(self):
        first = tugaphone_reads("O doutor Silva chegou", "pt-PT")
        second = tugaphone_reads("subiu vinte por cento", "pt-PT")
        return list(f"{first}, {second}.")

    def test_lazy_path(self, punctuated):
        assert punctuated.phonemize(self.TEXT, "pt-PT") == [self.expected()]

    def test_list_path_agrees_with_lazy_path(self, punctuated):
        assert punctuated.phonemize_to_list(self.TEXT, "pt-PT") == self.expected()

    def test_a_clause_gets_one_mark_when_it_ends_in_an_abbreviation(self, punctuated):
        assert punctuated.phonemize("Falei com o Dr.", "pt-PT") == \
            [list(tugaphone_reads("Falei com o doutor", "pt-PT") + ".")]


class TestLazyOverrideTurnsTheFlagOff:
    """The clause at ``_keeps_punctuation``: an override owns its own output."""

    class Overriding(TugaphonePhonemizer):
        def phonemize_lazy(self, text, lang):
            yield list(self.phonemize_string(text, lang))

    def test_an_override_of_an_owner_ignores_the_flag(self):
        phonemizer = self.Overriding()
        phonemizer.keep_punctuation = True
        reading = tugaphone_reads("O doutor Silva chegou", "pt-PT")
        assert phonemizer.phonemize("O Dr. Silva chegou.", "pt-PT") == [list(reading)]
        assert phonemizer.phonemize_to_list("O Dr. Silva chegou.", "pt-PT") == list(reading)

    def test_shami_overrides_and_reads_the_percent_through_its_own_path(self):
        shami = ShamiPhonemizer()
        utterance = shami.frontend.process("الربح 20%.")
        assert shami.phonemize("الربح 20%.", "ar") == [utterance.symbols]
        assert shami.frontend.process("الربح 20.").symbols != utterance.symbols


class TestWhatReachesTheEngine:
    def test_an_owner_receives_each_chunk_with_its_punctuation(self):
        owner = RecordingOwner()
        owner.phonemize("o dr. Silva subiu 20%.", "pt")
        assert owner.received == ["o dr.", "Silva subiu 20%."]

    def test_an_owner_receives_each_clause_with_its_punctuation(self):
        owner = RecordingOwner()
        owner.keep_punctuation = True
        owner.phonemize("O Dr. Silva, subiu 20%.", "pt")
        assert owner.received == ["O Dr. Silva", "subiu 20%."]

    def test_a_chunk_of_punctuation_alone_gives_an_owner_nothing_to_read(self):
        owner = RecordingOwner()
        assert owner.phonemize("%", "pt") == [[]]
        assert owner.received == [""]

    def test_a_clause_of_punctuation_alone_never_reaches_the_engine(self):
        owner = RecordingOwner()
        owner.keep_punctuation = True
        owner.phonemize("... , casa.", "pt")
        assert "" not in owner.received

    @pytest.mark.parametrize("module, attribute, cls, lang", [
        ("pyopenjtalk", "g2p", OpenJTaklPhonemizer, "ja"),
        ("viphoneme", "vi2IPA", VIPhonemePhonemizer, "vi"),
    ])
    def test_engines_outside_the_test_extra_receive_the_percent(
            self, monkeypatch, module, attribute, cls, lang):
        seen = []
        engine = types.ModuleType(module)
        setattr(engine, attribute, lambda text, **_: seen.append(text) or "a")
        monkeypatch.setitem(sys.modules, module, engine)
        list(cls().phonemize_lazy("a 20%.", lang))
        assert seen == ["a 20%."]

    def test_other_backends_still_receive_bare_text(self):
        plain = Recording()
        plain.phonemize("O Dr. Silva subiu 20%.", "pt")
        assert plain.received == ["O Dr Silva subiu 20"]


class TestEchoedPunctuationNeverBecomesAPhoneme:
    def test_repeated_punctuation_is_dropped(self):
        assert spoken(RecordingOwner().phonemize("(olá) «mundo», 20%!", "pt")) == \
            "OLÁ MUNDO 20"

    def test_the_list_path_drops_it_too(self):
        assert "".join(RecordingOwner().phonemize_to_list("(olá), mundo.", "pt")) == \
            "OLÁ MUNDO"

    def test_a_clause_mark_is_not_doubled(self):
        owner = RecordingOwner()
        owner.keep_punctuation = True
        assert spoken(owner.phonemize("Olá, mundo.", "pt")) == "OLÁ, MUNDO."

    @pytest.mark.parametrize("text", ["(kaixo) mundua.", "Kaixo, mundua!", "«kaixo» mundua"])
    def test_ahotts_prints_punctuation_as_tokens(self, text):
        aho = AhoTTSPhonemizer()
        assert spoken(aho.phonemize(text, "eu-ES")) == \
            ahotts_g2p.phonemize("kaixo mundua", lang="eu", version="modern")

    @pytest.mark.parametrize("text", ["Ten 20% an 1975.", "(Ten) 20, an 1975?"])
    def test_mirandese_repeats_everything_between_words(self, text):
        mirandese = MirandesePhonemizer()
        assert spoken(mirandese.phonemize(text, "mwl")) == \
            mirandese.phonemize_string("Ten 20 an 1975", "mwl")

    def test_mantoq_notation_survives(self):
        # "_" spells the doubling token and "*" the dhaal.
        mantoq = MantoqPhonemizer(alphabet=Alphabet.HALABI)
        reading = mantoq.phonemize_string("ذهب بيت", "ar")
        assert "*" in reading and "_dbl_" in reading
        assert spoken(mantoq.phonemize("ذهب بيت.", "ar")) == reading


class TestOtherOwnersReadWrittenForms:
    def test_mantoq_reads_the_percent(self):
        mantoq = MantoqPhonemizer(alphabet=Alphabet.HALABI)
        assert spoken(mantoq.phonemize("بيت 20%.", "ar")) == \
            mantoq.phonemize_string("بيت عشرون بالمئة", "ar")

    def test_arbtok_reads_the_percent(self):
        engine = ArbtokG2PPlugin(lang="ar", diacritize=True)
        assert spoken(ArbtokPhonemizer().phonemize("الربح 20%.", "ar")) == \
            engine.transcribe("الربح 20%")

    def test_euskaphone_reads_the_percent(self):
        assert spoken(EuskaphonePhonemizer().phonemize("Etxean 20 % dira.", "eu")) == \
            EuskaPhonemizer().phonemize_sentence("Etxean ehuneko hogei dira")

    def test_ahotts_reads_the_percent(self):
        assert spoken(AhoTTSPhonemizer().phonemize("Etxean 20 % dira.", "eu-ES")) == \
            ahotts_g2p.phonemize("Etxean 20 % dira", lang="eu", version="modern")

    def test_phonikud_reads_the_percent(self):
        assert spoken(PhonikudPhonemizer().phonemize("20%.", "he")) == \
            phonikud.phonemize("20%")

    def test_phonikud_reads_a_date_and_a_time(self):
        assert spoken(PhonikudPhonemizer().phonemize("ב-12.03.2024 בשעה 16:30.", "he")) == \
            " ".join(phonikud.phonemize("ב 12.03.2024 בשעה 16:30").split())


class TestEngineDefectsTheWrappersAbsorb:
    @pytest.mark.parametrize("text, words", [
        ("Etxean 20, eta 1975ean.", "Etxean 20 eta 1975ean"),
        ("Etxean (20) dira?", "Etxean 20 dira"),
        ("Etxean 20! Bai.", "Etxean 20 Bai"),
    ])
    def test_euskaphone_keeps_a_number_with_punctuation_after_it(self, text, words):
        assert EuskaphonePhonemizer().phonemize_string(text, "eu") == \
            EuskaPhonemizer().phonemize_sentence(words)

    def test_euskaphone_percent_after_a_number_stays_for_the_unit_stage(self):
        assert EuskaphonePhonemizer().phonemize_string("20%", "eu") == \
            EuskaPhonemizer().phonemize_sentence("20%")

    @pytest.mark.parametrize("text, words", [("ו-5", "ו 5"), ("בְּ-5", "בְּ 5")])
    def test_phonikud_reads_a_prefix_hyphen_as_no_minus_sign(self, text, words):
        assert PhonikudPhonemizer().phonemize_string(text, "he") == phonikud.phonemize(words)

    def test_phonikud_reads_a_percent_before_punctuation(self):
        assert PhonikudPhonemizer().phonemize_string("20%, 30%.", "he") == \
            phonikud.phonemize("20% , 30% .")

    def test_phonikud_still_reads_a_negative_number(self):
        assert PhonikudPhonemizer().phonemize_string("-5", "he") == phonikud.phonemize("-5")

    @pytest.mark.parametrize("mark", "#'*_@/\\&[]{}\"")
    def test_tugaphone_reads_a_number_that_touches_punctuation(self, mark):
        expected = tugaphone_reads("casa 20 casa")
        for written in (f"{mark}20", f"20{mark}", f"{mark}20{mark}"):
            assert TugaphonePhonemizer().phonemize_string(f"casa {written} casa", "pt-PT") == expected

    @pytest.mark.parametrize("mark", "#'*_@/\\&[]{}\"")
    def test_euskaphone_reads_a_number_that_touches_punctuation(self, mark):
        expected = EuskaPhonemizer().phonemize_sentence("etxe 20 etxe")
        for written in (f"20{mark}", f"{mark}20{mark}"):
            assert EuskaphonePhonemizer().phonemize_string(f"etxe {written} etxe", "eu") == expected

    def test_euskaphone_reads_the_percent_written_first(self):
        assert EuskaphonePhonemizer().phonemize_string("%20.", "eu") == \
            EuskaPhonemizer().phonemize_sentence("%20")

    def test_tugaphone_still_reads_a_negative_number_and_a_percent(self):
        assert TugaphonePhonemizer().phonemize_string("(-5) 20%.", "pt-PT") == \
            tugaphone_reads("menos cinco vinte por cento")

    @pytest.mark.parametrize("text", ["בית [בית] בית", "בית [בית בית"])
    def test_phonikud_keeps_a_word_in_brackets(self, text):
        assert PhonikudPhonemizer().phonemize_string(text, "he") == \
            phonikud.phonemize(text.replace("[", " ").replace("]", " "))

    def test_viphoneme_keeps_a_word_that_touches_an_underscore(self, monkeypatch):
        seen = []
        engine = types.ModuleType("viphoneme")
        engine.vi2IPA = lambda text: seen.append(text) or "a"
        monkeypatch.setitem(sys.modules, "viphoneme", engine)
        VIPhonemePhonemizer().phonemize_string("nhà_ nhà", "vi")
        assert seen == ["nhà  nhà"]


class TestBareNumbers:
    @pytest.mark.parametrize("text, keep_before, keep_after, expected", [
        ("#20 (30) '40'", "", "", "20 30 40"),
        ("-5, 20%.", "-", "%", "-5 20%"),
        ("-5, 20%.", "", "", "5 20"),
        ("(casa) Dr. 'a'", "", "", "(casa) Dr. 'a'"),
        ("16:30, 3,5.", "", "", "16:30 3,5"),
        ("a  #1\nb", "", "", "a  1\nb"),
        ("٢٠،", "", "", "٢٠"),
    ])
    def test_values(self, text, keep_before, keep_after, expected):
        assert BasePhonemizer.bare_numbers(text, keep_before, keep_after) == expected
