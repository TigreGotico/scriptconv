"""Frontend errors, ``PhonemizerIdentity`` and the ``owned_stages`` table."""
import dataclasses
import hashlib
import logging
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from unittest import mock

import espyak.version
import orthography2ipa
import pytest
import tugaphone.version
from orthography2ipa.exceptions import EngineSourceUnavailable
from packaging.requirements import Requirement

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
    get_phonemizer_class,
)
from scriptconv.phonemizers.africa import AfricaG2PPhonemizer
from scriptconv.phonemizers.ar import MantoqPhonemizer
from scriptconv.phonemizers.eu import EuskaphonePhonemizer
from scriptconv.phonemizers.ghana import GhanaG2PPhonemizer
from scriptconv.phonemizers.ko import G2PKPhonemizer
from scriptconv.phonemizers.mul import EpitranPhonemizer, EspeakPhonemizer
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY
from scriptconv.phonemizers.vi import VIPhonemePhonemizer

ROOT = Path(__file__).resolve().parent.parent

# The table in knowledge/wiki/concepts/speech-stack-contract.md. A member not
# listed here owns no stage.
OWNED = {
    Phonemizer.TUGAPHONE: {"diacritize"},
    Phonemizer.ARBTOK: {"diacritize"},
}

# Code inside scriptconv, vendored or written here. Everything else names the
# distribution that its extra installs.
IN_TREE = {
    Phonemizer.UNICODE, Phonemizer.GRAPHEMES, Phonemizer.AFRICA_G2P,
    Phonemizer.MATOUB_KAB, Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA,
    Phonemizer.KOG2PK, Phonemizer.SHAMI, Phonemizer.VOSK, Phonemizer.BYT5,
    Phonemizer.CHARSIU,
}
# An engine that no extra can name: a binary, and a distribution the zh extra
# does not list.
OUTSIDE_THE_EXTRAS = {Phonemizer.ESPEAK: "espeak-ng", Phonemizer.G2PC: "g2pc"}


class TestErrors:
    def test_match_lang_names_the_language_it_refuses(self):
        with pytest.raises(UnsupportedLanguageError, match="unsupported language code: fi"):
            BasePhonemizer.match_lang("fi", ["pt-PT"])

    @pytest.mark.parametrize("resolve, lang", [
        (AfricaG2PPhonemizer.get_lang, "zzz"),
        (GhanaG2PPhonemizer.get_lang, "zzz"),
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

    def test_vendored_code_reports_the_scriptconv_version(self):
        from scriptconv import version
        identity = MantoqPhonemizer().identity("ar")
        assert (identity.backend, identity.distribution, identity.version) == \
            ("mantoq", "scriptconv", metadata.version("scriptconv"))
        assert identity.version == version.VERSION_STR

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

    # g2pk needs python-mecab-ko, which has no Python 3.13 wheel and needs
    # mecab-config to build, so the test extra installs g2pk below 3.13 only.
    @pytest.mark.skipif(sys.version_info >= (3, 13),
                        reason="python-mecab-ko has no Python 3.13 wheel")
    def test_g2pk_reports_the_installed_engine(self):
        assert G2PKPhonemizer().identity("ko") == PhonemizerIdentity(
            backend="g2pk", distribution="g2pk", version=metadata.version("g2pk"), lang="ko")

    def test_espeak_reports_the_binary_version(self):
        banner = "eSpeak NG text-to-speech: 1.52.0  Data at: /usr/share/espeak-ng-data\n"
        with mock.patch.object(EspeakPhonemizer, "_has_binary", return_value=True), \
                mock.patch.object(EspeakPhonemizer, "_run_espeak_command", return_value=banner):
            identity = EspeakPhonemizer().identity("pt")
        assert (identity.distribution, identity.version) == ("espeak-ng", "1.52.0")

    def test_espeak_without_the_binary_reports_the_port(self):
        with mock.patch.object(EspeakPhonemizer, "_has_binary", return_value=False):
            identity = EspeakPhonemizer().identity("pt")
        assert (identity.distribution, identity.version) == ("espyak", espyak.version.VERSION_STR)

    def test_a_preferred_port_that_is_missing_reports_the_binary(self):
        banner = "eSpeak NG text-to-speech: 1.52.0  Data at: /usr/share/espeak-ng-data"
        missing = metadata.PackageNotFoundError("espyak")
        with mock.patch.object(EspeakPhonemizer, "_has_binary", return_value=True), \
                mock.patch.object(EspeakPhonemizer, "_run_espeak_command", return_value=banner), \
                mock.patch("scriptconv.phonemizers.mul.metadata.version", side_effect=missing):
            identity = EspeakPhonemizer(prefer_espyak=True).identity("pt")
        assert (identity.distribution, identity.version) == ("espeak-ng", "1.52.0")

    def test_the_espyak_port_reports_itself(self):
        identity = EspeakPhonemizer(prefer_espyak=True).identity("pt")
        assert (identity.backend, identity.distribution, identity.version) == \
            ("espeak", "espyak", espyak.version.VERSION_STR)


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


class TestVietnameseNeedsAnOlderPython:
    def test_the_error_gives_the_reason(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "viphoneme", None)
        monkeypatch.setattr(sys, "version_info", (3, 12, 0))
        with pytest.raises(ImportError) as refused:
            VIPhonemePhonemizer()
        assert "below 3.12" in str(refused.value) and "imp" in str(refused.value)
        assert "scriptconv[vi]" not in str(refused.value)

    def test_a_python_that_can_load_it_is_told_to_install_it(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "viphoneme", None)
        monkeypatch.setattr(sys, "version_info", (3, 11, 9))
        with pytest.raises(ImportError, match=r"scriptconv\[vi\]"):
            VIPhonemePhonemizer()

    @pytest.mark.parametrize("python, installed", [("3.11", True), ("3.12", False), ("3.13", False)])
    def test_the_extra_installs_the_engine_only_where_it_loads(self, python, installed):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        engine = [Requirement(dep) for dep in project["optional-dependencies"]["vi"]
                  if not dep.startswith("scriptconv")]
        assert {dep.name for dep in engine} == {"viphoneme", "vinorm", "underthesea", "eng_to_ipa"}
        assert [dep.marker.evaluate({"python_version": python}) for dep in engine] == \
            [installed] * len(engine)


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
        extra = PHONEMIZER_REGISTRY[member][2]
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        wanted = {re.split(r"[\[<>=;~ ]", d, maxsplit=1)[0].lower().replace("_", "-")
                  for d in pyproject["project"]["optional-dependencies"][extra]}
        assert declared.lower().replace("_", "-") in wanted

    @pytest.mark.parametrize("member", sorted(IN_TREE, key=lambda m: m.value))
    def test_code_inside_scriptconv_names_no_distribution(self, member):
        assert get_phonemizer_class(member).engine_distribution is None
