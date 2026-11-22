"""Frontend errors, ``PhonemizerIdentity`` and the ``owned_stages`` table."""
import dataclasses
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import unicodedata
import zipfile
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
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend, spoken_normalizer
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
    Phonemizer.TUGAPHONE: {"normalize", "diacritize"},
    Phonemizer.ARBTOK: {"diacritize"},
    Phonemizer.DIZIONE: {"normalize"},
    Phonemizer.EUSKAPHONE: {"normalize"},
}

# Code written or vendored in scriptconv, scriptconv-copyleft or
# scriptconv-nonfree. Everything else names the distribution that its extra
# installs.
IN_TREE = {
    Phonemizer.UNICODE, Phonemizer.GRAPHEMES, Phonemizer.MATOUB_KAB,
    Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA, Phonemizer.KOG2PK,
    Phonemizer.SHAMI, Phonemizer.VOSK, Phonemizer.BYT5, Phonemizer.CHARSIU,
    Phonemizer.DIZIONE, Phonemizer.G2PW, Phonemizer.F5TTS_CHAR, Phonemizer.LEOKANI,
    Phonemizer.KOLOKWA,
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
        assert identity.revision.startswith("sc1:")

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
    def test_the_revision_holds_the_spec_revision(self, monkeypatch):
        first = Orthography2IPAPhonemizer().identity("gl")
        monkeypatch.setattr(orthography2ipa, "spec_revision", lambda code: "sha256:other")
        second = Orthography2IPAPhonemizer().identity("gl")
        assert first.lang == "gl-ES" and first.revision.startswith("sc1:")
        assert second.revision.startswith("sc1:") and second.revision != first.revision

    def test_a_packaged_lexicon_changes_the_revision(self, monkeypatch):
        assert "pt-PT" in orthography2ipa.packaged_lexicon_sources()
        with_lexicon = Orthography2IPAPhonemizer().identity("pt-PT").revision
        rules_only = Orthography2IPAPhonemizer(packaged_lexicons=False).identity("pt-PT").revision
        monkeypatch.setattr(orthography2ipa, "lexicon_revision", lambda code, patches: "other")
        other_lexicon = Orthography2IPAPhonemizer().identity("pt-PT").revision
        assert None not in (with_lexicon, rules_only, other_lexicon)
        assert len({with_lexicon, rules_only, other_lexicon}) == 3

    def test_the_engine_files_leave_the_hash(self):
        assert Orthography2IPAPhonemizer()._covered_distributions("pt-PT") == \
            {"orthography2ipa", "o2i-lexicons"}
        assert Orthography2IPAPhonemizer(packaged_lexicons=False)._covered_distributions("pt-PT") == \
            {"orthography2ipa"}
        assert Orthography2IPAPhonemizer()._covered_distributions("gl") == {"orthography2ipa"}

    def test_two_calls_give_equal_identities(self):
        phonemizer = Orthography2IPAPhonemizer()
        first = phonemizer.identity("pt-PT")
        phonemizer.phonemize_string("olá", "pt-PT")
        second = phonemizer.identity("pt-PT")
        assert first == second
        assert second.revision.startswith("sc1:")

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
        assert current.revision is not None
        assert current.differs_from(upgraded) == ()


@pytest.fixture
def fresh_tugaphone():
    """No ``tugaphone.revision`` kept by an earlier test, and none kept after this one."""
    from scriptconv.phonemizers import pt
    cache = getattr(pt, "_tugaphone_revision", None)
    if cache is not None:
        cache.cache_clear()
    yield
    if cache is not None:
        cache.cache_clear()


def hashed_tops(monkeypatch):
    """The names that :func:`_revision._top_level_digest` hashes from here on."""
    from scriptconv.phonemizers import _revision
    tops = []
    digest = _revision._top_level_digest

    def recorded(name):
        tops.append(name)
        return digest(name)
    monkeypatch.setattr(_revision, "_top_level_digest", recorded)
    return tops


@pytest.mark.usefixtures("fresh_tugaphone")
class TestTugaphoneRevision:
    def test_the_revision_holds_the_tugaphone_revision(self, monkeypatch):
        from scriptconv.phonemizers import pt
        monkeypatch.setattr(tugaphone, "revision", lambda lang: "tp1:one")
        first = TugaphonePhonemizer().identity("pt-PT").revision
        pt._tugaphone_revision.cache_clear()
        monkeypatch.setattr(tugaphone, "revision", lambda lang: "tp1:two")
        second = TugaphonePhonemizer().identity("pt-PT").revision
        assert first.startswith("sc1:") and second.startswith("sc1:")
        assert first != second

    def test_the_lect_changes_the_revision(self):
        revisions = {TugaphonePhonemizer().identity(lect).revision
                     for lect in ("pt-PT", "pt-BR", "pt-PT-x-porto")}
        assert None not in revisions and len(revisions) == 3

    def test_an_equal_revision_hides_a_tugaphone_upgrade(self, monkeypatch):
        from scriptconv.phonemizers import base
        current = TugaphonePhonemizer().identity("pt-PT")
        installed = metadata.version
        monkeypatch.setattr(base.metadata, "version",
                            lambda name: "99.0.0" if name == "tugaphone" else installed(name))
        upgraded = TugaphonePhonemizer().identity("pt-PT")
        assert current.revision is not None and upgraded.version == "99.0.0"
        assert current.revision == upgraded.revision
        assert current.differs_from(upgraded) == ()

    def test_the_tugaphone_files_leave_the_hash(self, monkeypatch):
        from scriptconv.phonemizers import _revision
        _revision._probe_outcome.cache_clear()
        tops = hashed_tops(monkeypatch)
        assert TugaphonePhonemizer().identity("pt-PT").revision is not None
        assert TextFrontend(FrontendConfig("pt-PT"), TugaphonePhonemizer()).identity().revision is not None
        covered = {_revision._canonical(name)
                   for name in TugaphonePhonemizer()._covered_distributions("pt-PT")}
        assert covered
        assert not covered & {_revision._canonical(name) for name in tops}
        assert not {"tugaphone", "orthography2ipa", "o2i_lexicons"} & set(tops)

    def test_a_tugaphone_revision_error_gives_no_revision_and_one_warning(self, monkeypatch, caplog):
        def fails(lang):
            raise tugaphone.RevisionError("the revision probe for 'pt-PT' did not finish in 120 s")
        monkeypatch.setattr(tugaphone, "revision", fails)
        with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers.pt"):
            identities = [TugaphonePhonemizer().identity("pt-PT") for _ in range(3)]
        assert [identity.revision for identity in identities] == [None] * 3
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "RevisionError" in warnings[0] and "did not finish in 120 s" in warnings[0]

    def test_a_contact_other_than_none_gives_no_revision(self):
        mixed = TugaphonePhonemizer()
        mixed.contact = "en"
        assert TugaphonePhonemizer().identity("pt-PT").revision is not None
        assert mixed.identity("pt-PT").revision is None
        # the policy reaches tugaphone and changes the output
        assert mixed.phonemize_string("o weekend", "pt-PT") == \
            tugaphone.TugaPhonemizer().phonemize_sentence("o weekend", "pt-PT", contact="en")
        assert mixed.phonemize_string("o weekend", "pt-PT") != \
            TugaphonePhonemizer().phonemize_string("o weekend", "pt-PT")


# Each backend whose revision hashes the code and data on its path, as source
# text for a fresh process, with a language it reads.
CODE_BACKENDS = {
    "graphemes": ("GraphemePhonemizer()", "ru"),
    "graphemes-plus": ("GraphemePhonemizer(stress_notation='plus')", "ru"),
    "graphemes-none": ("GraphemePhonemizer(stress_notation='none')", "uk"),
    "unicode": ("UnicodeCodepointPhonemizer()", "xx"),
    "unicode-nfkc": ("UnicodeCodepointPhonemizer('NFKC')", "xx"),
    "matoub_kab": ("MatoubKabylePhonemizer()", "kab"),
}
# Each frontend whose revision hashes the code on its path, with its backend.
CODE_FRONTENDS = {
    "frontend-graphemes": ("GraphemePhonemizer()", "pt-PT"),
    "frontend-unicode": ("UnicodeCodepointPhonemizer()", "pt-PT"),
}
# Each backend that wraps an engine with a revision of its own, and a frontend
# that reads through one.
WRAPPER_BACKENDS = {
    "tugaphone": ("TugaphonePhonemizer()", "pt-PT"),
    "orthography2ipa": ("Orthography2IPAPhonemizer()", "pt-PT"),
    "barranquenho": ("BarranquenhoPhonemizer()", "ext-PT-x-barrancos"),
    "mirandese": ("MirandesePhonemizer()", "mwl-x-sendim"),
    "dizione": ("DizionePhonemizer()", "en-US"),
}
WRAPPER_FRONTENDS = {"frontend-tugaphone": ("TugaphonePhonemizer()", "pt-PT")}


def revisions_script(backends, frontends, imports=""):
    """Python source that prints the revision of each of *backends* and *frontends*. *imports* holds the import
    lines that only these backends need, so a mutant of another module cannot break their import."""
    return f"""
import json, scriptconv
from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import GraphemePhonemizer, UnicodeCodepointPhonemizer
from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
from scriptconv.phonemizers.mwl import MirandesePhonemizer
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
from scriptconv.phonemizers.pt import BarranquenhoPhonemizer, TugaphonePhonemizer
{imports}
revisions = {{name: eval(source).identity(lang).revision for name, (source, lang) in {backends!r}.items()}}
revisions.update({{name: TextFrontend(FrontendConfig(lang), eval(source)).identity().revision
                  for name, (source, lang) in {frontends!r}.items()}})
print(json.dumps({{"scriptconv": scriptconv.__file__, **revisions}}))
"""


REVISIONS = revisions_script(CODE_BACKENDS, CODE_FRONTENDS)
WRAPPER_REVISIONS = revisions_script(WRAPPER_BACKENDS, WRAPPER_FRONTENDS,
                                     "from scriptconv.phonemizers.dizione import DizionePhonemizer")
SCRIPTCONV = Path(sys.modules["scriptconv"].__file__).parent

# Edits of the scriptconv source, (file, old text, new text), on the path of the
# named backend or frontend. Each edit but F4 changes its output for some input.
# F4 edits a module that the frontend loads and calls only when it diacritizes.
CODE_MUTANTS = {
    "G1 the letter test before a hyphen skips no combining mark": (
        "graphemes", "phonemizers/base.py",
        '    while letter > 0 and unicodedata.category(text[letter]).startswith("M"):',
        "    while False:"),
    "G2 the whitespace pattern takes re.ASCII": (
        "graphemes", "phonemizers/base.py",
        'whitespace_re = re.compile(r"\\s+")', 'whitespace_re = re.compile(r"\\s+", re.ASCII)'),
    "G3 the plus notation writes the sign after the vowel": (
        "graphemes-plus", "diacritics.py",
        "out.insert(base, before)\n            base += 1\n            out.append(after)",
        "out.insert(base, after)\n            base += 1\n            out.append(before)"),
    "P1 no mark separates two words": (
        "graphemes", "phonemizers/base.py",
        "_SEPARATING_MARKS = frozenset(mark", "_SEPARATING_MARKS = frozenset() and frozenset(mark"),
    "P2 a colon between digits is punctuation": (
        "unicode", "phonemizers/base.py",
        "and chars[i - 1].isdigit() and chars[i + 1].isdigit():", "and False:"),
    "P3 a semicolon is kept as a comma": (
        "unicode", "phonemizers/base.py", '":": ":", ";": ";",', '":": ":", ";": ",",'),
    "P4 a semicolon is kept as a comma, Kabyle": (
        "matoub_kab", "phonemizers/base.py", '":": ":", ";": ";",', '":": ":", ";": ",",'),
    "P5 no mark separates two words, Kabyle": (
        "matoub_kab", "phonemizers/base.py",
        "_SEPARATING_MARKS = frozenset(mark", "_SEPARATING_MARKS = frozenset() and frozenset(mark"),
    "K1 a doubled vowel is long": (
        "matoub_kab", "phonemizers/_vendored/matoub_kab/__init__.py",
        "word[index + 1] == char and char not in VOWELS", "word[index + 1] == char"),
    "F3 a block of whitespace cuts the text": (
        "frontend-graphemes", "frontend.py", "if block[2:-2].strip():", "if block[2:-2]:"),
    "F4 a diacritics change on the frontend path": (
        "frontend-unicode", "diacritics.py",
        '**dict.fromkeys(("lv", "sl", "az-Latn", "uz-Latn"), "Latn"),',
        '**dict.fromkeys(("lv", "sl", "az-Latn", "uz-Latn", "pt"), "Latn"),'),
    "K2 Kabyle carries stress marks": (
        "matoub_kab", "diacritics.py",
        '**dict.fromkeys(("lv", "sl", "az-Latn", "uz-Latn"), "Latn"),',
        '**dict.fromkeys(("lv", "sl", "az-Latn", "uz-Latn", "kab"), "Latn"),'),
}
# Edits that change no output: a docstring and a comment, the version, and
# the code of another backend.
NEUTRAL_EDITS = {
    "a docstring and a comment": (
        "phonemizers/base.py",
        '    """Whether the character at *index* of *text* stands between two letters.\n',
        '    """Whether the character at *index* of *text* stands between two letters, or not.\n'
        "    # a comment\n"),
    "version.py": ("version.py", "VERSION_ALPHA = ", "VERSION_ALPHA = 999 + "),
    "the code of another backend": (
        "phonemizers/zh.py", "\nclass JiebaPhonemizer(", "\nANSWER = 42\n\n\nclass JiebaPhonemizer("),
}


def revisions_in_a_copy(directory, edit=None, script=REVISIONS):
    """The revisions that *script* prints, in a fresh process, from a copy of
    the scriptconv package with *edit* ``(file, old, new)`` applied."""
    tree = directory / "tree"
    shutil.copytree(SCRIPTCONV, tree / "scriptconv", ignore=shutil.ignore_patterns("__pycache__"))
    if edit is not None:
        target, old, new = edit
        path = tree / "scriptconv" / target
        source = path.read_text(encoding="utf-8")
        assert source.count(old) == 1, f"{old!r} is not in {target} once"
        path.write_text(source.replace(old, new), encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", script], cwd=tree, check=True,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1",
                               "XDG_CACHE_HOME": str(directory / "cache")})
    revisions = json.loads(done.stdout.splitlines()[-1])
    assert Path(revisions.pop("scriptconv")).is_relative_to(tree)
    return revisions


GRAPHEMES_REVISION = """
import json, scriptconv
from scriptconv.frontend import FrontendConfig, TextFrontend
from scriptconv.phonemizers import GraphemePhonemizer
revision = TextFrontend(FrontendConfig("pt-PT"), GraphemePhonemizer()).identity().revision
print(json.dumps({"scriptconv": scriptconv.__file__, "graphemes": revision}))
"""


def test_a_fresh_process_of_the_tests_keeps_its_identities_out_of_the_user_cache(tmp_path, monkeypatch):
    user = tmp_path / "user-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(user))
    assert revisions_in_a_copy(tmp_path, script=GRAPHEMES_REVISION)["graphemes"].startswith("sc1:")
    assert not (user / "scriptconv" / "identity").exists()
    assert list((tmp_path / "cache" / "scriptconv" / "identity").glob("*.json"))


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    return revisions_in_a_copy(tmp_path_factory.mktemp("pristine"))


class LongVowel(GraphemePhonemizer):
    """Graphemes, with ":" after each "a"."""

    def phonemize_string(self, text, lang):
        return super().phonemize_string(text, lang).replace("a", "a:")


class OwnLazy(GraphemePhonemizer):
    """Graphemes, with a ``phonemize_lazy`` of its own, so ``keep_punctuation`` changes nothing."""

    def phonemize_lazy(self, text, lang):
        yield list(self.phonemize_string(text, lang))


# The revision of a grapheme backend with instance settings, in a fresh process.
INSTANCE_SETTINGS_REVISION = """
import json, re
from scriptconv.phonemizers import GraphemePhonemizer
backend = GraphemePhonemizer()
backend.keep_punctuation = True
backend.whitespace_re = re.compile(r"\\s+", re.ASCII)
print(json.dumps(backend.identity("ru").revision))
"""


class TestCodeRevision:
    def test_the_revision_is_the_same_in_every_process(self, tmp_path):
        runs = [subprocess.run([sys.executable, "-c", REVISIONS], cwd=ROOT, check=True,
                               capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": seed,
                                    "XDG_CACHE_HOME": str(tmp_path / seed)}).stdout.splitlines()[-1]
                for seed in ("0", "1", "4242")]
        revisions = json.loads(runs[0])
        revisions.pop("scriptconv")
        assert all(revision.startswith("sc1:") for revision in revisions.values())
        assert runs[0] == runs[1] == runs[2]
        assert len(set(revisions.values())) == len(CODE_BACKENDS) + len(CODE_FRONTENDS)

    @pytest.mark.parametrize("source, lang", CODE_BACKENDS.values(), ids=CODE_BACKENDS)
    def test_an_equal_revision_hides_a_scriptconv_upgrade(self, source, lang):
        current = eval(source).identity(lang)
        upgraded = dataclasses.replace(eval(source).identity(lang), version="0.0.4a999")
        assert current.revision is not None
        assert current.differs_from(upgraded) == ()

    @pytest.mark.parametrize("mutant", CODE_MUTANTS)
    def test_a_code_change_on_the_path_changes_the_revision(self, mutant, pristine, tmp_path):
        backend, *edit = CODE_MUTANTS[mutant]
        assert pristine[backend] is not None
        assert revisions_in_a_copy(tmp_path, edit)[backend] != pristine[backend]

    @pytest.mark.parametrize("edit", NEUTRAL_EDITS)
    def test_an_edit_that_changes_no_output_keeps_every_revision(self, edit, pristine, tmp_path):
        assert None not in pristine.values()
        assert revisions_in_a_copy(tmp_path, NEUTRAL_EDITS[edit]) == pristine

    def test_a_subclass_with_its_own_method_has_its_own_revision(self):
        assert LongVowel().phonemize_string("casa", "en") != GraphemePhonemizer().phonemize_string("casa", "en")
        assert GraphemePhonemizer().identity("en").revision is not None
        assert LongVowel().identity("en").revision != GraphemePhonemizer().identity("en").revision

    @pytest.mark.parametrize("name, value, text, before, after", [
        ("replace_chars", MappingProxyType({";": ".", "-": " ", ":": ","}), "a;b", "a,b", "a.b"),
        ("drop_chars", "<>()[]", 'say "hi"', "say hi", 'say "hi"'),
        ("in_word_chars", "", "motse-moholo", "motse-moholo", "motse moholo"),
        ("lowercase", False, "Ab", "ab", "Ab"),
    ])
    def test_a_character_rule_set_on_the_instance_changes_the_revision(self, name, value, text,
                                                                       before, after):
        original, changed = GraphemePhonemizer(), GraphemePhonemizer()
        setattr(changed, name, value)
        assert (original.phonemize_string(text, "en"), changed.phonemize_string(text, "en")) == \
            (before, after)
        assert original.identity("en").revision is not None
        assert changed.identity("en").revision != original.identity("en").revision

    def test_a_rule_set_on_the_instance_to_its_default_keeps_the_revision(self):
        changed = GraphemePhonemizer()
        changed.drop_chars = '<>()[]"'
        changed.replace_chars = {";": ",", "-": " ", ":": ","}
        assert GraphemePhonemizer().identity("en").revision is not None
        assert changed.identity("en").revision == GraphemePhonemizer().identity("en").revision

    # keep_punctuation: a clause symbol comes before its space, and a symbol
    # that ends the text stays (BasePhonemizer.phonemize_to_list).
    @pytest.mark.parametrize("source, lang, plain, kept", [
        ("GraphemePhonemizer()", "ru", "a b", "a, b."),
        ("UnicodeCodepointPhonemizer()", "xx", "a b", "a, b."),
    ])
    def test_keep_punctuation_set_on_the_instance_changes_the_revision(self, source, lang, plain, kept):
        original, keeping = eval(source), eval(source)
        keeping.keep_punctuation = True
        assert ("".join(original.phonemize_to_list("a, b.", lang)),
                "".join(keeping.phonemize_to_list("a, b.", lang))) == (plain, kept)
        assert original.identity(lang).revision is not None
        assert keeping.identity(lang).revision != original.identity(lang).revision

    def test_keep_punctuation_that_the_backend_ignores_keeps_the_revision(self):
        original, keeping = OwnLazy(), OwnLazy()
        keeping.keep_punctuation = True
        assert keeping.phonemize_to_list("a, b.", "ru") == original.phonemize_to_list("a, b.", "ru")
        assert original.identity("ru").revision is not None
        assert keeping.identity("ru").revision == original.identity("ru").revision

    def test_a_whitespace_pattern_set_on_the_instance_changes_the_revision(self):
        original, ascii_only = GraphemePhonemizer(), GraphemePhonemizer()
        ascii_only.whitespace_re = re.compile(r"\s+", re.ASCII)
        # U+00A0 is whitespace to str patterns, and not to ASCII ones
        assert (original.phonemize_string("a\xa0b", "ru"), ascii_only.phonemize_string("a\xa0b", "ru")) == \
            ("a b", "a\xa0b")
        assert original.identity("ru").revision is not None
        assert ascii_only.identity("ru").revision != original.identity("ru").revision

    def test_settings_set_on_the_instance_to_their_defaults_keep_the_revision(self):
        changed = GraphemePhonemizer()
        changed.keep_punctuation = False
        changed.whitespace_re = re.compile(r"\s+")
        assert GraphemePhonemizer().identity("ru").revision is not None
        assert changed.identity("ru").revision == GraphemePhonemizer().identity("ru").revision

    def test_instance_settings_give_the_same_revision_in_every_process(self, tmp_path):
        runs = [subprocess.run([sys.executable, "-c", INSTANCE_SETTINGS_REVISION], cwd=ROOT, check=True,
                               capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": seed,
                                    "XDG_CACHE_HOME": str(tmp_path / seed)}).stdout.splitlines()[-1]
                for seed in ("0", "1")]
        assert json.loads(runs[0]).startswith("sc1:")
        assert runs[0] == runs[1]
        assert json.loads(runs[0]) != GraphemePhonemizer().identity("ru").revision

    def test_the_normaliser_hook_stays_out_of_the_revision(self):
        import text2spoken
        hooked = GraphemePhonemizer(normalizer=text2spoken.normalize)
        assert hooked.phonemize("2 gatos", "pt-PT") != GraphemePhonemizer().phonemize("2 gatos", "pt-PT")
        assert GraphemePhonemizer().identity("pt-PT").revision is not None
        assert hooked.identity("pt-PT").revision == GraphemePhonemizer().identity("pt-PT").revision

    def test_the_stress_notation_changes_the_revision(self):
        revisions = {GraphemePhonemizer(stress_notation=notation).identity("ru").revision
                     for notation in GraphemePhonemizer.STRESS_NOTATIONS}
        assert None not in revisions and len(revisions) == 3

    def test_the_normalisation_form_changes_the_revision(self):
        revisions = {UnicodeCodepointPhonemizer(form).identity("xx").revision
                     for form in ("NFC", "NFD", "NFKC", "NFKD")}
        assert None not in revisions and len(revisions) == 4

    @staticmethod
    def zipped_package(tmp_path, monkeypatch):
        """A package ``zipped_backend`` that loads from a zip archive, with a grapheme subclass."""
        archive = tmp_path / "backends.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("zipped_backend/__init__.py",
                            "from scriptconv.phonemizers import GraphemePhonemizer\n\n\n"
                            "class Zipped(GraphemePhonemizer):\n    pass\n")
        monkeypatch.syspath_prepend(str(archive))
        monkeypatch.delitem(sys.modules, "zipped_backend", raising=False)
        return importlib.import_module("zipped_backend")

    def test_a_package_in_a_zip_raises_a_named_error(self, tmp_path, monkeypatch):
        from scriptconv.phonemizers._revision import RevisionSourceUnavailable, _top_level_digest
        self.zipped_package(tmp_path, monkeypatch)
        with pytest.raises(RevisionSourceUnavailable, match="zipped_backend"):
            _top_level_digest("zipped_backend")

    def test_a_class_from_a_zip_gives_no_revision_and_a_warning(self, tmp_path, monkeypatch, caplog):
        zipped = self.zipped_package(tmp_path, monkeypatch)
        with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers._revision"):
            identity = zipped.Zipped().identity("en")
        assert GraphemePhonemizer().identity("en").revision is not None
        assert identity.revision is None
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "RevisionSourceUnavailable" in warnings[0] and "Zipped" in warnings[0]

    @pytest.mark.parametrize("source, lang", CODE_BACKENDS.values(), ids=CODE_BACKENDS)
    def test_another_unicode_version_changes_the_revision(self, source, lang, monkeypatch):
        current = eval(source).identity(lang).revision
        monkeypatch.setattr(unicodedata, "unidata_version", "1.1.0")
        assert current is not None
        assert eval(source).identity(lang).revision != current


# Edits of the wrapper code, (backend, file, old text, new text). Each changes
# the output of the named backend for some input.
WRAPPER_MUTANTS = {
    "T1 the tugaphone wrapper drops the stress mark": (
        "tugaphone", "phonemizers/pt.py",
        "return self.tuga.phonemize_sentence(text, lang, contact=self.contact)",
        'return self.tuga.phonemize_sentence(text, lang, contact=self.contact).replace("ˈ", "")'),
    "T2 a semicolon is kept as a comma, tugaphone": (
        "tugaphone", "phonemizers/base.py", '":": ":", ";": ";",', '":": ":", ";": ",",'),
    "T3 the tugaphone frontend keeps a block of whitespace": (
        "frontend-tugaphone", "frontend.py", "if block[2:-2].strip():", "if block[2:-2]:"),
    "O1 the orthography2ipa wrapper drops the stress mark": (
        "orthography2ipa", "phonemizers/o2ipa.py",
        "return self._engine(resolved).transcribe(text)",
        'return self._engine(resolved).transcribe(text).replace("ˈ", "")'),
    "B1 the Barranquenho wrapper drops the stress mark": (
        "barranquenho", "phonemizers/pt.py",
        "return self._o2i.phonemize_string(text, self._SPEC)",
        'return self._o2i.phonemize_string(text, self._SPEC).replace("ˈ", "")'),
    "M1 the Mirandese wrapper drops the stress mark": (
        "mirandese", "phonemizers/mwl.py",
        "return self._o2i.phonemize_string(text, DIALECTS[self.get_lang(lang)])",
        'return self._o2i.phonemize_string(text, DIALECTS[self.get_lang(lang)]).replace("ˈ", "")'),
    "D1 the dizione wrapper joins two sentences with a bar": (
        "dizione", "phonemizers/dizione.py",
        'return " ".join(self._ipa_sentences(text))', 'return " | ".join(self._ipa_sentences(text))'),
}


@pytest.fixture(scope="module")
def wrapped_pristine(tmp_path_factory):
    return revisions_in_a_copy(tmp_path_factory.mktemp("wrapped"), script=WRAPPER_REVISIONS)


# Each copy runs the tugaphone and orthography2ipa probes in a fresh process.
@pytest.mark.timeout(900)
class TestWrapperRevision:
    def test_each_wrapper_has_its_own_revision(self, wrapped_pristine):
        assert all(revision.startswith("sc1:") for revision in wrapped_pristine.values())
        assert len(set(wrapped_pristine.values())) == len(WRAPPER_BACKENDS) + len(WRAPPER_FRONTENDS)

    @pytest.mark.parametrize("mutant", WRAPPER_MUTANTS)
    def test_a_wrapper_code_change_changes_the_revision(self, mutant, wrapped_pristine, tmp_path):
        backend, *edit = WRAPPER_MUTANTS[mutant]
        assert wrapped_pristine[backend] is not None
        changed = revisions_in_a_copy(tmp_path, edit, WRAPPER_REVISIONS)
        assert changed[backend] != wrapped_pristine[backend]

    @pytest.mark.parametrize("edit", NEUTRAL_EDITS)
    def test_an_edit_that_changes_no_output_keeps_every_wrapper_revision(self, edit, wrapped_pristine,
                                                                         tmp_path):
        assert None not in wrapped_pristine.values()
        assert revisions_in_a_copy(tmp_path, NEUTRAL_EDITS[edit], WRAPPER_REVISIONS) == wrapped_pristine


def frontend(backend=None, **config):
    return TextFrontend(FrontendConfig("pt-PT", **config), backend or GraphemePhonemizer())


class TestFrontendRevision:
    def test_the_frontend_revision_covers_the_backend_and_the_frontend(self):
        identity, backend = frontend().identity(), GraphemePhonemizer().identity("pt-PT")
        assert backend.revision is not None and identity.revision.startswith("sc1:")
        assert identity.revision != backend.revision

    def test_keep_punctuation_changes_the_revision(self):
        assert frontend().identity().revision is not None
        assert frontend(keep_punctuation=True).identity().revision != frontend().identity().revision

    def test_a_normaliser_that_scriptconv_cannot_vouch_for_gives_no_revision(self):
        assert frontend().identity().revision is not None
        assert frontend(normalizer=lambda text, lang: text.upper()).identity().revision is None

    def test_the_text2spoken_hook_folds_in_the_text2spoken_revision(self, monkeypatch):
        import text2spoken
        monkeypatch.setattr(text2spoken, "revision", lambda lang: f"t2s1:{lang}:1", raising=False)
        first = frontend(normalizer=spoken_normalizer()).identity().revision
        monkeypatch.setattr(text2spoken, "revision", lambda lang: f"t2s1:{lang}:2")
        second = frontend(normalizer=spoken_normalizer()).identity().revision
        assert None not in (first, second) and first != second
        assert first != frontend().identity().revision

    def test_a_text2spoken_without_a_revision_gives_no_revision(self, monkeypatch):
        import text2spoken
        monkeypatch.delattr(text2spoken, "revision", raising=False)
        assert frontend().identity().revision is not None
        assert frontend(normalizer=spoken_normalizer()).identity().revision is None

    def test_a_text2spoken_revision_error_gives_no_revision_and_a_warning(self, monkeypatch, caplog):
        import text2spoken

        def fails(lang):
            raise ValueError("a module loads from a zip file")
        monkeypatch.setattr(text2spoken, "revision", fails, raising=False)
        with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
            assert frontend(normalizer=spoken_normalizer()).identity().revision is None
        assert [r.levelno for r in caplog.records if r.name == "scriptconv.frontend"] == [logging.WARNING]

    def test_a_diacritizing_frontend_gives_no_revision(self):
        assert TextFrontend(FrontendConfig("es"), GraphemePhonemizer()).identity().revision is not None
        assert TextFrontend(FrontendConfig("ar"), GraphemePhonemizer()).identity().revision is None

    def test_a_casing_gives_no_revision(self):
        assert frontend().identity().revision is not None
        assert frontend(stages=Stages(casing=str.upper)).identity().revision is None

    def test_a_backend_with_no_revision_gives_no_revision(self):
        class Custom(BasePhonemizer):
            def phonemize_string(self, text, lang):
                return text
        assert frontend(Custom()).identity().revision is None


GRAPHEMES_EN_REVISION = """
import json
from scriptconv.phonemizers import GraphemePhonemizer
print(json.dumps(GraphemePhonemizer().identity("en").revision))
"""


@pytest.fixture
def fresh_probes():
    """Probe results and warnings kept by no earlier test, and none kept after this one."""
    from scriptconv.phonemizers import _revision
    caches = [getattr(_revision, name) for name in ("_probe_outcome", "_probe_digest", "_warn_once")
              if hasattr(getattr(_revision, name, None), "cache_clear")]
    for cache in caches:
        cache.cache_clear()
    yield
    for cache in caches:
        cache.cache_clear()


def fake_python(directory, body):
    """An executable that runs the shell *body* in place of Python."""
    path = directory / "python"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return str(path)


class TestProbeFailures:
    def assert_no_revision_and_one_warning(self, caplog, words):
        with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers._revision"):
            identity = GraphemePhonemizer().identity("en")
        assert identity.revision is None
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "RevisionProbeFailed" in warnings[0] and words in warnings[0]

    def test_a_probe_that_runs_too_long_gives_no_revision(self, fresh_probes, tmp_path, monkeypatch,
                                                          caplog):
        from scriptconv.phonemizers import _revision
        monkeypatch.setattr(_revision, "PROBE_TIMEOUT", 1, raising=False)
        monkeypatch.setattr(sys, "executable", fake_python(tmp_path, "sleep 5"))
        started = time.monotonic()
        self.assert_no_revision_and_one_warning(caplog, "longer than 1 s")
        assert time.monotonic() - started < 4

    def test_a_probe_that_prints_nothing_gives_no_revision(self, fresh_probes, tmp_path, monkeypatch,
                                                           caplog):
        monkeypatch.setattr(sys, "executable", fake_python(tmp_path, "exit 0"))
        self.assert_no_revision_and_one_warning(caplog, "printed 0 results")

    def test_a_failed_probe_warns_once_in_a_process(self, fresh_probes, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(sys, "executable", fake_python(tmp_path, "exit 0"))
        with caplog.at_level(logging.WARNING, logger="scriptconv.phonemizers._revision"):
            revisions = [GraphemePhonemizer().identity("en").revision for _ in range(5)]
        assert revisions == [None] * 5
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "printed 0 results" in warnings[0]

    def test_a_failed_probe_keeps_no_exception(self, fresh_probes, monkeypatch):
        from scriptconv.phonemizers import _revision
        keys = []

        def fails(*key):
            keys.append(key)
            raise _revision.RevisionProbeFailed("the probe exited with 1")
        monkeypatch.setattr(_revision, "_run_probe", fails)
        for _ in range(5):
            assert GraphemePhonemizer().identity("en").revision is None
        assert len(keys) == 1
        kept = _revision._probe_outcome(*keys[0])
        # a kept exception, raised again on each call, grows its traceback
        assert not isinstance(kept, BaseException)
        assert "the probe exited with 1" in str(kept)

    def test_scriptconv_loaded_before_the_probe_gives_no_revision(self, fresh_probes, tmp_path,
                                                                  monkeypatch, caplog):
        (tmp_path / "sitecustomize.py").write_text("import scriptconv.phonemizers.base\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        self.assert_no_revision_and_one_warning(caplog, "scriptconv loaded before it started")

    def test_a_distribution_loaded_before_the_probe_still_counts(self, fresh_probes, tmp_path,
                                                                 monkeypatch):
        from scriptconv.phonemizers import _revision
        expected = GraphemePhonemizer().identity("en").revision
        _revision._probe_outcome.cache_clear()
        (tmp_path / "sitecustomize.py").write_text("import quebra_frases\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        assert expected is not None
        assert GraphemePhonemizer().identity("en").revision == expected

    def test_a_change_to_a_distribution_loaded_before_the_probe_changes_the_revision(self, tmp_path):
        import quebra_frases
        shutil.copytree(Path(quebra_frases.__file__).parent, tmp_path / "quebra_frases",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (tmp_path / "sitecustomize.py").write_text("import quebra_frases\n")

        def revision():
            done = subprocess.run([sys.executable, "-c", GRAPHEMES_EN_REVISION], cwd=ROOT, check=True,
                                  capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT)]),
                                       "PYTHONDONTWRITEBYTECODE": "1"})
            return json.loads(done.stdout.splitlines()[-1])
        before = revision()
        with open(tmp_path / "quebra_frases" / "tokenization.py", "a", encoding="utf-8") as module:
            module.write("\n_split = sentence_tokenize\n\n\n"
                         "def sentence_tokenize(input_string):\n    return _split(input_string)[::-1]\n")
        after = revision()
        assert None not in (before, after)
        assert after != before

    def test_a_dependency_imported_by_a_preloaded_distribution_counts(self, tmp_path):
        import quebra_frases
        shutil.copytree(Path(quebra_frases.__file__).parent, tmp_path / "quebra_frases",
                        ignore=shutil.ignore_patterns("__pycache__"))
        init = tmp_path / "quebra_frases" / "__init__.py"
        init.write_text("import stubdep\nfrom stubdep2 import helper\n" + init.read_text(encoding="utf-8"),
                        encoding="utf-8")
        for name, body in (("stubdep", "VALUE = 1\n"), ("stubdep2", "def helper():\n    return 1\n")):
            (tmp_path / name).mkdir()
            (tmp_path / name / "__init__.py").write_text(body)
        (tmp_path / "sitecustomize.py").write_text("import quebra_frases\n")

        def revision():
            done = subprocess.run([sys.executable, "-c", GRAPHEMES_EN_REVISION], cwd=ROOT, check=True,
                                  capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT)]),
                                       "PYTHONDONTWRITEBYTECODE": "1"})
            return json.loads(done.stdout.splitlines()[-1])
        base = revision()
        results = {}
        for name, file in (("stubdep", "__init__.py"), ("stubdep2", "__init__.py")):
            with open(tmp_path / name / file, "a", encoding="utf-8") as module:
                module.write("\nCHANGED = 1\n")
            results[name] = revision()
        assert base is not None
        assert results["stubdep"] != base
        assert results["stubdep2"] != results["stubdep"]

    @staticmethod
    def preloaded_revision(directory, sitecustomize=None):
        """The GRAPHEMES en revision in a process whose path starts at *directory*."""
        if sitecustomize is not None:
            (directory / "sitecustomize.py").write_text(sitecustomize)
        done = subprocess.run([sys.executable, "-c", GRAPHEMES_EN_REVISION], cwd=ROOT, check=True,
                              capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join([str(directory), str(ROOT)]),
                                   "PYTHONDONTWRITEBYTECODE": "1"})
        return json.loads(done.stdout.splitlines()[-1])

    def test_a_hook_from_an_unrelated_package_keeps_the_revision(self, tmp_path):
        (tmp_path / "hookpkg").mkdir()
        (tmp_path / "hookpkg" / "__init__.py").write_text("def hook(*args):\n    return None\n")
        (tmp_path / "empty").mkdir()
        expected = self.preloaded_revision(tmp_path / "empty")
        hooked = self.preloaded_revision(
            tmp_path, "import sys, hookpkg\nsys.excepthook = hookpkg.hook\n")
        assert expected is not None
        assert hooked == expected

    def test_a_dependency_of_a_dependency_of_a_preloaded_distribution_counts(self, tmp_path):
        import quebra_frases
        shutil.copytree(Path(quebra_frases.__file__).parent, tmp_path / "quebra_frases",
                        ignore=shutil.ignore_patterns("__pycache__"))
        init = tmp_path / "quebra_frases" / "__init__.py"
        init.write_text("import hop_a\n" + init.read_text(encoding="utf-8"), encoding="utf-8")
        for name, body in (("hop_a", "import hop_b\n"), ("hop_b", "import hop_c\n"), ("hop_c", "VALUE = 1\n")):
            (tmp_path / name).mkdir()
            (tmp_path / name / "__init__.py").write_text(body)
        before = self.preloaded_revision(tmp_path, "import quebra_frases\n")
        with open(tmp_path / "hop_c" / "__init__.py", "a", encoding="utf-8") as module:
            module.write("\nCHANGED = 1\n")
        assert self.preloaded_revision(tmp_path) not in (None, before)

    def test_a_hook_on_a_standard_library_module_a_used_package_holds_keeps_the_revision(self, tmp_path):
        (tmp_path / "hookpkg").mkdir()
        (tmp_path / "hookpkg" / "__init__.py").write_text("def hook(*args):\n    return None\n")
        (tmp_path / "empty").mkdir()
        expected = self.preloaded_revision(tmp_path / "empty")
        hooked = self.preloaded_revision(
            tmp_path, "import quebra_frases, hookpkg, xml.dom\n"
                      "quebra_frases.held = xml.dom\nxml.dom.hook = hookpkg.hook\n")
        assert expected is not None
        assert hooked == expected

    def test_a_blocked_import_in_sys_modules_keeps_the_revision(self, tmp_path):
        (tmp_path / "empty").mkdir()
        expected = self.preloaded_revision(tmp_path / "empty", None)
        blocked = self.preloaded_revision(
            tmp_path, "import sys, quebra_frases\nsys.modules['quebra_frases.blocked'] = None\n")
        assert expected is not None
        assert blocked == expected

    def test_another_distribution_loaded_before_the_probe_keeps_the_revision(self, fresh_probes, tmp_path,
                                                                             monkeypatch):
        from scriptconv.phonemizers import _revision
        expected = GraphemePhonemizer().identity("en").revision
        _revision._probe_outcome.cache_clear()
        (tmp_path / "sitecustomize.py").write_text("import pytest\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        assert expected is not None
        assert GraphemePhonemizer().identity("en").revision == expected

    def test_a_print_after_the_probe_result_keeps_the_revision(self, fresh_probes, tmp_path,
                                                               monkeypatch):
        from scriptconv.phonemizers import _revision
        expected = GraphemePhonemizer().identity("en").revision
        _revision._probe_outcome.cache_clear()
        (tmp_path / "sitecustomize.py").write_text('import atexit\natexit.register(print, "done")\n')
        monkeypatch.syspath_prepend(str(tmp_path))
        assert expected is not None
        assert GraphemePhonemizer().identity("en").revision == expected


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
