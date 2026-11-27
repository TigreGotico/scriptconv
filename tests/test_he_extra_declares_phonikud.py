"""Pins the ``he`` extra to actually provide the modules the Hebrew
phonemizer/diacritizer import.

``scriptconv/phonemizers/he.py`` does ``from phonikud import phonemize`` --
that is the ``phonikud`` PyPI distribution, a separate package from
``phonikud-onnx`` (which ``scriptconv/diacritics.py`` uses for niqqud
restoration via ``from phonikud_onnx import Phonikud``). Both backends are
exercised by the Hebrew pipeline, so ``pip install scriptconv[he]`` must
pull in both distributions -- declaring only one leaves the other import
failing at runtime with a message that just repeats what was already
installed.
"""
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # tomllib is stdlib only from Python 3.11
    import tomli as tomllib

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _he_extra_requirement_names():
    data = tomllib.loads(PYPROJECT.read_text())
    he = data["project"]["optional-dependencies"]["he"]
    names = set()
    for req in he:
        match = re.match(r"^[A-Za-z0-9_.-]+", req)
        if match:
            names.add(match.group(0).lower())
    return names


def test_he_extra_declares_both_phonikud_distributions():
    names = _he_extra_requirement_names()
    # phonikud-onnx: used by diacritics.py for niqqud restoration
    assert "phonikud-onnx" in names
    # phonikud: used by phonemizers/he.py for `from phonikud import phonemize`
    assert "phonikud" in names


def test_he_py_imports_from_declared_distribution():
    he_py = (PYPROJECT.parent / "scriptconv" / "phonemizers" / "he.py").read_text()
    assert "from phonikud import" in he_py
    names = _he_extra_requirement_names()
    assert "phonikud" in names, (
        "he.py imports the 'phonikud' package but the [he] extra does not "
        "declare it"
    )
