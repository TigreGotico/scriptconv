"""Frontend errors, ``PhonemizerIdentity`` and the ``owned_stages`` table."""
import dataclasses
import hashlib
import logging
import os
import re
import subprocess
import sys
import tomllib
import unicodedata
from importlib import metadata
from pathlib import Path
from types import MappingProxyType

import orthography2ipa
import pytest
import tugaphone.version
from orthography2ipa.exceptions import EngineSourceUnavailable

from scriptconv.phonemizers import (
    BasePhonemizer,
    FrontendError,
    GraphemePhonemizer,
    ModelUnavailableError,
    Phonemizer,
    PhonemizerIdentity,
    StageError,
    UnicodeCodepointPhonemizer,
    UnreadTextError,
    UnsupportedLanguageError,
    get_phonemizer,
    get_phonemizer_class,
)
from scriptconv.phonemizers._vendored import matoub_kab
from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
from scriptconv.phonemizers.eu import EuskaphonePhonemizer
from scriptconv.phonemizers.mul import EpitranPhonemizer
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY

ROOT = Path(__file__).resolve().parent.parent

# The table in knowledge/wiki/concepts/speech-stack-contract.md. A member not
# listed here owns no stage.
OWNED = {
    Phonemizer.TUGAPHONE: {"diacritize"},
    Phonemizer.ARBTOK: {"diacritize"},
    Phonemizer.DIZIONE: {"normalize"},
}

# Code written or vendored in scriptconv, scriptconv-copyleft or
# scriptconv-nonfree. Everything else names the distribution that its extra
# installs.
IN_TREE = {
    Phonemizer.UNICODE, Phonemizer.GRAPHEMES, Phonemizer.MATOUB_KAB,
    Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA, Phonemizer.KOG2PK,
    Phonemizer.SHAMI, Phonemizer.VOSK, Phonemizer.BYT5, Phonemizer.CHARSIU,
    Phonemizer.DIZIONE, Phonemizer.G2PW, Phonemizer.F5TTS_CHAR,
}
# An engine that no extra can name: a binary, and a distribution the zh extra
# does not list.
OUTSIDE_THE_EXTRAS = {Phonemizer.ESPEAK: "espeak-ng", Phonemizer.G2PC: "g2pc"}


class TestErrors:
    def test_match_lang_names_the_language_it_refuses(self):
        with pytest.raises(UnsupportedLanguageError, match="unsupported language code: fi"):
            BasePhonemizer.match_lang("fi", ["pt-PT"])

    @pytest.mark.parametrize("resolve, lang", [
        (EuskaphonePhonemizer.get_lang, "pt"),
        (Orthography2IPAPhonemizer.get_lang, "zzz"),
        (EpitranPhonemizer.get_lang, "ja"),
    ])
    def test_each_wrapper_with_its_own_check_raises_the_same_error(self, resolve, lang):
        with pytest.raises(UnsupportedLanguageError, match=lang):
            resolve(lang)

    @pytest.mark.parametrize("error", [UnsupportedLanguageError, StageError,
                                       UnreadTextError, ModelUnavailableError])
    def test_one_except_clause_catches_every_error(self, error):
        with pytest.raises(FrontendError, match="boom"):
            raise error("boom")

    def test_existing_value_error_handlers_keep_working(self):
        with pytest.raises(ValueError):
            BasePhonemizer.match_lang("fi", ["pt-PT"])

    def test_unread_text_carries_the_pieces_it_could_not_read(self):
        assert UnreadTextError("no phonemes", unread=["123", "abc"]).unread == ("123", "abc")
        assert UnreadTextError("no phonemes").unread == ()


class TestDiffersFrom:
    BASE = dict(backend="tugaphone", distribution="tugaphone", version="1.4.0a2",
                lang="pt-PT", revision="sha256:ab12")

    def test_equal_identities_differ_in_nothing(self):
        assert PhonemizerIdentity(**self.BASE).differs_from(
            PhonemizerIdentity(**self.BASE)) == ()

    @pytest.mark.parametrize("field, value", [
        ("backend", "espeak"), ("distribution", "espeak-ng"), ("lang", "pt-BR"),
        ("revision", None),
    ])
    def test_each_field_is_compared(self, field, value):
        other = PhonemizerIdentity(**{**self.BASE, field: value})
        assert PhonemizerIdentity(**self.BASE).differs_from(other) == (field,)

    def test_revision_comes_first(self):
        other = PhonemizerIdentity(**{**self.BASE, "revision": "sha256:cd34",
                                      "version": "1.4.0a3", "lang": "pt-BR"})
        assert PhonemizerIdentity(**self.BASE).differs_from(other) == \
            ("revision", "version", "lang")

    def test_an_equal_revision_hides_a_version_change(self):
        other = PhonemizerIdentity(**{**self.BASE, "version": "1.4.0a3"})
        assert PhonemizerIdentity(**self.BASE).differs_from(other) == ()

    def test_an_equal_revision_hides_only_the_version(self):
        other = PhonemizerIdentity(**{**self.BASE, "version": "1.4.0a3", "lang": "pt-BR"})
        assert PhonemizerIdentity(**self.BASE).differs_from(other) == ("lang",)

    def test_a_version_change_shows_when_no_revision_exists(self):
        base = {**self.BASE, "revision": None}
        other = PhonemizerIdentity(**{**base, "version": "1.4.0a3"})
        assert PhonemizerIdentity(**base).differs_from(other) == ("version",)

    def test_a_version_change_shows_when_one_side_has_no_revision(self):
        other = PhonemizerIdentity(**{**self.BASE, "revision": None, "version": "1.4.0a3"})
        assert PhonemizerIdentity(**self.BASE).differs_from(other) == ("revision", "version")

    def test_an_identity_cannot_change(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            PhonemizerIdentity(**self.BASE).version = "2"


class TestIdentity:
    def test_a_wrapper_names_its_engine_and_the_resolved_lect(self):
        assert TugaphonePhonemizer().identity("pt-pt-x-porto") == PhonemizerIdentity(
            backend="tugaphone", distribution="tugaphone",
            version=tugaphone.version.__version__, lang="pt-PT-x-porto", revision=None)

    @pytest.mark.parametrize("member, lang, distribution", [
        (Phonemizer.MANTOQ, "ar", "scriptconv-nonfree"),
        (Phonemizer.KOG2PK, "ko", "scriptconv-copyleft"),
    ])
    def test_code_vendored_in_a_sister_package_reports_that_package(self, member, lang,
                                                                     distribution):
        identity = get_phonemizer(member).identity(lang)
        assert (identity.backend, identity.distribution, identity.version) == \
            (member.value, distribution, metadata.version(distribution))

    @pytest.mark.parametrize("phonemizer", [GraphemePhonemizer(), UnicodeCodepointPhonemizer()])
    def test_a_backend_with_no_get_lang_keeps_the_language_it_was_given(self, phonemizer):
        assert phonemizer.identity("xx-YY").lang == "xx-YY"

    def test_an_unsupported_language_is_refused(self):
        with pytest.raises(UnsupportedLanguageError):
            TugaphonePhonemizer().identity("fi")

    def test_a_subclass_of_a_registered_backend_keeps_its_name(self):
        class Tuned(TugaphonePhonemizer):
            pass
        assert Tuned().identity("pt-PT").backend == "tugaphone"

    def test_an_unregistered_backend_reports_its_class_name(self):
        class Custom(BasePhonemizer):
            def phonemize_string(self, text, lang):
                return text
        assert Custom().identity("pt").backend == "Custom"


class TestOrthography2IPARevision:
    @staticmethod
    def with_lexicon(lang):
        """The spec revision and the lexicon revision of *lang*, hashed together."""
        patches = lang in orthography2ipa.packaged_lexicon_sources(patches=True)
        combined = (f"{orthography2ipa.spec_revision(lang)}\n"
                    f"{orthography2ipa.lexicon_revision(lang, patches=patches)}")
        return "sha256:" + hashlib.sha256(combined.encode()).hexdigest()

    def test_a_lect_with_no_lexicon_reports_the_spec_revision(self):
        assert "gl-ES" not in orthography2ipa.packaged_lexicon_sources()
        identity = Orthography2IPAPhonemizer().identity("gl")
        assert (identity.lang, identity.revision) == \
            ("gl-ES", orthography2ipa.spec_revision("gl-ES"))

    def test_a_packaged_lexicon_changes_the_revision(self):
        assert "pt-PT" in orthography2ipa.packaged_lexicon_sources()
        revision = Orthography2IPAPhonemizer().identity("pt-PT").revision
        assert revision != orthography2ipa.spec_revision("pt-PT")
        assert revision == self.with_lexicon("pt-PT")

    def test_an_engine_without_packaged_lexicons_reports_the_spec_revision(self):
        identity = Orthography2IPAPhonemizer(packaged_lexicons=False).identity("pt-PT")
        assert identity.revision == orthography2ipa.spec_revision("pt-PT")

    def test_two_calls_give_equal_identities(self):
        phonemizer = Orthography2IPAPhonemizer()
        first = phonemizer.identity("pt-PT")
        phonemizer.phonemize_string("olá", "pt-PT")
        second = phonemizer.identity("pt-PT")
        assert first == second
        assert second.revision == self.with_lexicon("pt-PT")

    def test_a_missing_engine_source_gives_no_revision_and_a_warning(self, monkeypatch, caplog):
        def unavailable(code):
            raise EngineSourceUnavailable("engine source of g2p.py is missing")
        monkeypatch.setattr(orthography2ipa, "spec_revision", unavailable)
        with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.o2ipa"):
            identity = Orthography2IPAPhonemizer().identity("gl")
        assert identity.revision is None
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "engine source" in warnings[0] and "g2p.py is missing" in warnings[0]

    def test_an_equal_revision_hides_an_engine_upgrade(self):
        current = Orthography2IPAPhonemizer().identity("gl")
        upgraded = dataclasses.replace(current, version="99.0.0")
        assert current.differs_from(upgraded) == ()


# Each backend whose revision hashes the tables that scriptconv ships, as
# source text for a fresh process, with a language it reads.
TABLE_BACKENDS = [
    ("GraphemePhonemizer()", "en"),
    ("GraphemePhonemizer(stress_notation='plus')", "ru"),
    ("GraphemePhonemizer(stress_notation='none')", "uk"),
    ("UnicodeCodepointPhonemizer()", "xx"),
    ("UnicodeCodepointPhonemizer('NFKC')", "xx"),
    ("MatoubKabylePhonemizer()", "kab"),
]
REVISIONS = f"""
from scriptconv.phonemizers import GraphemePhonemizer, UnicodeCodepointPhonemizer
from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
for source, lang in {TABLE_BACKENDS!r}:
    print(eval(source).identity(lang).revision)
"""


def grapheme_mutant(**rules):
    """A grapheme backend with *rules* in place of its own, in a subclass."""
    return type("Mutant", (GraphemePhonemizer,), rules)()


class TestTableRevision:
    def test_the_revision_is_the_same_in_every_process(self):
        runs = [subprocess.run([sys.executable, "-c", REVISIONS], cwd=ROOT, check=True,
                               capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": seed}).stdout.split()
                for seed in ("0", "1", "4242")]
        assert len(runs[0]) == len(TABLE_BACKENDS)
        assert all(revision.startswith("sha256:") for revision in runs[0])
        assert runs[0] == runs[1] == runs[2]
        assert len(set(runs[0])) == len(TABLE_BACKENDS)

    @pytest.mark.parametrize("source, lang", TABLE_BACKENDS)
    def test_an_equal_revision_hides_a_scriptconv_upgrade(self, source, lang):
        current = eval(source).identity(lang)
        upgraded = dataclasses.replace(eval(source).identity(lang), version="0.0.4a999")
        assert current.revision is not None
        assert current.differs_from(upgraded) == ()

    @pytest.mark.parametrize("rules, text, before, after", [
        ({"replace_chars": MappingProxyType({";": ".", "-": " ", ":": ","})},
         "a;b", "a,b", "a.b"),
        ({"drop_chars": "<>()[]"}, 'say "hi"',
         "say hi", 'say "hi"'),
        ({"in_word_chars": ""}, "motse-moholo", "motse-moholo", "motse moholo"),
        ({"lowercase": False}, "Ab", "ab", "Ab"),
        ({"whitespace_re": re.compile(" +")}, "a\tb", "a b", "a\tb"),
    ])
    def test_a_grapheme_rule_change_changes_the_output_and_the_revision(self, rules, text,
                                                                        before, after):
        original, mutant = GraphemePhonemizer(), grapheme_mutant(**rules)
        assert (original.phonemize_string(text, "en"), mutant.phonemize_string(text, "en")) == \
            (before, after)
        assert original.identity("en").revision is not None
        assert mutant.identity("en").revision != original.identity("en").revision

    def test_the_order_of_the_dropped_characters_does_not_change_the_revision(self):
        reordered = grapheme_mutant(drop_chars='"][)(><')
        assert GraphemePhonemizer().identity("en").revision is not None
        assert reordered.identity("en").revision == GraphemePhonemizer().identity("en").revision

    def test_the_stress_notation_changes_the_revision(self):
        revisions = {GraphemePhonemizer(stress_notation=notation).identity("ru").revision
                     for notation in GraphemePhonemizer.STRESS_NOTATIONS}
        assert None not in revisions and len(revisions) == 3

    def test_the_normalisation_form_changes_the_revision(self):
        revisions = {UnicodeCodepointPhonemizer(form).identity("xx").revision
                     for form in ("NFC", "NFD", "NFKC", "NFKD")}
        assert None not in revisions and len(revisions) == 4

    @pytest.mark.parametrize("source, lang", TABLE_BACKENDS)
    def test_another_unicode_version_changes_the_revision(self, source, lang, monkeypatch):
        current = eval(source).identity(lang).revision
        monkeypatch.setattr(unicodedata, "unidata_version", "1.1.0")
        assert current is not None
        assert eval(source).identity(lang).revision != current

    @pytest.mark.parametrize("table, key, value", [
        ("PLAIN", "a", "a"), ("SPIRANTS", "t", ("t", "t")), ("FOLD", "t\u0361\u0283", "t\u0283"),
    ])
    def test_a_kabyle_table_change_changes_the_output_and_the_revision(self, table, key, value,
                                                                       monkeypatch):
        phonemizer = MatoubKabylePhonemizer()
        current = (phonemizer.phonemize_string("taddart čay", "kab"),
                   phonemizer.identity("kab").revision)
        original = getattr(matoub_kab, table)
        monkeypatch.setattr(matoub_kab, table, {**original, key: value})
        mutant = (phonemizer.phonemize_string("taddart čay", "kab"),
                  phonemizer.identity("kab").revision)
        assert original[key] != value
        assert current[1] is not None
        assert mutant[0] != current[0] and mutant[1] != current[1]


class TestDeclarations:
    @pytest.mark.parametrize("member", list(Phonemizer))
    def test_owned_stages_match_the_contract_table(self, member):
        assert get_phonemizer_class(member).owned_stages == frozenset(OWNED.get(member, ()))

    @pytest.mark.parametrize("member", [m for m in Phonemizer if m not in IN_TREE])
    def test_engine_distribution_comes_from_the_extra(self, member):
        declared = get_phonemizer_class(member).engine_distribution
        if member in OUTSIDE_THE_EXTRAS:
            assert declared == OUTSIDE_THE_EXTRAS[member]
            return
        module, _, extra = PHONEMIZER_REGISTRY[member]
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        wanted = {re.split(r"[\[<>=;~ ]", d, maxsplit=1)[0].lower().replace("_", "-")
                  for d in pyproject["project"]["optional-dependencies"][extra]}
        package = module.partition(".")[0]
        if package != "scriptconv":
            # the sister package declares the engine in its own extra
            assert package.replace("_", "-") in wanted
            return
        assert declared.lower().replace("_", "-") in wanted

    @pytest.mark.parametrize("member", sorted(IN_TREE, key=lambda m: m.value))
    def test_code_inside_scriptconv_names_no_distribution(self, member):
        assert get_phonemizer_class(member).engine_distribution is None
