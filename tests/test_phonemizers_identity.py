"""Frontend errors, ``PhonemizerIdentity`` and the ``owned_stages`` table."""
import dataclasses
import hashlib
import logging
import re
import tomllib
from importlib import metadata
from pathlib import Path

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
    Phonemizer.UNICODE, Phonemizer.GRAPHEMES, Phonemizer.AFRICA_G2P,
    Phonemizer.MATOUB_KAB, Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA,
    Phonemizer.KOG2PK, Phonemizer.SHAMI, Phonemizer.VOSK, Phonemizer.BYT5,
    Phonemizer.CHARSIU, Phonemizer.DIZIONE, Phonemizer.G2PW,
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
        (Phonemizer.AFRICA_G2P, "yor", "scriptconv-nonfree"),
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
