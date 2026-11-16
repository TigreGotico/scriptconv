"""The ``openjtalk`` backend runs only on pyopenjtalk-plus with onnxruntime.

pyopenjtalk and pyopenjtalk-plus both install the ``pyopenjtalk`` module, with
other dictionaries and accent rules. The backend checks which distribution
owns the module and which dictionary it reads before it reads, and the extras
install pyopenjtalk-plus only.
"""
import base64
import hashlib
import os
import re
import subprocess
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
ALPHABETS = [Alphabet.HEPBURN, Alphabet.KANA]
BUNDLED = Path(os.path.dirname(os.path.abspath(pyopenjtalk.__file__))) / "dictionary"


@pytest.fixture(autouse=True)
def no_dictionary_variable(monkeypatch):
    monkeypatch.delenv("OPEN_JTALK_DICT_DIR", raising=False)


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
        monkeypatch.setattr(pyopenjtalk, "OPEN_JTALK_DICT_DIR", str(module_file.parent / "dictionary").encode())
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


@pytest.mark.parametrize("alphabet", ALPHABETS)
@pytest.mark.parametrize("order", ORDERS)
def test_refuses_the_pyopenjtalk_module(both_installed, order, alphabet):
    both_installed("pyopenjtalk", order)
    with pytest.raises(ImportError) as refusal:
        OpenJTaklPhonemizer(alphabet)
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


@pytest.fixture
def foreign_dictionary(tmp_path):
    """A working dictionary at another path: a directory of links to the bundled files."""
    directory = tmp_path / "open_jtalk_dic"
    directory.mkdir()
    for file in BUNDLED.iterdir():
        (directory / file.name).symlink_to(file)
    return directory


def _build_in_a_new_process(dictionary, cwd=None, before: str = "") -> str:
    """Builds the backend in a new Python with ``OPEN_JTALK_DICT_DIR`` set, as pyopenjtalk reads it at import.

    *before* runs first in that Python, and the backend reads 何時ですか when it builds.
    """
    code = (before + "from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer\n"
            "try:\n"
            "    print(get_phonemizer(Phonemizer.OPENJTALK, Alphabet.KANA).phonemize_string('何時ですか', 'ja'))\n"
            "except ImportError as e:\n"
            "    print(e)\n")
    env = {**os.environ, "OPEN_JTALK_DICT_DIR": str(dictionary), "PYTHONPATH": str(ROOT),
           "BUNDLED_DICTIONARY": str(BUNDLED)}
    result = subprocess.run([sys.executable, "-P", "-c", code], env=env, cwd=cwd, capture_output=True, text=True,
                            check=True)
    return result.stdout.strip()


def _refusal(value) -> str:
    return ("The OpenJTalk phonemizer reads the dictionary of pyopenjtalk-plus, but OPEN_JTALK_DICT_DIR "
            f"is {str(value)!r}, not {str(BUNDLED)!r}. Unset OPEN_JTALK_DICT_DIR, then start Python again.")


def test_refuses_another_dictionary_from_the_environment(foreign_dictionary):
    assert _build_in_a_new_process(foreign_dictionary) == _refusal(foreign_dictionary)


@pytest.mark.parametrize("spelling", ["", "/", "/../dictionary"])
def test_reads_with_the_absolute_path_of_the_bundled_dictionary(spelling):
    assert _build_in_a_new_process(f"{BUNDLED}{spelling}") == "ナンジデスカ"


@pytest.mark.parametrize("value", ["dictionary", "./dictionary"])
def test_refuses_a_relative_path_to_the_bundled_dictionary(value):
    """pyopenjtalk opens a relative path from the directory of the first reading, which can change."""
    assert _build_in_a_new_process(value, cwd=BUNDLED.parent) == _refusal(value)


def test_refuses_a_link_to_the_bundled_dictionary(tmp_path):
    """The link can point at another dictionary by the time pyopenjtalk opens it."""
    link = tmp_path / "dictionary"
    link.symlink_to(BUNDLED)
    assert _build_in_a_new_process(link) == _refusal(link)


def test_refuses_a_link_re_pointed_to_the_bundled_dictionary_after_the_import(foreign_dictionary, tmp_path):
    """pyopenjtalk took the link while it named another dictionary, and keeps that value."""
    link = tmp_path / "dictionary"
    link.symlink_to(foreign_dictionary)
    before = ("import os, pyopenjtalk\n"
              "os.remove(os.environ['OPEN_JTALK_DICT_DIR'])\n"
              "os.symlink(os.environ['BUNDLED_DICTIONARY'], os.environ['OPEN_JTALK_DICT_DIR'])\n")
    assert _build_in_a_new_process(link, before=before) == _refusal(link)


@pytest.mark.parametrize("alphabet", ALPHABETS)
def test_refuses_the_variable_set_after_the_import(foreign_dictionary, monkeypatch, alphabet):
    monkeypatch.setenv("OPEN_JTALK_DICT_DIR", str(foreign_dictionary))
    with pytest.raises(ImportError) as refusal:
        OpenJTaklPhonemizer(alphabet)
    assert str(refusal.value) == _refusal(foreign_dictionary)


def test_refuses_an_empty_value(monkeypatch):
    """pyopenjtalk takes an empty value as a path, and the first reading fails."""
    monkeypatch.setenv("OPEN_JTALK_DICT_DIR", "")
    with pytest.raises(ImportError) as refusal:
        OpenJTaklPhonemizer()
    assert str(refusal.value) == _refusal("")


def test_refuses_the_dictionary_that_the_module_read_at_import(foreign_dictionary, monkeypatch):
    monkeypatch.setattr(pyopenjtalk, "OPEN_JTALK_DICT_DIR", str(foreign_dictionary).encode())
    with pytest.raises(ImportError) as refusal:
        OpenJTaklPhonemizer()
    assert str(refusal.value) == _refusal(foreign_dictionary)


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
