"""The ``openjtalk`` backend runs only on pyopenjtalk-plus with onnxruntime.

pyopenjtalk and pyopenjtalk-plus both install the ``pyopenjtalk`` module, with
other dictionaries and accent rules. The backend checks which distribution
owns the module before it reads, and the extras install pyopenjtalk-plus only.
"""
import base64
import hashlib
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pyopenjtalk
import pytest
from packaging.requirements import Requirement

from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer
from scriptconv.phonemizers.ja import OpenJTaklPhonemizer
from scriptconv.phonemizers.openjtalk_engine import module_distribution

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = {"pyopenjtalk": "0.4.1", "pyopenjtalk-plus": "0.4.1.post10"}
ORDERS = [["pyopenjtalk", "pyopenjtalk-plus"], ["pyopenjtalk-plus", "pyopenjtalk"]]


def _record_hash(content: bytes) -> SimpleNamespace:
    value = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
    return SimpleNamespace(mode="sha256", value=value)


@pytest.fixture
def both_installed(tmp_path, monkeypatch):
    """pyopenjtalk and pyopenjtalk-plus both record ``pyopenjtalk/__init__.py``.

    The file on disk holds the content of the distribution that the test names
    as the owner, as when that distribution was installed last.
    """
    module_file = tmp_path / "pyopenjtalk" / "__init__.py"
    module_file.parent.mkdir()
    contents = {name: f"# {name}\n".encode() for name in VERSIONS}

    def install(owner: str, order: list[str]):
        module_file.write_bytes(contents[owner])
        dists = {name: SimpleNamespace(files=[SimpleNamespace(hash=_record_hash(contents[name]),
                                                              locate=lambda: module_file)])
                 for name in VERSIONS}
        monkeypatch.setattr(pyopenjtalk, "__file__", str(module_file))
        monkeypatch.setattr(metadata, "packages_distributions", lambda: {"pyopenjtalk": order})
        monkeypatch.setattr(metadata, "distribution", dists.__getitem__)
        monkeypatch.setattr(metadata, "version", VERSIONS.__getitem__)

    return install


@pytest.fixture
def broken_onnxruntime(tmp_path, monkeypatch):
    """An onnxruntime whose import raises, and no ``pyopenjtalk`` imported yet.

    pyopenjtalk-plus imports onnxruntime while ``pyopenjtalk`` imports. The
    modules leave ``sys.modules`` so that the backend imports them again.
    """
    def install(error: str):
        package = tmp_path / "onnxruntime"
        package.mkdir()
        (package / "__init__.py").write_text(f"raise {error}('libonnxruntime.so: cannot open shared object file')\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        for name in [n for n in sys.modules if n.split(".")[0] in ("onnxruntime", "pyopenjtalk")]:
            monkeypatch.delitem(sys.modules, name)

    return install


@pytest.mark.parametrize("owner", VERSIONS)
@pytest.mark.parametrize("order", ORDERS)
def test_module_distribution_names_the_owner(both_installed, owner, order):
    both_installed(owner, order)
    assert module_distribution("pyopenjtalk", pyopenjtalk.__file__) == owner


def test_a_recorded_file_at_another_path_does_not_own_the_module(both_installed, tmp_path, monkeypatch):
    """A distribution that records the same bytes at another path is not the owner."""
    both_installed("pyopenjtalk-plus", ["pyopenjtalk-plus"])
    copy = tmp_path / "other" / "__init__.py"
    copy.parent.mkdir()
    copy.write_bytes(Path(pyopenjtalk.__file__).read_bytes())
    owners = {"other": SimpleNamespace(files=[SimpleNamespace(hash=_record_hash(copy.read_bytes()),
                                                             locate=lambda: copy)]),
              "pyopenjtalk-plus": metadata.distribution("pyopenjtalk-plus")}
    monkeypatch.setattr(metadata, "packages_distributions", lambda: {"pyopenjtalk": ["other", "pyopenjtalk-plus"]})
    monkeypatch.setattr(metadata, "distribution", owners.__getitem__)
    assert module_distribution("pyopenjtalk", pyopenjtalk.__file__) == "pyopenjtalk-plus"


def test_a_module_with_no_file_has_no_owner():
    assert module_distribution("pyopenjtalk", None) is None


@pytest.mark.parametrize("order", ORDERS)
def test_refuses_the_pyopenjtalk_module(both_installed, order):
    both_installed("pyopenjtalk", order)
    with pytest.raises(ImportError) as refusal:
        OpenJTaklPhonemizer()
    assert str(refusal.value) == (
        "The OpenJTalk phonemizer needs pyopenjtalk-plus, but the installed pyopenjtalk module comes "
        "from pyopenjtalk. Run 'pip uninstall pyopenjtalk', then "
        "'pip install --force-reinstall pyopenjtalk-plus[onnxruntime]', or install "
        "'scriptconv[ja-phonemizers]' in a new environment."
    )


def test_refuses_a_pyopenjtalk_namespace_package(monkeypatch):
    """The uninstall of one distribution leaves a namespace package with no ``__file__``."""
    monkeypatch.setattr(pyopenjtalk, "__file__", None)
    with pytest.raises(ImportError, match=r"comes from an unknown distribution\. Run 'pip uninstall pyopenjtalk'"):
        OpenJTaklPhonemizer()


def test_refuses_to_run_without_onnxruntime(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    with pytest.raises(ImportError, match=r"needs onnxruntime.*scriptconv\[ja-phonemizers\]"):
        OpenJTaklPhonemizer()


@pytest.mark.parametrize("error", ["ImportError", "OSError", "RuntimeError"])
def test_refuses_an_onnxruntime_that_does_not_import(broken_onnxruntime, error):
    broken_onnxruntime(error)
    with pytest.raises(ImportError, match=r"needs onnxruntime.*does not import") as refusal:
        OpenJTaklPhonemizer()
    assert type(refusal.value.__cause__).__name__ == error


@pytest.mark.parametrize("order", ORDERS)
def test_runs_on_pyopenjtalk_plus(both_installed, order):
    both_installed("pyopenjtalk-plus", order)
    identity = OpenJTaklPhonemizer().identity("ja")
    assert (identity.distribution, identity.version) == ("pyopenjtalk-plus", "0.4.1.post10")


def test_the_installed_engine_is_pyopenjtalk_plus():
    phonemizer = get_phonemizer(Phonemizer.OPENJTALK, Alphabet.KANA)
    identity = phonemizer.identity("ja-JP")
    assert (identity.distribution, identity.version, identity.lang) == \
        ("pyopenjtalk-plus", metadata.version("pyopenjtalk-plus"), "ja")


def test_onnxruntime_reads_nani():
    """Without onnxruntime pyopenjtalk-plus reads 何時 as なにじ."""
    assert OpenJTaklPhonemizer(Alphabet.KANA).phonemize_string("何時ですか", "ja") == "ナンジデスカ"


def test_the_dictionary_comes_with_the_wheel():
    """A first use with no network reads: the dictionary is in the installed package."""
    dictionary = Path(pyopenjtalk.OPEN_JTALK_DICT_DIR.decode())
    package = Path(pyopenjtalk.__file__).parent
    assert dictionary.is_relative_to(package)
    assert (dictionary / "sys.dic").is_file()


def _extras():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]


def test_no_extra_names_pyopenjtalk():
    names = {extra: [Requirement(r).name for r in reqs] for extra, reqs in _extras().items()}
    assert {extra for extra, found in names.items() if "pyopenjtalk" in found} == set()


@pytest.mark.parametrize("extra", ["ja-phonemizers", "test"])
def test_the_extra_installs_pyopenjtalk_plus_with_onnxruntime(extra):
    plus = [Requirement(r) for r in _extras()[extra] if re.match(r"pyopenjtalk-plus\b", r)]
    assert [(r.extras, str(r.specifier)) for r in plus] == [({"onnxruntime"}, ">=0.4.1.post10")]


def test_the_misaki_extra_takes_the_copyleft_alpha_on_pyopenjtalk_plus():
    """scriptconv-copyleft 0.1.2a1 installs pyopenjtalk with its misaki extra, 0.2.0a1 pyopenjtalk-plus."""
    copyleft = [Requirement(r) for r in _extras()["misaki"] if r.startswith("scriptconv-copyleft")]
    assert [str(r.specifier) for r in copyleft] == [">=0.2.0a1"]
