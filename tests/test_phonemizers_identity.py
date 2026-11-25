"""Frontend errors, ``PhonemizerIdentity`` and the ``owned_stages`` table."""
import dataclasses
import logging
import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
import tugaphone.version

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
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend, spoken_normalizer
from scriptconv.phonemizers.eu import EuskaphonePhonemizer
from scriptconv.phonemizers.mul import EpitranPhonemizer
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY

ROOT = Path(__file__).resolve().parent.parent

# The table in knowledge/wiki/concepts/speech-stack-contract.md. A member not
# listed here owns no stage.
OWNED = {
    Phonemizer.TUGAPHONE: {"normalize", "diacritize"},
    Phonemizer.ARBTOK: {"diacritize"},
    Phonemizer.DIZIONE: {"normalize"},
    Phonemizer.EUSKAPHONE: {"normalize"},
    Phonemizer.TLTK: {"normalize"},
}

# Code written or vendored in scriptconv, scriptconv-copyleft or
# scriptconv-nonfree. Everything else names the distribution that its extra
# installs.
IN_TREE = {
    Phonemizer.UNICODE, Phonemizer.GRAPHEMES, Phonemizer.MATOUB_KAB,
    Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA, Phonemizer.KOG2PK,
    Phonemizer.SHAMI, Phonemizer.VOSK, Phonemizer.BYT5, Phonemizer.CHARSIU,
    Phonemizer.DIZIONE, Phonemizer.G2PW, Phonemizer.F5TTS_CHAR, Phonemizer.LEOKANI,
    Phonemizer.KOLOKWA, Phonemizer.HEBREW_IPA, Phonemizer.NEMO_IPA,
}
# An engine that no extra can name: a binary, and a distribution the zh extra
# does not list.
OUTSIDE_THE_EXTRAS = {Phonemizer.ESPEAK: "espeak-ng", Phonemizer.ESPEAK_LT_ACCENT: "espeak-ng",
                      Phonemizer.G2PC: "g2pc"}


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
        identity = TugaphonePhonemizer().identity("pt-pt-x-porto")
        assert identity == PhonemizerIdentity(
            backend="tugaphone", distribution="tugaphone",
            version=tugaphone.version.__version__, lang="pt-PT-x-porto", revision=identity.revision)
        assert identity.revision == (
            f"scriptconv=={metadata.version('scriptconv')};{tugaphone.revision('pt-PT-x-porto')}")

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


def installed(*names):
    """The ``;name==version`` string of each distribution, as ``importlib.metadata`` reads it."""
    return "".join(f";{name}=={metadata.version(name)}" for name in names)


class TestRevision:
    @pytest.mark.parametrize("backend", [GraphemePhonemizer(), UnicodeCodepointPhonemizer()])
    def test_code_inside_scriptconv_gives_the_scriptconv_version(self, backend):
        assert backend.identity("pt").revision == f"scriptconv=={metadata.version('scriptconv')}"

    def test_a_sister_package_follows_scriptconv_and_the_engine_comes_last(self):
        identity = get_phonemizer(Phonemizer.ESPEAK).identity("pt")
        assert identity.revision == (f"scriptconv=={metadata.version('scriptconv')}"
                                     + installed("scriptconv-copyleft") + f";espeak-ng=={identity.version}")

    def test_code_in_a_sister_package_names_it_once(self):
        revision = get_phonemizer(Phonemizer.MANTOQ).identity("ar").revision
        assert revision == f"scriptconv=={metadata.version('scriptconv')}" + installed("scriptconv-nonfree")

    def test_an_engine_distribution_follows_scriptconv(self):
        assert get_phonemizer(Phonemizer.EPITRAN).identity("rus-Cyrl").revision == \
            f"scriptconv=={metadata.version('scriptconv')}" + installed("epitran")

    def test_the_orthography2ipa_wrappers_name_the_lexicon_package(self):
        expected = f"scriptconv=={metadata.version('scriptconv')}" + installed("orthography2ipa", "o2i-lexicons")
        assert Orthography2IPAPhonemizer().identity("pt-PT").revision == expected
        assert get_phonemizer(Phonemizer.BARRANQUENHO).identity("ext-PT-x-barrancos").revision == expected
        assert get_phonemizer(Phonemizer.MIRANDESE).identity("mwl").revision == expected

    def test_tugaphone_takes_the_revision_that_tugaphone_gives(self):
        assert TugaphonePhonemizer().identity("pt-PT").revision == (
            f"scriptconv=={metadata.version('scriptconv')};{tugaphone.revision('pt-PT')}")

    def test_euskaphone_names_orthography2ipa_and_text2spoken(self):
        assert EuskaphonePhonemizer().identity("eu").revision == (
            f"scriptconv=={metadata.version('scriptconv')}"
            + installed("euskaphone", "orthography2ipa", "text2spoken"))

    @pytest.mark.parametrize("lang, pack", [("fr", "gruut-lang-fr"), ("ru", "gruut-lang-ru")])
    def test_gruut_names_the_language_pack_of_the_lect(self, lang, pack):
        assert get_phonemizer(Phonemizer.GRUUT).identity(lang).revision == \
            f"scriptconv=={metadata.version('scriptconv')}" + installed("gruut", pack)

    def test_a_data_distribution_that_is_not_installed_stays_out(self, monkeypatch):
        real = metadata.version

        def version(name):
            if name == "o2i-lexicons":
                raise metadata.PackageNotFoundError(name)
            return real(name)
        monkeypatch.setattr(metadata, "version", version)
        assert Orthography2IPAPhonemizer().identity("pt-PT").revision == \
            f"scriptconv=={real('scriptconv')}" + installed("orthography2ipa")

    def test_an_engine_that_is_not_installed_raises_import_error(self, monkeypatch):
        monkeypatch.setattr(Orthography2IPAPhonemizer, "engine_distribution", "no-such-distribution")
        with pytest.raises(ImportError):
            Orthography2IPAPhonemizer().identity("pt-PT")

    def test_a_release_of_a_data_distribution_changes_the_revision(self, monkeypatch):
        backend = Orthography2IPAPhonemizer()
        current = backend.identity("pt-PT")
        real = metadata.version
        monkeypatch.setattr(metadata, "version",
                            lambda name: "99.0" if name == "o2i-lexicons" else real(name))
        assert backend.identity("pt-PT").differs_from(current) == ("revision",)

    def test_a_release_of_the_engine_changes_the_revision_and_the_version(self, monkeypatch):
        backend = get_phonemizer(Phonemizer.EPITRAN)
        current = backend.identity("rus-Cyrl")
        monkeypatch.setattr(type(backend), "_engine_release",
                            lambda self: ("epitran", f"{current.version}.post1"))
        assert backend.identity("rus-Cyrl").differs_from(current) == ("revision", "version")

    def test_two_tugaphone_identities_log_no_missing_revision(self, caplog):
        backend = TugaphonePhonemizer()
        with caplog.at_level(logging.WARNING):
            revisions = [backend.identity(lect).revision for lect in ("pt-PT", "pt-BR")]
        assert revisions == [f"scriptconv=={metadata.version('scriptconv')};{tugaphone.revision(lect)}"
                             for lect in ("pt-PT", "pt-BR")]
        assert "gives no revision" not in caplog.text


def frontend(backend=None, lang="pt-PT", **config):
    return TextFrontend(FrontendConfig(lang, **config), backend or GraphemePhonemizer())


class TestFrontendRevision:
    def test_the_frontend_keeps_the_backend_revision_when_no_stage_adds_one(self):
        assert frontend().identity().revision == GraphemePhonemizer().identity("pt-PT").revision

    def test_text2spoken_follows_the_backend_when_it_normalises(self):
        revision = frontend(normalizer=spoken_normalizer()).identity().revision
        assert revision == (f"scriptconv=={metadata.version('scriptconv')}" + installed("text2spoken"))

    def test_normalisation_switched_off_leaves_text2spoken_out(self):
        identity = frontend(normalizer=spoken_normalizer(), stages=Stages(normalize=False)).identity()
        assert identity.revision == f"scriptconv=={metadata.version('scriptconv')}"

    def test_a_backend_that_owns_normalisation_adds_no_second_text2spoken(self):
        identity = frontend(TugaphonePhonemizer(), normalizer=spoken_normalizer()).identity()
        assert identity.revision == TugaphonePhonemizer().identity("pt-PT").revision

    def test_another_normaliser_gives_no_revision(self):
        assert frontend(normalizer=lambda text, lang: text.upper()).identity().revision is None

    def test_a_casing_gives_no_revision(self):
        assert frontend(stages=Stages(casing=str.upper)).identity().revision is None

    def test_a_diacritizer_follows_the_backend(self):
        identity = frontend(lang="ar").identity()
        assert identity.revision == f"scriptconv=={metadata.version('scriptconv')}" + installed("text2tashkeel")

    def test_a_diacritizer_model_gives_no_revision(self):
        assert frontend(lang="ar", stages=Stages(diacritizer_model="rawi-ensemble")).identity().revision is None

    def test_a_release_of_text2spoken_changes_the_frontend_revision(self, monkeypatch):
        backend, config = GraphemePhonemizer(), FrontendConfig("pt-PT", normalizer=spoken_normalizer())
        current = TextFrontend(config, backend).identity()
        real = metadata.version
        monkeypatch.setattr(metadata, "version", lambda name: "99.0" if name == "text2spoken" else real(name))
        assert TextFrontend(config, backend).identity().differs_from(current) == ("revision",)


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
