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
REVISIONS = f"""
import json, scriptconv
from scriptconv.phonemizers import GraphemePhonemizer, UnicodeCodepointPhonemizer
from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
print(json.dumps({{"scriptconv": scriptconv.__file__, **{{name: eval(source).identity(lang).revision
                  for name, (source, lang) in {CODE_BACKENDS!r}.items()}}}}))
"""
SCRIPTCONV = Path(sys.modules["scriptconv"].__file__).parent

# Edits of the scriptconv source, (file, old text, new text), each of which
# changes the output of the named backend for some input.
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


def revisions_in_a_copy(directory, edit=None):
    """The revision of each of :data:`CODE_BACKENDS`, in a fresh process, from a
    copy of the scriptconv package with *edit* ``(file, old, new)`` applied."""
    tree = directory / "tree"
    shutil.copytree(SCRIPTCONV, tree / "scriptconv", ignore=shutil.ignore_patterns("__pycache__"))
    if edit is not None:
        target, old, new = edit
        path = tree / "scriptconv" / target
        source = path.read_text(encoding="utf-8")
        assert source.count(old) == 1, f"{old!r} is not in {target} once"
        path.write_text(source.replace(old, new), encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", REVISIONS], cwd=tree, check=True,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1"})
    revisions = json.loads(done.stdout.splitlines()[-1])
    assert Path(revisions.pop("scriptconv")).is_relative_to(tree)
    return revisions


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    return revisions_in_a_copy(tmp_path_factory.mktemp("pristine"))


class LongVowel(GraphemePhonemizer):
    """Graphemes, with ":" after each "a"."""

    def phonemize_string(self, text, lang):
        return super().phonemize_string(text, lang).replace("a", "a:")


class TestCodeRevision:
    def test_the_revision_is_the_same_in_every_process(self):
        runs = [subprocess.run([sys.executable, "-c", REVISIONS], cwd=ROOT, check=True,
                               capture_output=True, text=True,
                               env={**os.environ, "PYTHONHASHSEED": seed}).stdout.splitlines()[-1]
                for seed in ("0", "1", "4242")]
        revisions = json.loads(runs[0])
        revisions.pop("scriptconv")
        assert all(revision.startswith("sc1:") for revision in revisions.values())
        assert runs[0] == runs[1] == runs[2]
        assert len(set(revisions.values())) == len(CODE_BACKENDS)

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
