"""The wrappers that live in scriptconv-copyleft and scriptconv-nonfree.

The registry resolves them from the sister package, the extra that served each
one installs that package, a missing package raises an error naming the extra,
and the old import paths give the moved class with a deprecation warning.
"""
import importlib
import re
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
from scriptconv.phonemizers._moved import MOVED, REMOVAL_VERSION
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY
from scriptconv.version import VERSION_STR

ROOT = Path(__file__).resolve().parent.parent
FLOOR = Version("0.1.0a1")

COPYLEFT = {Phonemizer.ESPEAK, Phonemizer.TRANSPHONE, Phonemizer.MISAKI, Phonemizer.MISAKI_EN,
            Phonemizer.MISAKI_JA, Phonemizer.MISAKI_ZH, Phonemizer.MISAKI_KO,
            Phonemizer.MISAKI_VI, Phonemizer.COTOVIA, Phonemizer.AHOTTS, Phonemizer.G2PFA,
            Phonemizer.PYKAKASI, Phonemizer.G2PK, Phonemizer.KOG2PK}
NONFREE = {Phonemizer.MANTOQ, Phonemizer.HALABI, Phonemizer.IQRA, Phonemizer.VIPHONEME,
           Phonemizer.AFRICA_G2P, Phonemizer.GHANA_G2P}
MOVED_MEMBERS = sorted(COPYLEFT | NONFREE, key=lambda m: m.value)
OLD_PATHS = sorted((module, name) for module, names in MOVED.items() for name in names)


def _package(member):
    return "scriptconv_copyleft" if member in COPYLEFT else "scriptconv_nonfree"


def _extras():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["optional-dependencies"]


@pytest.mark.parametrize("member", MOVED_MEMBERS)
def test_the_registry_imports_the_class_from_its_sister_package(member):
    cls = get_phonemizer_class(member)
    assert cls.__module__.split(".")[0] == _package(member)
    assert cls.__name__ == PHONEMIZER_REGISTRY[member][1]


@pytest.mark.parametrize("member", [m for m in Phonemizer if m not in COPYLEFT | NONFREE])
def test_the_other_members_stay_in_scriptconv(member):
    assert get_phonemizer_class(member).__module__.startswith("scriptconv.")


@pytest.mark.parametrize("member", MOVED_MEMBERS)
def test_the_extra_installs_the_sister_package_at_the_published_alpha(member):
    extra = PHONEMIZER_REGISTRY[member][2]
    sister = _package(member).replace("_", "-")
    reqs = [Requirement(r) for r in _extras()[extra]]
    pinned = [r for r in reqs if r.name == sister]
    assert len(pinned) == 1, (extra, [str(r) for r in reqs])
    assert pinned[0].specifier.contains(FLOOR, prereleases=True)
    assert not pinned[0].specifier.contains(Version("0.0.9"), prereleases=True)


@pytest.mark.parametrize("member", MOVED_MEMBERS)
def test_a_missing_sister_package_names_the_extra(member, monkeypatch):
    monkeypatch.setitem(sys.modules, _package(member), None)
    for name in list(sys.modules):
        if name.startswith(_package(member) + "."):
            monkeypatch.delitem(sys.modules, name)
    with pytest.raises(ImportError) as refused:
        get_phonemizer_class(member)
    assert f"pip install scriptconv[{PHONEMIZER_REGISTRY[member][2]}]" in str(refused.value)


def test_the_removal_version_is_a_later_stable_release():
    removal = Version(REMOVAL_VERSION)
    assert removal > Version(VERSION_STR)
    assert not removal.is_prerelease


@pytest.mark.parametrize("module, name", OLD_PATHS)
def test_an_old_import_path_warns_once_and_gives_the_moved_class(module, name, monkeypatch):
    old = importlib.import_module(module)
    monkeypatch.delitem(old.__dict__, name, raising=False)
    new_module, _ = MOVED[module][name]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = getattr(old, name)
        second = getattr(old, name)
    assert first is second is getattr(importlib.import_module(new_module), name)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1
    message = str(deprecations[0].message)
    assert f"{module}.{name}" in message and new_module in message and REMOVAL_VERSION in message
    assert deprecations[0].filename == __file__


def test_the_package_attributes_give_the_espeak_and_transphone_classes(monkeypatch):
    import scriptconv.phonemizers as P
    from scriptconv_copyleft.phonemizers import mul
    for name in ("EspeakPhonemizer", "TransphonePhonemizer"):
        monkeypatch.delitem(P.__dict__, name, raising=False)
    with pytest.warns(DeprecationWarning):
        assert getattr(P, "EspeakPhonemizer") is mul.EspeakPhonemizer
    with pytest.warns(DeprecationWarning):
        assert getattr(P, "TransphonePhonemizer") is mul.TransphonePhonemizer


@pytest.mark.parametrize("module, name", OLD_PATHS)
def test_an_old_import_path_without_the_sister_package_names_the_extra(module, name, monkeypatch):
    old = importlib.import_module(module)
    monkeypatch.delitem(old.__dict__, name, raising=False)
    new_module, extra = MOVED[module][name]
    package = new_module.split(".")[0]
    monkeypatch.setitem(sys.modules, package, None)
    for loaded in list(sys.modules):
        if loaded.startswith(package + "."):
            monkeypatch.delitem(sys.modules, loaded)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(ImportError, match=re.escape(f"pip install scriptconv[{extra}]")):
            getattr(old, name)


def test_an_unknown_name_is_still_an_attribute_error():
    from scriptconv.phonemizers import mul
    with pytest.raises(AttributeError):
        mul.NoSuchPhonemizer


class TestJapaneseReadings:
    NAMES = ["ReadingToken", "tokens", "to_hiragana", "to_katakana"]

    @pytest.mark.parametrize("name", NAMES)
    def test_each_name_is_the_function_of_scriptconv_copyleft(self, name):
        import scriptconv
        from scriptconv import readings
        from scriptconv_copyleft import readings as moved
        assert getattr(readings, name) is getattr(moved, name)
        assert getattr(scriptconv, name) is getattr(moved, name)

    def test_the_reading_is_the_dictionary_reading(self):
        from scriptconv import to_hiragana, to_katakana
        assert to_hiragana("東京") == "とうきょう"
        assert to_katakana("日本語") == "ニホンゴ"

    @pytest.mark.parametrize("name", NAMES)
    def test_without_the_sister_package_the_error_names_the_ja_extra(self, name, monkeypatch):
        import scriptconv
        monkeypatch.setitem(sys.modules, "scriptconv_copyleft", None)
        with pytest.raises(ImportError, match=re.escape("pip install scriptconv[ja]")):
            getattr(scriptconv, name)


def test_importing_scriptconv_imports_no_sister_package():
    modules = ["scriptconv", "scriptconv.readings", "scriptconv.graph",
               "scriptconv.phonemizers", "scriptconv.phonemizers.registry"] + sorted(MOVED)
    code = ("import importlib, sys\n"
            f"for m in {modules!r}: importlib.import_module(m)\n"
            "print(sorted(m for m in sys.modules if m.startswith(('scriptconv_copyleft', "
            "'scriptconv_nonfree'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
